"""Observateur Marché : contrôles purs, exécuteur runtime (vrai dépôt git), validation, route API."""
import copy
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from agent_bench.observation import agents as ag
from agent_bench.observation import executor as ex
from agent_bench.observation import invocation as inv
from agent_bench.observation import market_observer as mo
from agent_bench.observation import runtime_observer as ro

REPO = Path(__file__).resolve().parents[2]
MISSION = json.loads((REPO / "docs/agents/observation/examples/market_observer_mission.json").read_text(encoding="utf-8"))
NOW_MS = 1795398010000


def health(**over):
    b = {"clock": {"rtt_ms": 325}, "collector": {"state": "RUNNING", "last_success_ms": str(NOW_MS - 5000),
                                                 "failures": 0, "fault_injection": False},
         "evidence_kind": "PUBLIC_OBSERVED", "histories_available": 120, "histories_expected": 120,
         "selected_instruments": 30, "states": {"LIVE": 30, "STALE": 0, "DISCONNECTED": 0, "UNRESOLVED": 0, "SYNTHETIC": 0},
         "unavailable": []}
    for k, v in over.items():
        b[k] = v
    return b


def rows(n=3, age=7000, state="LIVE", issue=None):
    return {"complete": True, "rows": [{"display_symbol": f"S{i}/USDT", "data_issue": issue,
                                        "freshness": {"age_ms": age, "state": state}} for i in range(n)]}


MARKET = {"generated_at_utc": "2026-10-29T05:32:36Z", "snapshot_age_s": 2146055.07,
          "freshness_classification": "STALE", "universe_size": 124}


def ok(body):
    return {"http_status": 200, "body": body, "bytes": 10, "sha256": "0" * 64, "error": None}


def resp(h=None, r=None, m=None):
    return {"scanner_health": ok(h or health()), "scanner_rows": ok(r or rows()), "operator_market": ok(m or MARKET)}


def verdicts(ct):
    return {c["code"]: c["verdict"] for c in ct["checks"]}


def test_mission_is_sealed_and_bounded_to_loopback_routes():
    ro.validate_mission(MISSION)
    assert MISSION["mission_id"] == ro.mission_id_of(MISSION)
    assert {s["port"] for s in MISSION["sources"]} <= set(ro.ALLOWED_PORTS)
    bad = copy.deepcopy(MISSION)
    bad["sources"][0]["path"] = "/admin/restart"
    bad["mission_id"] = ro.mission_id_of(bad)
    with pytest.raises(ex.Refused):
        ro.validate_mission(bad)
    for p in ("/api/operator/v1/../x", "/api/operator/v1/x?y=1"):
        b = copy.deepcopy(MISSION)
        b["sources"][0]["path"] = p
        b["mission_id"] = ro.mission_id_of(b)
        with pytest.raises(ex.Refused):
            ro.validate_mission(b)


def test_healthy_scanner_and_stale_market_snapshot():
    ct = mo.analyse(resp(), MISSION, NOW_MS)
    v = verdicts(ct)
    assert ct["status"] == "COMPLETE"
    assert {v[k] for k in ("COLLECTOR_FRESHNESS", "COLLECTOR_STATE", "INSTRUMENTS_LIVE", "HISTORY_COVERAGE",
                            "ROWS_FRESHNESS", "FAULT_INJECTION_OFF", "EVIDENCE_PUBLIC_OBSERVED")} == {"OK"}
    # /market figé au 29 octobre : âge publié par l'API repris tel quel, alerte au-delà de 24 h.
    assert v["MARKET_SNAPSHOT_FRESHNESS"] == "ALERT"
    assert ct["metrics"]["market_snapshot_age_s"] == 2146055.1
    assert [f["code"] for f in ct["findings"]] == ["MARKET_SNAPSHOT_FRESHNESS"]


