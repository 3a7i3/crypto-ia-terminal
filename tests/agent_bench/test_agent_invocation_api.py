"""Route lecture seule des preuves d'invocation : vrai dépôt git, vrai exécuteur, aucun VPS."""
import json
import time

import pytest
from fastapi.testclient import TestClient
from invocation_bench import ZONE_MISSION, lock_content

from agent_bench.observation import executor as ex
from agent_bench.observation import invocation as inv
from observability.operator_api import agent_invocation_reader as air
from observability.operator_api import app as api

URL = "/api/operator/v1/agent-invocations/repository-cartographer"


@pytest.fixture()
def client(monkeypatch, genv):
    monkeypatch.setattr(air, "DEFAULT_REPORTS_PATH", genv.reports)
    # La mission de banc pointe sur le commit du checkout de banc : identité attendue ajustée.
    target = dict(air.TARGETS["repository-cartographer"], mission_id=genv.mission["mission_id"])
    monkeypatch.setitem(air.TARGETS, "repository-cartographer", target)
    return TestClient(api.app), genv


def test_targets_match_the_committed_zone_mission():
    m = json.loads(ZONE_MISSION.read_text(encoding="utf-8"))
    t = air.TARGETS["repository-cartographer"]
    assert t["mission_id"] == m["mission_id"]
    assert t["profile_blob_sha1"] == m["profile"]["blob_sha1"]


def test_unknown_agent_is_refused_with_no_store(client):
    c, _ = client
    r = c.get("/api/operator/v1/agent-invocations/sniper-engine")
    assert r.status_code == 404 and r.json() == {"error_code": "AGENT_NOT_ALLOWED"}
    assert r.headers["cache-control"] == "no-store"


def test_missing_reports_is_explicit_absence_and_gray(client):
    c, _ = client
    r = c.get(URL)
    body = r.json()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert body["connection"] == "ABSENT" and body["activity"] == "INDETERMINE"
    assert body["display"]["light"] == "GRAY" and body["display"]["valid_until_utc"] is None
    assert body["read_only"] is True


def test_route_never_exposes_the_reports_path(client):
    c, genv = client
    ex.run_once(**genv.kwargs())
    r = c.get(URL)
    assert str(genv.root) not in r.text


def test_valid_terminal_invocation_is_red_and_never_refreshed(client):
    c, genv = client
    env, _ = ex.run_once(**genv.kwargs())
    body = c.get(URL).json()
    assert body["connection"] == "AVAILABLE"
    assert body["last_result"] == env["result_status"]
    assert body["activity"] == "TERMINE" and body["display"]["light"] == "RED"
    assert body["display"]["label"].startswith("Inactif · fin normale")
    assert body["last_activity_utc"] == env["ended_utc"]
    later = air.read_agent_invocation("repository-cartographer", reports=genv.reports,
                                      now_ts=inv.parse_utc(env["ended_utc"]) + 86400)
    assert later["last_activity_utc"] == env["ended_utc"]
    assert later["server_observed_at_utc"] != body["server_observed_at_utc"]


def test_running_invocation_is_green_only_with_kernel_lock(client, holders):
    c, genv = client
    h = holders(genv.reports, lock_content(genv.mission["mission_id"], time.time()))
    body = c.get(URL).json()
    assert body["activity"] == "EN_COURS" and body["life_observed"] is True
    assert body["display"]["light"] == "GREEN"
    assert inv.parse_utc(body["display"]["valid_until_utc"]) <= time.time() + inv.DISPLAY_TTL_S + 1
    h.kill()
    body = c.get(URL).json()
    assert body["activity"] != "EN_COURS" and body["display"]["light"] != "GREEN"


def test_wrong_qualified_profile_is_invalid_gray(client, monkeypatch):
    c, genv = client
    ex.run_once(**genv.kwargs())
    target = dict(air.TARGETS["repository-cartographer"], profile_blob_sha1="0" * 40)
    monkeypatch.setitem(air.TARGETS, "repository-cartographer", target)
    body = c.get(URL).json()
    assert body["connection"] == "INVALID" and body["display"]["light"] == "GRAY"


def test_reader_crash_becomes_gray_unreadable(client, monkeypatch):
    c, _ = client

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(air.rd, "read_status", boom)
    body = c.get(URL).json()
    assert body["connection"] == "UNREADABLE" and body["display"]["light"] == "GRAY"
