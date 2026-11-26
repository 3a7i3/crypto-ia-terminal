"""Programmateur (P6-GOV-02) : seule écriture de l'API, demande bornée, identité opérateur exigée.

L'API dépose une demande dans ``requests/`` et lit l'état publié par l'applicateur root dans
``state/`` ; elle ne lance rien. Tous les tests utilisent un dossier temporaire.
"""
import calendar
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from observability.operator_api import agent_schedule as sch
from observability.operator_api import app as api

URL = "/api/operator/v1/agent-invocations/repository-cartographer/schedule"
WHO = "operator@example.test"
TOKEN = "ab" * 32
H = {"x-cat-operator": "schedule", "x-cat-operator-identity": WHO, "x-cat-relay-token": TOKEN,
     "content-type": "application/json"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    (tmp_path / "requests").mkdir()
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(sch, "SCHEDULE_ROOT", tmp_path)
    monkeypatch.delenv("AGENT_SCHEDULE_ALLOW_TEST", raising=False)
    monkeypatch.setenv("CAT_OPERATOR_LOGINS", f"{WHO},second@example.test")
    tok = tmp_path / "relay.token"
    tok.write_text(TOKEN + "\n")
    os.chmod(tok, 0o640)
    monkeypatch.setenv("CAT_RELAY_TOKEN_FILE", str(tok))
    sch.reset_memory()
    yield TestClient(api.app), tmp_path
    sch.reset_memory()


def post(c, body, headers=H):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return c.post(URL, content=raw, headers=headers)


def requests_of(d):
    return sorted(p.name for p in (d / "requests").iterdir())


def test_get_without_anything_is_explicit(env):
    c, _ = env
    b = c.get(URL).json()
    assert b["requested"] is None and b["applied"] is None and b["allowed"] == ["10min", "1h", "off"]
    assert b["writable"] is True and b["reason"] == "aucun état appliqué publié"


@pytest.mark.parametrize("r", ["10min", "1h", "off"])
def test_post_writes_only_the_request_file(env, r):
    c, d = env
    res = post(c, {"rhythm": r})
    assert res.status_code == 202 and res.headers["cache-control"] == "no-store"
    assert (d / "requests" / "repository-cartographer.request").read_text() == r + "\n"
    assert requests_of(d) == ["repository-cartographer.request"]
    assert list((d / "state").iterdir()) == []
    b = res.json()
    assert b["requested"] == r and b["applied"] is None and len(b["request_id"]) == 16


def test_identity_is_required_and_checked(env, monkeypatch):
    c, d = env
    no_id = {k: v for k, v in H.items() if k != "x-cat-operator-identity"}
    assert post(c, {"rhythm": "1h"}, no_id).status_code == 401
    assert post(c, {"rhythm": "1h"}, {**H, "x-cat-operator-identity": "intruder@example.test"}).status_code == 403
    assert post(c, {"rhythm": "1h"}, {**H, "x-cat-operator-identity": "bad login\n"}).status_code == 401
    monkeypatch.setenv("CAT_OPERATOR_LOGINS", "")
    r = post(c, {"rhythm": "1h"})
    assert r.status_code == 403 and r.json()["error_code"] == "OPERATOR_ALLOWLIST_UNSET"
    assert requests_of(d) == []


def test_fixed_header_alone_is_not_enough(env):
    c, d = env
    assert c.post(URL, json={"rhythm": "1h"}, headers={"x-cat-operator": "schedule"}).status_code == 401
    assert post(c, {"rhythm": "1h"}, {k: v for k, v in H.items() if k != "x-cat-operator"}).status_code == 403
    assert requests_of(d) == []


def test_body_limits_and_strict_parsing(env):
    c, d = env
    assert post(c, b'{"rhythm":"1h"}', {**H, "content-type": "text/plain"}).status_code == 415
    assert post(c, b'{"rhythm":"1h","pad":"' + b"x" * 300 + b'"}').status_code == 413
    for body, why in [
        (b'{"rhythm":"1min"}', "test rhythm disabled"),
        (b'{"rhythm":"5s; rm -rf /"}', "injection"),
        (b"x", "not json"),
        (b'{"rhythm":"1h","rhythm":"off"}', "duplicate key"),
        (b'{"rhythm":"1h","agent":"market-observer"}', "extra key"),
        ('{"rhythm":"1hé"}'.encode(), "non ascii"),
        (b'["1h"]', "not an object"),
        (b'{"rhythm":1}', "not a string"),
    ]:
        assert post(c, body).status_code == 422, why
    assert requests_of(d) == []


def test_streamed_body_over_limit_is_refused(env):
    c, d = env

    def chunks():
        yield b'{"rhythm":"1h","pad":"'
        for _ in range(10):
            yield b"x" * 64
        yield b'"}'

    r = c.post(URL, content=chunks(), headers={k: v for k, v in H.items()})
    assert r.status_code == 413
    assert requests_of(d) == []


def test_other_agents_are_read_only(env):
    c, d = env
    for agent in ("data-provenance-auditor", "market-observer", "sniper-engine"):
        url = URL.replace("repository-cartographer", agent)
        assert c.post(url, content=b'{"rhythm":"off"}', headers=H).status_code == 404
    for agent in ("data-provenance-auditor", "market-observer"):
        b = c.get(URL.replace("repository-cartographer", agent)).json()
        assert b["writable"] is False and b["allowed"] == []
    assert requests_of(d) == []


def test_throttle_and_unchanged(env):
    c, d = env
    assert post(c, {"rhythm": "10min"}).status_code == 202
    r = post(c, {"rhythm": "1h"})
    assert r.status_code == 429 and 1 <= int(r.headers["retry-after"]) <= 31
    assert (d / "requests" / "repository-cartographer.request").read_text() == "10min\n"
    (d / "state" / "repository-cartographer.json").write_text('{"applied":"1h"}')
    r = post(c, {"rhythm": "1h"})
    assert r.status_code == 200 and r.json()["result"] == "UNCHANGED"


def test_hourly_cap(env):
    now = 1_800_000_000.0
    for i in range(sch.MAX_PER_HOUR):
        assert sch.throttle("repository-cartographer", "1h", None, now + i * 31)[0] == "ACCEPT"
        sch._accepted.append(now + i * 31)
    decision, retry = sch.throttle("repository-cartographer", "1h", None, now + sch.MAX_PER_HOUR * 31 + 5)
    assert decision == "THROTTLED" and retry > 0


def test_test_rhythm_only_when_enabled(env, monkeypatch):
    c, _ = env
    monkeypatch.setenv("AGENT_SCHEDULE_ALLOW_TEST", "1")
    assert post(c, {"rhythm": "1min"}).status_code == 202


def test_unwritable_requests_dir_is_503(env):
    c, d = env
    os.rmdir(d / "requests")
    os.symlink(d / "state", d / "requests")  # un lien à la place du dossier n'est jamais suivi
    r = post(c, {"rhythm": "1h"})
    assert r.status_code == 503 and r.json()["error_code"] == "CONTROL_UNWRITABLE"
    assert list((d / "state").iterdir()) == []


def test_audit_lines_have_no_body_or_headers(env, capfd):
    c, _ = env
    post(c, {"rhythm": "1h"})
    post(c, b'{"rhythm":"SECRETVALUE-tok"}')
    c.post(URL, content=b'{"rhythm":"1h"}', headers={**H, "x-cat-operator-identity": "intruder@example.test",
                                                       "authorization": "Bearer SECRET-TOKEN"})
    err = capfd.readouterr().err
    lines = [json.loads(ln) for ln in err.splitlines() if '"cat.schedule.audit"' in ln]
    assert [(x["decision"], x["http_status"]) for x in lines][:3] == [("ACCEPTED", 202), ("REFUSED", 422), ("REFUSED", 403)]
    assert lines[0]["identity"] == WHO and lines[0]["value"] == "1h"
    assert lines[1]["value"] is None
    assert "SECRET" not in err and "Bearer" not in err
    assert all(set(x) == {"event", "ts", "request_id", "identity", "agent", "value", "decision", "http_status", "reason"}
               for x in lines)


def test_operator_identity_route(env, monkeypatch):
    c, _ = env
    u = "/api/operator/v1/operator-identity"
    ok = {"x-cat-operator-identity": WHO, "x-cat-relay-token": TOKEN}
    assert c.get(u, headers=ok).json() == {"identity": WHO, "authorized": True, "reason": None}
    assert c.get(u, headers={"x-cat-operator-identity": WHO}).json()["reason"] == "RELAY_TOKEN_INVALID"
    assert c.get(u).json()["authorized"] is False


def test_state_symlink_is_not_followed(env, tmp_path_factory):
    c, d = env
    secret = tmp_path_factory.mktemp("outside") / "secret.json"
    secret.write_text('{"applied":"1h"}')
    os.symlink(secret, d / "state" / "repository-cartographer.json")
    b = c.get(URL).json()
    assert b["applied"] is None and b["connection"] == "UNREADABLE"


def test_applied_status_is_read_back(env):
    c, d = env
    (d / "state" / "repository-cartographer.json").write_text(
        '{"applied":"1h","applied_utc":"2026-11-22T07:00:00Z","next_utc":"2026-11-22T08:00:00Z"}')
    b = c.get(URL).json()
    assert b["applied"] == "1h" and b["next_utc"].endswith(":00:00Z")


def test_only_this_route_mutates():
    mut = [(r.path, sorted(r.methods & {"POST", "PUT", "PATCH", "DELETE"}))
           for r in api.app.routes if (getattr(r, "methods", None) or set()) & {"POST", "PUT", "PATCH", "DELETE"}]
    assert mut == [("/api/operator/v1/agent-invocations/{agent_id}/schedule", ["POST"])]


def test_next_slot_follows_the_clock_after_each_pass(tmp_path):
    (tmp_path / "state").mkdir()
    st = tmp_path / "state" / "repository-cartographer.json"
    st.write_text('{"applied":"10min","applied_utc":"2026-11-22T08:24:00Z","next_utc":"2026-11-22T08:30:00Z"}')

    def at(s):
        return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))

    rs = sch.read_schedule
    assert rs("repository-cartographer", root=tmp_path, now_ts=at("2026-11-22T08:24:10Z"))["next_utc"] == "2026-11-22T08:30:00Z"
    assert rs("repository-cartographer", root=tmp_path, now_ts=at("2026-11-22T08:30:01Z"))["next_utc"] == "2026-11-22T08:40:00Z"
    st.write_text('{"applied":"1h"}')
    assert rs("repository-cartographer", root=tmp_path, now_ts=at("2026-11-22T09:20:00Z"))["next_utc"] == "2026-11-22T10:00:00Z"
    st.write_text('{"applied":"off","next_utc":"2026-11-22T10:00:00Z"}')
    assert rs("repository-cartographer", root=tmp_path)["next_utc"] is None