def test_collector_pause_between_campaigns_is_not_an_alert():
    h = health(collector={"state": "STOPPED", "last_success_ms": str(NOW_MS - 30_000), "failures": 0,
                          "fault_injection": False})
    assert verdicts(mo.analyse(resp(h=h), MISSION, NOW_MS))["COLLECTOR_STATE"] == "WARN"
    h["collector"]["last_success_ms"] = str(NOW_MS - 900_000)
    v = verdicts(mo.analyse(resp(h=h), MISSION, NOW_MS))
    assert v["COLLECTOR_STATE"] == "ALERT" and v["COLLECTOR_FRESHNESS"] == "ALERT"


def test_synthetic_or_missing_instruments_are_flagged():
    h = health(states={"LIVE": 28, "STALE": 1, "DISCONNECTED": 0, "UNRESOLVED": 0, "SYNTHETIC": 1})
    assert verdicts(mo.analyse(resp(h=h), MISSION, NOW_MS))["INSTRUMENTS_LIVE"] == "ALERT"
    h = health(states={"LIVE": 28, "STALE": 2, "DISCONNECTED": 0, "UNRESOLVED": 0, "SYNTHETIC": 0})
    assert verdicts(mo.analyse(resp(h=h), MISSION, NOW_MS))["INSTRUMENTS_LIVE"] == "WARN"
    v = verdicts(mo.analyse(resp(r=rows(age=700_000, state="STALE", issue="BOOK_CROSSED")), MISSION, NOW_MS))
    assert v["ROWS_FRESHNESS"] == "ALERT" and v["ROWS_NOT_LIVE"] == "WARN" and v["ROWS_DATA_ISSUES"] == "WARN"


def test_unreadable_source_is_unknown_never_zero():
    r = resp()
    r["scanner_health"] = {"http_status": None, "body": None, "bytes": None, "sha256": None, "error": "ConnectionRefusedError"}
    ct = mo.analyse(r, MISSION, NOW_MS)
    assert ct["status"] == "PARTIAL"
    assert "INSTRUMENTS_LIVE" not in verdicts(ct) and "instruments_selected" not in ct["metrics"]
    assert ct["unknowns"][0] == {"code": "SOURCE_UNREADABLE", "source": "scanner_health", "reason": "ConnectionRefusedError"}
    h = health()
    del h["collector"]["failures"]
    ct = mo.analyse(resp(h=h), MISSION, NOW_MS)
    assert verdicts(ct)["COLLECTOR_FAILURES"] == "UNKNOWN" and ct["metrics"]["collector_failures"] is None
    assert ct["status"] == "PARTIAL"
    down = {k: {"http_status": 503, "body": None, "bytes": 0, "sha256": None, "error": None} for k in mo.SOURCE_IDS}
    assert mo.analyse(down, MISSION, NOW_MS)["status"] == "BLOCKED"


# --------------------------------------------------------------------------- exécuteur runtime

def git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def checkout(tmp_path):
    co = tmp_path / "checkout"
    for rel in [f"agent_bench/observation/{p.name}" for p in (REPO / "agent_bench/observation").glob("*.py")] \
            + ["agent_bench/__init__.py", MISSION["profile"]["source_path"]]:
        (co / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, co / rel)
    git(co.parent, "init", "-q", "-b", "main", str(co))
    git(co, "add", "-A")
    git(co, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "code")
    (tmp_path / "reports").mkdir()
    return co, git(co, "rev-parse", "HEAD"), tmp_path / "reports"


def fake_fetcher(port, path):
    """Réponses saines à l'heure réelle de l'invocation (le collecteur vient de réussir)."""
    sid = next(s["id"] for s in MISSION["sources"] if s["path"] == path and s["port"] == port)
    h = health()
    h["collector"]["last_success_ms"] = str(int(time.time() * 1000) - 5000)
    return resp(h=h)[sid]


def _valid(env):
    return inv.validate_envelope(env, agent_id="market-observer", runner_id="obs-market-ro-01",
                                 mission_id=MISSION["mission_id"], now_ts=time.time() + 5,
                                 expected_profile_blob=MISSION["profile"]["blob_sha1"])


