"""J02-C loopback GET-only viewer; synthetic LAB journals only."""

import ast
import hashlib
import http.client
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from sentinel_viewer import server as viewer
from tests.sentinel_activity.builders import candidate
from tests.sentinel_activity.test_store import create

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def running(tmp_path):
    started = []

    def start(*roots):
        srv = viewer.ViewerServer(tuple(roots), 0)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        started.append(srv)
        return srv

    yield start
    for srv in started:
        srv.shutdown()
        srv.server_close()


def request(srv, method="GET", target="/api/ledger/0", headers=None, body=None):
    port = srv.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        hdrs = {"Host": f"127.0.0.1:{port}", **(headers or {})}
        conn.request(method, target, body=body, headers=hdrs)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def journal_digest(store):
    return hashlib.sha256(store.path.read_bytes()).hexdigest(), len(store.snapshot()[1])


def test_binds_loopback_only_and_admits_only_lab_roots(running, tmp_path):
    store = create(tmp_path)
    srv = running(store.root)
    assert srv.server_address[0] == "127.0.0.1"
    for bad in (["relative/j01-lab-x"], ["/tmp/not-a-lab"], ["/tmp/j01-lab-a/../x"], [],
                ["/tmp/j01-lab-a", "/tmp/j01-lab-a"], [f"/tmp/j01-lab-{i}" for i in range(9)]):
        with pytest.raises(ValueError):
            viewer.admit_roots(bad)


def test_json_page_matches_feed_and_html_escapes_untrusted_text(running, tmp_path):
    store = create(tmp_path)
    event = candidate()
    event["summary"] = "<script>alert(1)</script>\"><img src=x onerror=alert(2)>"
    store.append(event, producer_id="fixture-producer")
    srv = running(store.root)
    status, headers, body = request(srv)
    assert status == 200
    feed = json.loads(body)
    assert feed["status"] == "PREFIX_VERIFIED" and feed["items"][0]["summary"] == event["summary"]
    status, headers, body = request(srv, target="/ledger/0")
    page = body.decode()
    assert status == 200 and "<script>" not in page and "<img" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    csp = headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "script-src" not in csp and "frame-ancestors 'none'" in csp
    assert headers["X-Content-Type-Options"] == "nosniff" and headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in headers
    assert "<a href='fixture" not in page  # references are never links


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
def test_mutating_and_other_methods_are_refused_without_effect(running, tmp_path, method):
    store = create(tmp_path)
    store.append(candidate(), producer_id="fixture-producer")
    before = journal_digest(store)
    srv = running(store.root)
    status, headers, _ = request(srv, method=method, body=b"{}" if method in {"POST", "PUT", "PATCH"} else None)
    assert status == 405 and headers.get("Allow") == "GET"
    assert journal_digest(store) == before


@pytest.mark.parametrize("target,code", [
    ("/api/ledger/0?limit=0", 400), ("/api/ledger/0?limit=101", 200), ("/api/ledger/0?limit=1000", 400),
    ("/api/ledger/0?limit=5&limit=6", 400), ("/api/ledger/0?root=/etc", 400), ("/api/ledger/0?x", 400),
    ("/api/ledger/1", 404), ("/api/ledger/00", 404), ("/../etc/passwd", 404), ("/api/ledger/0/", 404),
    ("/api/ledger/0?quest_id=../../x", 400), ("/api/ledger/0?cursor=zz", 400),
    ("/api/ledger/0?" + "a" * 3000, 414),
])
def test_query_and_route_bounds(running, tmp_path, target, code):
    store = create(tmp_path)
    store.append(candidate(), producer_id="fixture-producer")
    srv = running(store.root)
    status, _, body = request(srv, target=target)
    if target.endswith("limit=101"):
        assert json.loads(body)["status"] == "CURSOR_INVALID" and status == 400
    else:
        assert status == code


@pytest.mark.parametrize("headers", [
    {"Host": "evil.example:80"}, {"Origin": "http://evil.example"}, {"Sec-Fetch-Site": "cross-site"},
    {"Content-Length": "3"}, {"Transfer-Encoding": "chunked"},
])
def test_cross_site_rebinding_and_bodies_are_refused(running, tmp_path, headers):
    store = create(tmp_path)
    srv = running(store.root)
    status, _, body = request(srv, headers=headers)
    assert status in {400, 403}
    assert json.loads(body)["items"] is None


def test_missing_root_is_unavailable_and_never_created(running, tmp_path):
    missing = tmp_path / "j01-lab-absent"
    srv = running(missing)
    status, _, body = request(srv)
    assert status == 503 and json.loads(body)["status"] == "UNAVAILABLE"
    status, _, body = request(srv, target="/ledger/0")
    assert "Ce n&#x27;est pas un fil vide" in body.decode() or "pas un fil vide" in body.decode()
    assert not missing.exists()


