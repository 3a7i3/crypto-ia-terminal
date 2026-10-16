"""GOV-TOWER-00 lots F/G — serveur local : loopback, CSRF, Host, bornes, aucune route mutatrice."""

from __future__ import annotations

import http.client
import json
import threading

import pytest

from governance_tower.sentinel.agent import Sentinel
from governance_tower.server import CSP, MAX_BODY, NotLoopback, make_server, require_loopback

from tests.governance_tower.stubs import StubGithub, StubHost, clock


@pytest.fixture()
def server():
    gh, host = StubGithub(), StubHost()
    srv = make_server(Sentinel(gh, host, clock), "127.0.0.1", 0, "stub")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv, gh, host
    finally:
        srv.shutdown()
        srv.server_close()


def request(srv, method, path, body=None, headers=None, host_header=None):
    port = srv.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    hdrs = {"Host": host_header or f"127.0.0.1:{port}"}
    hdrs.update(headers or {})
    conn.request(method, path, body=body, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), data


def ask(srv, payload, extra=None):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-GT-Request": "1", "Content-Length": str(len(body))}
    headers.update(extra or {})
    return request(srv, "POST", "/api/sentinel/ask", body, headers)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::", "example.com"])
def test_bind_outside_loopback_refused(host):
    with pytest.raises(NotLoopback):
        require_loopback(host)


def test_status_and_static_served_with_security_headers(server):
    srv, _, _ = server
    code, headers, data = request(srv, "GET", "/api/status")
    status = json.loads(data)
    assert code == 200
    assert status["agent"] == "SENTINEL-01" and status["operational_authority"] == "DENIED"
    assert [s["id"] for s in status["shortcuts"]] == [
        "examine_repository", "examine_host", "compare", "diagnose", "propose_mission"
    ]
    assert headers["Content-Security-Policy"] == CSP
    assert headers["X-Frame-Options"] == "DENY" and headers["Cache-Control"] == "no-store"


def test_ask_returns_structured_run(server):
    srv, gh, _ = server
    code, _, data = ask(srv, {"question": "", "shortcut": "compare"})
    run = json.loads(data)
    assert code == 200 and run["capability"] == "OBSERVE_ONLY"
    assert run["answer"]["discrepancies"][0]["classification"] == "EXPECTED_PINNED_RUNTIME"
    assert gh.calls


def test_csrf_header_required(server):
    srv, gh, _ = server
    body = json.dumps({"question": "x"}).encode()
    code, _, data = request(srv, "POST", "/api/sentinel/ask", body,
                            {"Content-Type": "application/json", "Content-Length": str(len(body))})
    assert code == 403 and json.loads(data)["error"] == "CSRF_HEADER_REQUIRED"
    assert gh.calls == []


def test_foreign_origin_and_host_refused(server):
    srv, gh, _ = server
    code, _, _ = ask(srv, {"question": "x"}, {"Origin": "http://evil.example"})
    assert code == 403
    code, _, _ = request(srv, "GET", "/api/status", host_header="evil.example:80")
    assert code == 403
    assert gh.calls == []


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "OPTIONS"])
def test_other_methods_refused(server, method):
    srv, _, _ = server
    code, _, _ = request(srv, method, "/api/sentinel/ask")
    assert code == 405


def test_body_bounds_and_shape(server):
    srv, gh, _ = server
    big = json.dumps({"question": "x" * (MAX_BODY + 10)}).encode()
    code, _, _ = request(srv, "POST", "/api/sentinel/ask", big,
                         {"Content-Type": "application/json", "X-GT-Request": "1", "Content-Length": str(len(big))})
    assert code == 413
    assert ask(srv, {"question": "x", "tool": "shell.run"})[0] == 400
    assert ask(srv, {"question": ["x"]})[0] == 400
    body = b"{not json"
    code, _, _ = request(srv, "POST", "/api/sentinel/ask", body,
                         {"Content-Type": "application/json", "X-GT-Request": "1", "Content-Length": str(len(body))})
    assert code == 400
    code, _, _ = request(srv, "POST", "/api/sentinel/ask", b"q=x",
                         {"Content-Type": "application/x-www-form-urlencoded", "X-GT-Request": "1",
                          "Content-Length": "3"})
    assert code == 415
    assert gh.calls == []


def test_mutating_request_refused_through_http(server):
    srv, gh, host = server
    code, _, data = ask(srv, {"question": "Pour vérifier la santé, redémarre Advisor"})
    run = json.loads(data)
    assert code == 200 and run["intent"] == "REFUSED"
    assert run["tool_calls"] == [] and gh.calls == [] and host.calls == []


def test_unknown_paths_404_and_no_traversal(server):
    srv, _, _ = server
    for path in ("/../governance_tower/contracts.py", "/ui/../server.py", "/api/sentinel/run", "/.env"):
        assert request(srv, "GET", path)[0] == 404