def test_runtime_run_publishes_a_valid_sealed_envelope(checkout):
    co, sha, reports = checkout
    env, name = ro.run_once(mission=MISSION, checkout=co, reports=reports, runner_id="obs-market-ro-01",
                            code_sha=sha, fetcher=fake_fetcher)
    assert env["contract"] == inv.RUNTIME_INVOCATION_CONTRACT and env["state"] == "COMPLETED"
    assert (reports / "runs" / MISSION["mission_id"] / name).is_file()
    assert _valid(env) == ("VALID", "ok")
    assert "agent_bench/observation/market_observer.py" in env["verification"]["executed_modules"]
    t = copy.deepcopy(env)
    t["report"]["content"]["checks"][0]["verdict"] = "OK" if t["report"]["content"]["checks"][0]["verdict"] != "OK" else "ALERT"
    assert _valid(t)[0] == "INVALID"
    t = copy.deepcopy(env)
    t["agent_id"] = "data-provenance-auditor"
    assert _valid(t)[0] == "INVALID"


def test_runtime_run_refuses_a_modified_checkout_before_locking(checkout):
    co, sha, reports = checkout
    (co / MISSION["profile"]["source_path"]).write_text("modifié\n")
    with pytest.raises(ex.Refused) as e:
        ro.run_once(mission=MISSION, checkout=co, reports=reports, runner_id="obs-market-ro-01", code_sha=sha,
                    fetcher=fake_fetcher)
    assert e.value.code == "PROFILE_MODIFIED"
    assert not (reports / "locks").exists()


def test_fetch_failure_inside_the_run_is_published_as_partial(checkout):
    co, sha, reports = checkout

    def broken(port, path):
        return {"http_status": None, "body": None, "bytes": None, "sha256": None, "error": "ConnectionRefusedError"} \
            if port == 8090 else fake_fetcher(port, path)

    env, _ = ro.run_once(mission=MISSION, checkout=co, reports=reports, runner_id="obs-market-ro-01", code_sha=sha,
                         fetcher=broken)
    assert env["result_status"] == "PARTIAL" and _valid(env) == ("VALID", "ok")


def test_fetch_is_loopback_get_and_never_raises():
    out = ro.fetch(1, "/api/operator/v1/market")  # port fermé : panne consignée, pas d'exception
    assert out["http_status"] is None and out["error"]


def test_api_reads_the_market_observer_folder(checkout, monkeypatch):
    from fastapi.testclient import TestClient

    from observability.operator_api import agent_invocation_reader as air
    from observability.operator_api import app as api

    co, sha, reports = checkout
    ro.run_once(mission=MISSION, checkout=co, reports=reports, runner_id="obs-market-ro-01", code_sha=sha,
                fetcher=fake_fetcher)
    monkeypatch.setattr(air, "MARKET_REPORTS_PATH", reports)
    c = TestClient(api.app)
    base = "/api/operator/v1/agent-invocations/market-observer"
    st = c.get(base).json()
    assert st["connection"] == "AVAILABLE" and st["last_result"] == "COMPLETE" and st["display"]["light"] == "RED"
    h = c.get(f"{base}/history").json()
    item = h["items"][0]
    assert item["verdict"] == "VALID" and item["analysed_sha"] is None
    s = item["summary"]
    assert s["domain"] == "MARKET" and s["found"] == ["MARKET_SNAPSHOT_FRESHNESS"]
    assert {k["code"]: k["verdict"] for k in s["checks"]}["MARKET_SNAPSHOT_FRESHNESS"] == "ALERT"
    assert s["verdict_counts"]["ALERT"] == 1


def test_registry_api_target_and_mission_agree():
    from observability.operator_api import agent_invocation_reader as air
    from observability.operator_api import agent_schedule as sch
    t, s = air.TARGETS["market-observer"], ag.spec("market-observer")
    assert t["runner_id"] == s.runner_id and str(air.MARKET_REPORTS_PATH) == s.storage_dir
    assert t["mission_id"] == MISSION["mission_id"]
    assert t["profile_blob_sha1"] == MISSION["profile"]["blob_sha1"] == git(REPO, "hash-object", s.profile_path)
    assert "market-observer" in sch.SCHEDULABLE
