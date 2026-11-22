"""Route lecture seule des preuves d'invocation (synthétique, sans VPS)."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_bench.observation import executor as ex
from observability.operator_api import agent_invocation_reader as air
from observability.operator_api import app as api

REPO = Path(__file__).resolve().parents[1]
ZONE = REPO / "docs" / "agents" / "observation" / "examples" / "cartographer_zone_mission.json"
ZONE_SHA = "e387318eeaed81d4e6dc90228d46943a65a5b73c"
CODE_SHA = "3b67c91b641b4c805cf07c01782db4f547090a67"


@pytest.fixture()
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        monkeypatch.setattr(air, "DEFAULT_REPORTS_PATH", root / "reports")
        yield TestClient(api.app), root


def test_unknown_agent_is_refused_with_no_store(client):
    c, _ = client
    r = c.get("/api/operator/v1/agent-invocations/sniper-engine")
    assert r.status_code == 404 and r.json() == {"error_code": "AGENT_NOT_ALLOWED"}
    assert r.headers["cache-control"] == "no-store"


def test_missing_reports_is_explicit_absence(client):
    c, _ = client
    r = c.get("/api/operator/v1/agent-invocations/repository-cartographer")
    body = r.json()
    assert r.status_code == 200
    assert body["connection"] == "ABSENT" and body["activity"] == "INDETERMINE"
    assert body["read_only"] is True


def test_route_never_exposes_the_reports_path(client):
    c, root = client
    r = c.get("/api/operator/v1/agent-invocations/repository-cartographer")
    assert str(root) not in r.text


def inv_ts(env):
    from agent_bench.observation import invocation as inv
    return inv.parse_utc(env["ended_utc"])


def test_valid_terminal_invocation_is_shown_without_refreshing_activity(client):
    c, root = client
    mission = json.loads(ZONE.read_text(encoding="utf-8"))
    checkout = root / "checkout"
    for rel in mission["scope"]["read_paths"] + [".github/agents/repository-cartographer.agent.md"]:
        (checkout / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, checkout / rel)
    env = ex.run_once(mission=mission, checkout=checkout, reports=root / "reports",
                      runner_id="obs-repo-cartographer-ro-01", code_sha=CODE_SHA, analysed_sha=ZONE_SHA)
    body = c.get("/api/operator/v1/agent-invocations/repository-cartographer").json()
    assert body["connection"] == "AVAILABLE"
    assert body["last_result"] == "PARTIAL"
    assert body["activity"] == "TERMINE"
    assert body["last_activity_utc"] == env["ended_utc"]
    # Une relecture tardive (même fichier) ne rajeunit pas l'activité.
    later = air.read_agent_invocation("repository-cartographer", reports=root / "reports",
                                      now_ts=inv_ts(env) + 86400)
    assert later["last_activity_utc"] == env["ended_utc"]
