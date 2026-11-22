"""Programmateur : seule écriture de l'API, liste fermée, en-tête opérateur exigé, aucun lancement."""
import pytest
from fastapi.testclient import TestClient

from observability.operator_api import agent_schedule as sch
from observability.operator_api import app as api

URL = "/api/operator/v1/agent-invocations/repository-cartographer/schedule"
H = {"x-cat-operator": "schedule"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sch, "CONTROL_PATH", tmp_path)
    monkeypatch.delenv("AGENT_SCHEDULE_ALLOW_TEST", raising=False)
    return TestClient(api.app), tmp_path


def test_get_without_anything_is_explicit(client):
    c, _ = client
    b = c.get(URL).json()
    assert b["requested"] is None and b["applied"] is None and b["allowed"] == ["10min", "1h", "off"]


@pytest.mark.parametrize("r", ["10min", "1h", "off"])
def test_post_writes_only_the_request_file(client, r):
    c, d = client
    res = c.post(URL, json={"rhythm": r}, headers=H)
    assert res.status_code == 202 and res.headers["cache-control"] == "no-store"
    assert (d / "repository-cartographer.rhythm").read_text() == r + "\n"
    assert sorted(p.name for p in d.iterdir()) == ["repository-cartographer.rhythm"]
    assert res.json()["requested"] == r and res.json()["applied"] is None


def test_refusals_write_nothing(client):
    c, d = client
    assert c.post(URL, json={"rhythm": "1h"}).status_code == 403
    assert c.post(URL, json={"rhythm": "1min"}, headers=H).status_code == 422
    assert c.post(URL, json={"rhythm": "5s; rm -rf /"}, headers=H).status_code == 422
    assert c.post(URL, content=b"x", headers=H).status_code == 422
    other = URL.replace("repository-cartographer", "sniper-engine")
    assert c.post(other, json={"rhythm": "1h"}, headers=H).status_code == 404
    assert list(d.iterdir()) == []


def test_test_rhythm_only_when_enabled(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("AGENT_SCHEDULE_ALLOW_TEST", "1")
    assert c.post(URL, json={"rhythm": "1min"}, headers=H).status_code == 202


def test_applied_status_is_read_back(client):
    c, d = client
    (d / "repository-cartographer.status.json").write_text(
        '{"applied":"1h","applied_utc":"2026-11-22T07:00:00Z","next_utc":"2026-11-22T08:00:00Z"}')
    b = c.get(URL).json()
    assert b["applied"] == "1h" and b["next_utc"] == "2026-11-22T08:00:00Z"


def test_only_this_route_mutates():
    mut = [(r.path, sorted(r.methods & {"POST", "PUT", "PATCH", "DELETE"}))
           for r in api.app.routes if (getattr(r, "methods", None) or set()) & {"POST", "PUT", "PATCH", "DELETE"}]
    assert mut == [("/api/operator/v1/agent-invocations/{agent_id}/schedule", ["POST"])]