def test_relay_token_is_required_on_the_internal_transport(env, tmp_path):
    """Un processus local qui joint l'API directement ne connaît pas le jeton du relais."""
    c, d = env
    forged = {k: v for k, v in H.items() if k != "x-cat-relay-token"}
    r = post(c, {"rhythm": "1h"}, forged)
    assert r.status_code == 401 and r.json()["error_code"] == "RELAY_TOKEN_INVALID"
    r = post(c, {"rhythm": "1h"}, {**H, "x-cat-relay-token": "cd" * 32})
    assert r.status_code == 401
    r = post(c, {"rhythm": "1h"}, {**H, "x-cat-relay-token": TOKEN.upper()})
    assert r.status_code == 401
    assert requests_of(d) == []


@pytest.mark.parametrize("variant", ["missing", "unset", "world_readable", "symlink", "short", "fifo"])
def test_bad_token_file_closes_writes(env, monkeypatch, tmp_path, variant):
    c, d = env
    tok = tmp_path / "relay.token"
    if variant == "missing":
        tok.unlink()
    elif variant == "unset":
        monkeypatch.delenv("CAT_RELAY_TOKEN_FILE")
    elif variant == "world_readable":
        os.chmod(tok, 0o644)
    elif variant == "symlink":
        real = tmp_path / "real.token"
        real.write_text(TOKEN)
        os.chmod(real, 0o640)
        tok.unlink()
        os.symlink(real, tok)
    elif variant == "short":
        tok.write_text("abc")
    elif variant == "fifo":
        tok.unlink()
        os.mkfifo(tok)
    r = post(c, {"rhythm": "1h"})
    assert r.status_code == 403 and r.json()["error_code"] == "RELAY_TOKEN_UNSET"
    assert requests_of(d) == []