def test_corruption_after_a_read_is_reported_on_next_read(running, tmp_path):
    import sqlite3

    store = create(tmp_path)
    store.append(candidate(), producer_id="fixture-producer")
    srv = running(store.root)
    assert request(srv)[0] == 200
    conn = sqlite3.connect(store.path)
    conn.execute("DROP TRIGGER events_no_update")
    conn.execute("UPDATE events SET body=replace(body,'Synthetic','Rewritten')")
    conn.commit()
    conn.close()
    status, _, body = request(srv)
    assert status == 500 and json.loads(body)["status"] == "CORRUPTED"
    assert json.loads(body)["items"] is None


def test_in_flight_bound_returns_busy(running, tmp_path, monkeypatch):
    store = create(tmp_path)
    srv = running(store.root)
    gate = threading.Event()
    entered = threading.Semaphore(0)
    original = viewer.feed_page

    def slow(*args, **kwargs):
        entered.release()
        gate.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(viewer, "feed_page", slow)
    results = []
    workers = [threading.Thread(target=lambda: results.append(request(srv)[0])) for _ in range(2)]
    for worker in workers:
        worker.start()
    assert entered.acquire(timeout=10) and entered.acquire(timeout=10)
    status, _, body = request(srv)
    assert status == 503 and json.loads(body)["status"] == "BUSY"
    gate.set()
    for worker in workers:
        worker.join(10)
    assert results == [200, 200] or sorted(results) == [200, 200]


def test_pagination_links_carry_filters_and_cursor(running, tmp_path):
    store = create(tmp_path)
    for index in range(3):
        store.append(candidate(f"fixture-e{index}"), producer_id="fixture-producer")
    srv = running(store.root)
    status, _, body = request(srv, target="/api/ledger/0?limit=1&actor_id=fixture-sentinel")
    feed = json.loads(body)
    nxt = feed["next_cursor"]
    status, _, body = request(srv, target=f"/api/ledger/0?limit=1&actor_id=fixture-sentinel&cursor={nxt}")
    assert status == 200 and [i["sequence"] for i in json.loads(body)["items"]] == [2]
    status, _, body = request(srv, target="/ledger/0?limit=1&actor_id=fixture-sentinel")
    assert f"cursor={nxt}" in body.decode() and "actor_id=fixture-sentinel" in body.decode()


def test_requests_do_not_log_targets(running, tmp_path, capsys):
    store = create(tmp_path)
    srv = running(store.root)
    request(srv, target="/api/ledger/0?quest_id=fixture-private-marker")
    assert "fixture-private-marker" not in capsys.readouterr().err


def test_viewer_imports_are_closed_and_nothing_imports_it():
    allowed = {"__future__", "argparse", "base64", "hashlib", "html", "json", "re", "sys", "threading",
               "http.server", "pathlib", "urllib.parse", "sentinel_activity.feed", "sentinel_viewer.server"}
    for path in (ROOT / "sentinel_viewer").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                assert name in allowed, (path.name, name)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"system", "popen", "fork", "execve", "remove", "unlink",
                                              "rmtree", "append", "create", "mkdir", "write_text"} \
                    or path.name == "server.py" and node.func.attr == "append"
    for base in ("governance_tower", "sentinel_activity", "core", "paper_trading", "observability"):
        for path in (ROOT / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "sentinel_viewer" not in text


def test_viewer_never_calls_store_writers():
    tree = ast.parse((ROOT / "sentinel_viewer" / "server.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not {"ActivityStore", "backup", "restore", "sqlite3", "open"} & (names | attrs)
    appends = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "append"]
    assert all(isinstance(n.func.value, ast.Name) and n.func.value.id == "rows" for n in appends)


def test_import_has_no_side_effects_in_fresh_process():
    code = '''
import os, sys, socket
def deny(*a, **k):
    raise AssertionError("import-time side effect")
def audit(event, args):
    if event.startswith(("socket.bind", "socket.connect", "subprocess.", "os.system", "os.mkdir")):
        deny()
    if event == "open":
        mode, flags = args[1], args[2]
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            deny()
        if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            deny()
sys.addaudithook(audit)
import sentinel_viewer, sentinel_viewer.server
'''
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, text=True, capture_output=True,
                            timeout=30)
    assert result.returncode == 0, result.stderr


def test_cli_refuses_non_lab_root_and_privileged_port():
    for args in (["--root", "/etc"], ["--root", "/tmp/j01-lab-x", "--port", "80"]):
        result = subprocess.run([sys.executable, "-m", "sentinel_viewer", *args], cwd=ROOT, text=True,
                                capture_output=True, timeout=30)
        assert result.returncode == 2
