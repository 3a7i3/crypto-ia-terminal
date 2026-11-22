"""Banc isolé du pilote Observation (data-provenance-auditor).

FIXTURE_ONLY · NOT_REGISTRY_DATA · NOT_OPERATOR_DATA · NOT_DEPLOYED.
Aucun réseau, aucun VPS, aucune API de marché. Un test qui passe ne qualifie
aucun runner et n'allume aucun voyant de Système.
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

import pytest

from agent_bench.observation import bench
from agent_bench.observation import contract as c
from agent_bench.observation.provenance_auditor import audit

CASES = bench.cases()
CASE_IDS = [p.name for p in CASES]
REPO = bench.REPO

# --- garde d'accès : un hook d'audit Python enregistre chaque ouverture et connexion.
_AUDIT = {"on": False, "opens": [], "sockets": []}


def _hook(event, args):
    if not _AUDIT["on"]:
        return
    if event == "open" and args and isinstance(args[0], (str, bytes, Path)):
        _AUDIT["opens"].append(str(args[0]))
    elif event.startswith("socket."):
        _AUDIT["sockets"].append(event)


sys.addaudithook(_hook)


def _guarded_audit(mission, ws, **kw):
    _AUDIT.update(on=True, opens=[], sockets=[])
    try:
        return audit(mission, ws, REPO, **kw)
    finally:
        _AUDIT["on"] = False


def test_nine_required_cases_are_present():
    letters = sorted({name[0] for name in CASE_IDS})
    assert letters == list("ABCDEFGHI")
    for case in CASES:
        expected = json.loads((case / "expected.json").read_text())
        assert {"title", "status", "expected_summary"} <= set(expected)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_case_matches_predefined_expectation(case):
    expected = json.loads((case / "expected.json").read_text())
    report = bench.run_case(case)
    verdict = bench.compare(report, expected)
    assert verdict["mismatches"] == []
    assert verdict["false_findings"] == []
    assert verdict["unjustified_findings"] == []


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_two_runs_same_content_hash_time_separated(case):
    clocks = iter([1_700_000_000_000_000_000, 1_700_000_000_500_000_000,
                   1_800_000_000_000_000_000, 1_800_000_009_000_000_000])
    r1 = bench.run_case(case, clock=lambda: next(clocks))
    r2 = bench.run_case(case, clock=lambda: next(clocks))
    assert r1["content"] == r2["content"]
    assert r1["content_sha256"] == r2["content_sha256"] == c.sha256_json(r1["content"])
    assert r1["run"]["started_utc"] != r2["run"]["started_utc"]
    assert r1["report_sha256"] != r2["report_sha256"]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_reads_only_scope_no_network_no_write(case):
    with tempfile.TemporaryDirectory() as tmp:
        mission, ws = bench.prepare_case(case, tmp)
        before = {p: p.read_bytes() for p in ws.rglob("*") if p.is_file()}
        report = _guarded_audit(mission, ws)
        after = {p: p.read_bytes() for p in ws.rglob("*") if p.is_file()}
        assert before == after, "the auditor must not write"
        assert _AUDIT["sockets"] == []
        profile = str(REPO / mission["profile"]["source_path"])
        allowed_prefixes = [str(Path(ws).resolve() / p) + ("/" if p.endswith("/") else "")
                            for p in mission["scope"]["read_paths"]]
        for opened in _AUDIT["opens"]:
            if opened == profile:
                continue
            if opened.startswith((sys.prefix, sys.base_prefix)) or "/site-packages/" in opened:
                continue  # imports paresseux de la bibliothèque standard
            resolved = str(Path(opened).resolve())
            assert any(resolved == a.rstrip("/") or (a.endswith("/") and resolved.startswith(a)) for a in allowed_prefixes), \
                f"opened outside scope: {opened}"
        dumped = json.dumps(report, ensure_ascii=False)
        assert "not-a-secret" not in dumped


def test_secret_in_scope_is_blocked_before_any_read():
    case = next(p for p in CASES if p.name.startswith("H1"))
    with tempfile.TemporaryDirectory() as tmp:
        mission, ws = bench.prepare_case(case, tmp)
        report = _guarded_audit(mission, ws)
    ct = report["content"]
    assert ct["status"] == "BLOCKED"
    assert ct["sources_consulted"] == []
    assert not [o for o in _AUDIT["opens"] if o.endswith(".env")]


def _mission(case_prefix="A"):
    case = next(p for p in CASES if p.name.startswith(case_prefix))
    return case, json.loads((case / "mission.json").read_text())


def _run_mutated(mutate, refresh_id=True):
    case, mission = _mission()
    mission = copy.deepcopy(mission)
    mutate(mission)
    if refresh_id:
        mission = bench.finalize(mission)
    with tempfile.TemporaryDirectory() as tmp:
        _, ws = bench.prepare_case(case, tmp)
        return audit(mission, ws, REPO)["content"]


@pytest.mark.parametrize("mutate,code,refresh", [
    (lambda m: m.update(agent_id="repository-cartographer"), "AGENT_NOT_QUALIFIED_FOR_BENCH", True),
    (lambda m: m.update(agent_id="sniper-engine"), "AGENT_UNKNOWN", True),
    (lambda m: m["question"].update(text="Une autre question ici, sans recalcul d'identité."), "MISSION_ID_MISMATCH", False),
    (lambda m: m["profile"].update(blob_sha1="0" * 40), "PROFILE_VERSION_MISMATCH", True),
    (lambda m: m["capture"].update(sha256="0" * 64), "CAPTURE_FINGERPRINT_MISMATCH", True),
    (lambda m: m["scope"].update(read_paths=["web/", "api/"]), "SCOPE_ARRAY_NOT_CANONICAL", True),
    (lambda m: m["scope"].update(read_paths=sorted(m["scope"]["read_paths"] + ["../outside/"])), "SCOPE_PATH_INVALID", True),
    (lambda m: m["scope"].update(read_paths=["/etc/"]), "SCOPE_PATH_INVALID", True),
    (lambda m: m["scope"].update(read_paths=["api/**"]), "SCOPE_PATH_INVALID", True),
    (lambda m: m["scope"].update(read_paths=["keys/id_rsa"]), "SECRET_PATH_REQUESTED", True),
    (lambda m: m["scope"].update(read_paths=["config/secrets/"]), "SECRET_PATH_REQUESTED", True),
    (lambda m: m["capture"].update(path="other/history.json"), "CAPTURE_OUT_OF_SCOPE", True),
    (lambda m: m.update(extra_field=True), "MISSION_SCHEMA_VIOLATION", False),
])
def test_rejected_missions_are_blocked(mutate, code, refresh):
    ct = _run_mutated(mutate, refresh)
    assert ct["status"] == "BLOCKED"
    assert [e["code"] for e in ct["errors"]] == [code]
    assert ct["findings"] == [] and ct["chain"] == []


def test_budget_exhaustion_is_failed_not_complete():
    ct = _run_mutated(lambda m: m["budget"].update(max_files=1))
    assert ct["status"] == "FAILED"
    assert any(e["code"] == "BUDGET_EXCEEDED" for e in ct["errors"])


def test_partial_failure_keeps_proven_links_and_never_marks_unknown_healthy():
    case = next(p for p in CASES if p.name.startswith("G"))
    ct = bench.run_case(case)["content"]
    assert ct["status"] == "PARTIAL"
    assert all(h["level"] == "PROVEN" for h in ct["chain"])
    assert ct["freshness"]["verdict"] == "INCONCLUSIVE"
    assert not any(f["code"].startswith("SOURCE_WITHIN") for f in ct["findings"])


def test_stale_source_not_masked_by_recent_mtime():
    case = next(p for p in CASES if p.name.startswith("D"))
    f = bench.run_case(case)["content"]["freshness"]
    assert f["verdict"] == "SOURCE_STALE"
    assert f["mtime_age_ms"] <= f["max_source_age_ms"] < f["source_age_ms"]
    assert f["mtime_used_as_evidence"] is False and f["effective_source"] == "source_event_ts"


def test_every_finding_has_locatable_evidence():
    for case in CASES:
        for f in bench.run_case(case)["content"]["findings"]:
            assert f["evidence"] and f["level"] in c.PROOF_LEVELS and f["confidence"] in c.CONFIDENCE
            for e in f["evidence"]:
                assert e["evidence_type"] in c.EVIDENCE_TYPES
                if e["path"]:
                    assert c.HEX64.match(e.get("file_sha256", "")), (case.name, f["code"], e)


def test_report_never_self_certifies():
    for case in CASES:
        ct = bench.run_case(case)["content"]
        dumped = json.dumps(ct)
        assert "CERTIFIED" not in dumped and '"valid"' not in dumped and '"PASS"' not in dumped
        assert "REPORT_IS_NOT_SELF_CERTIFYING" in ct["limits"]


def test_fixtures_are_frozen():
    for case in CASES:
        m = json.loads((case / "mission.json").read_text())
        assert m["analyzed_ref"]["sha"] == bench.tree_sha256(case / "workspace")
        assert m["mission_id"] == c.compute_mission_id(m)


def test_example_mission_is_valid_and_pilot_matches_committed_report():
    mission = json.loads(bench.PILOT_MISSION.read_text())
    c.validate_mission(mission)
    committed = json.loads((bench.PILOT_MISSION.parent / "pilot_report.json").read_text())
    recorded = {s["path"]: s["sha256"] for s in committed["content"]["sources_consulted"]}
    import hashlib
    for path in mission["scope"]["read_paths"]:
        if hashlib.sha256((REPO / path).read_bytes()).hexdigest() != recorded.get(path):
            pytest.skip(f"{path} changed since the pilot SHA; rerun the pilot under a new mission")
    report = audit(mission, REPO, REPO)

    def without_mtime(content):
        # mtime d'un checkout git = heure du checkout : fait du système de fichiers, pas du dépôt.
        out = copy.deepcopy(content)
        out["freshness"].pop("mtime")
        out["freshness"].pop("mtime_age_ms")
        return out
    assert without_mtime(report["content"]) == without_mtime(committed["content"])
    hops = {h["hop"]: h["level"] for h in report["content"]["chain"]}
    assert hops.pop("STORAGE_TO_READER") == "INFERRED"
    assert set(hops.values()) == {"PROVEN"}
    assert report["content"]["status"] == "PARTIAL"


def test_access_guard_detects_an_outside_open():
    """Contrôle du contrôle : le hook voit bien une ouverture hors périmètre."""
    with tempfile.TemporaryDirectory() as tmp:
        outside = Path(tmp) / "outside.txt"
        outside.write_text("x")
        _AUDIT.update(on=True, opens=[], sockets=[])
        try:
            outside.read_text()
        finally:
            _AUDIT["on"] = False
        assert str(outside) in _AUDIT["opens"]
