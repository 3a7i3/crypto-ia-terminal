"""Cartographie statique d'une zone (repository-cartographer) — banc isolé.

FIXTURE_ONLY · NOT_REGISTRY_DATA · NOT_OPERATOR_DATA · NOT_DEPLOYED.
Les quatre premiers tests sont ceux du prototype reçu, inchangés hormis l'import.
"""
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from agent_bench.observation import bench
from agent_bench.observation import contract as c
from agent_bench.observation import repository_cartographer as rc
from agent_bench.observation.repository_cartographer import map_repository


class RepositoryCartographerTest(unittest.TestCase):
    def test_import_does_not_create_call(self):
        result = map_repository(
            {"main.py": b"from worker import run"},
            frozenset({"main.py"}),
        )
        self.assertEqual([fact["relation"] for fact in result["facts"]], ["IMPORTS"])

    def test_fallback_reports_both_expressions(self):
        result = map_repository(
            {"main.py": b"try:\n    primary.run()\nexcept ValueError:\n    fallback.run()"},
            frozenset({"main.py"}),
        )
        self.assertEqual(
            [(fact["target"], fact["line"]) for fact in result["facts"]],
            [("primary.run", 2), ("fallback.run", 4)],
        )

    def test_replay_and_parse_error(self):
        sources = {"broken.py": b"def ?", "worker.py": b"def run(): pass"}
        allowed = frozenset(sources)
        result = map_repository(sources, allowed)
        self.assertEqual(
            result,
            map_repository(dict(reversed(list(sources.items()))), allowed),
        )
        self.assertEqual(
            result["unknowns"],
            [{"path": "broken.py", "reason": "PARSE_FAILED"}],
        )

    def test_scope(self):
        for path in ("../outside.py", "/absolute.py", "secrets/test.py"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "SOURCE_OUT_OF_SCOPE"):
                    map_repository({path: b"run()"}, frozenset({path}))


# --------------------------------------------------------------------------- critères

def _case(case_id):
    return next(c_ for c_ in rc.CASES if c_["id"] == case_id)


def test_matrix_all_cases_pass():
    rows = rc.cartographer_matrix()
    failed = [r["id"] for r in rows if not r["passed"]]
    assert failed == []
    assert len(rows) == 10


def test_import_never_becomes_call_or_activity():
    content = rc.analyse(_case("CARTO_1_import_seul")["sources"])
    assert content["calls"] == []
    assert content["activity"]["production_calls"] == 0
    assert [i["status"] for i in content["imports"]] == ["IMPORT_ONLY"]


def test_test_only_import_and_call_are_not_production_activity():
    content = rc.analyse(_case("CARTO_2_test_seul")["sources"])
    assert content["activity"]["production_calls"] == 0
    assert [call["status"] for call in content["calls"]] == ["TEST_CALL"]


def test_test_helper_imported_by_production_is_not_activity():
    content = rc.analyse(_case("CARTO_3_import_test_en_production")["sources"])
    assert content["activity"]["production_calls"] == 0
    assert [call["status"] for call in content["calls"]] == ["TEST_SCOPE_CALL"]
    assert [i["status"] for i in content["imports"]] == ["IMPORT_TEST_SCOPE"]


def test_fallback_call_is_conditional():
    content = rc.analyse(_case("CARTO_4_fallback_conditionnel")["sources"])
    by_target = {call["target"]: call for call in content["calls"]}
    assert by_target["primary.run"]["status"] == "PRODUCTION_CALL"
    assert by_target["fallback.run"]["status"] == "CONDITIONAL_PRODUCTION_CALL"
    assert by_target["fallback.run"]["condition"] == "EXCEPT_HANDLER"


def test_dynamic_target_is_inconclusive_and_is_no_call():
    content = rc.analyse(_case("CARTO_5_cible_dynamique")["sources"])
    assert content["calls"] == []
    assert [u["reason"] for u in content["unknowns"]] == ["DYNAMIC_CALL_TARGET"]
    assert all(u["level"] == "INCONCLUSIVE" for u in content["unknowns"])
    assert content["status"] == "PARTIAL"


def test_two_producer_candidates_cite_each_reference():
    sources = _case("CARTO_6_deux_producteurs")["sources"]
    content = rc.analyse(sources)
    (finding,) = [f for f in content["findings"] if f["code"] == "MULTIPLE_PRODUCER_CANDIDATES"]
    refs = {(e["path"], e["symbol"]) for e in finding["evidence"]}
    assert refs == {("export_a.py", "dump"), ("export_b.py", "dump_again")}
    for e in finding["evidence"]:
        assert e["line"] >= 1 and e["sha256"] == __import__("hashlib").sha256(sources[e["path"]]).hexdigest()


def test_flag_read_on_one_path_is_attributed_to_that_path():
    content = rc.analyse(_case("CARTO_7_flag_un_chemin")["sources"])
    (finding,) = [f for f in content["findings"] if f["code"] == "FLAG_SINGLE_PATH"]
    assert finding["attributed_to"] == {"path": "cfg.py", "symbol": "load"}
    assert finding["level"] == "SUPPORTED"


def test_flag_read_on_two_paths_is_not_attributed():
    content = rc.analyse(_case("CARTO_8_flag_deux_chemins")["sources"])
    codes = [f["code"] for f in content["findings"]]
    assert "FLAG_MULTI_PATH" in codes and "FLAG_SINGLE_PATH" not in codes


def test_every_constat_cites_file_line_and_source_hash():
    import hashlib
    for case in rc.CASES:
        if "sources" not in case or "error" in case["expected"]:
            continue
        content = rc.analyse(case["sources"])
        digests = {s["path"]: s["sha256"] for s in content["sources"]}
        for f in content["findings"]:
            for e in f["evidence"]:
                assert e["path"] in digests and e["line"] >= 1, (case["id"], f["code"])
                assert e["sha256"] == digests[e["path"]] == hashlib.sha256(case["sources"][e["path"]]).hexdigest()


def test_same_sources_same_report_regardless_of_order():
    sources = _case("CARTO_6_deux_producteurs")["sources"]
    a = rc.analyse(sources)
    b = rc.analyse(dict(reversed(list(sources.items()))))
    assert a == b
    assert c.sha256_json(a) == c.sha256_json(b)


def test_budget_of_thirty_files():
    ok = {f"m{i:02d}.py": b"x = 1\n" for i in range(30)}
    assert rc.analyse(ok)["status"] == "COMPLETE"
    with pytest.raises(ValueError, match="FILE_BUDGET_EXCEEDED"):
        rc.analyse({f"m{i:02d}.py": b"x = 1\n" for i in range(31)})


def test_mission_budget_above_thirty_is_refused():
    m = bench.finalize(json.loads(bench.ZONE_MISSION.read_text()))
    m["budget"]["max_files"] = 31
    m = bench.finalize(m)
    with pytest.raises(c.MissionRejected) as exc:
        c.validate_mission(m)
    assert exc.value.code == "FILE_BUDGET_EXCEEDED"


def test_dataset_question_is_refused_for_repository_cartographer():
    m = json.loads(bench.ZONE_MISSION.read_text())
    m["agent_id"] = "repository-cartographer"
    m["question"] = {"kind": "DATASET_PROVENANCE_CHAIN"}
    m = bench.finalize(m)
    with pytest.raises(c.MissionRejected) as exc:
        c.validate_mission(m)
    assert exc.value.code == "MISSION_SCHEMA_VIOLATION"


def test_zone_run_reads_only_scope_and_refuses_secrets_and_links():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "ws"
        (ws / "zone").mkdir(parents=True)
        (ws / "zone" / "ok.py").write_text("def run():\n    pass\n")
        (ws / "zone" / ".env").write_text("TOKEN=fixture\n")
        (ws / "zone" / "secrets").mkdir()
        (ws / "zone" / "secrets" / "x.py").write_text("y = 1\n")
        (ws / "zone" / "link.py").symlink_to(ws / "zone" / "ok.py")
        m = {"contract": c.MISSION_CONTRACT, "agent_id": "repository-cartographer",
             "profile": {"source_path": ".github/agents/repository-cartographer.agent.md",
                         "blob_sha1": "dd414cad0c9b73c5106d6593dd603966db14ec83"},
             "mission_id": "", "analyzed_ref": {"kind": "FIXTURE_TREE", "sha": "0" * 64},
             "scope": {"read_paths": ["zone/"]},
             "question": {"kind": "REPOSITORY_MAP", "zone_id": "zone-test", "text": "Cartographier la zone de test fixture."},
             "budget": {"max_files": 30, "max_bytes": 100000, "max_wall_ms": 20000},
             "capture": None}
        m = bench.finalize(m)
        report = rc.audit_zone(m, ws, bench.REPO)
        ct = report["content"]
        assert ct["status"] == "COMPLETE"
        assert [s["path"] for s in ct["sources"] if s["path"].startswith("zone/")] == ["zone/ok.py"]
        refused = {r["path"]: r["code"] for r in ct["refused_paths"]}
        assert refused.get("zone/.env") == "SKIPPED_SECRET_PATTERN"
        assert refused.get("zone/secrets/x.py") == "SKIPPED_SECRET_PATTERN"
        assert refused.get("zone/link.py") == "SKIPPED_SYMLINK"


def test_zone_report_is_reproducible_at_same_scope():
    m = bench.finalize(json.loads(bench.ZONE_MISSION.read_text()))
    clocks = iter([1, 2, 3, 4])
    a = rc.audit_zone(m, bench.REPO, bench.REPO, clock=lambda: next(clocks))
    b = rc.audit_zone(m, bench.REPO, bench.REPO, clock=lambda: next(clocks))
    assert a["content_sha256"] == b["content_sha256"]
    assert a["run"] != b["run"]


def test_repository_cartographer_profile_is_qualified_only_by_blob():
    mission = json.loads(bench.ZONE_MISSION.read_text())
    assert mission["profile"]["blob_sha1"] == c.git_blob_sha1(
        (bench.REPO / mission["profile"]["source_path"]).read_bytes())
    registry = (bench.REPO / "frontend/src/agents/agentIdentityRegistry.v1.json").read_text()
    assert mission["profile"]["blob_sha1"] in registry
    assert '"wiring_status": "NOT_WIRED"' in registry or '"wiring_status":"NOT_WIRED"' in registry


def test_zone_summary_is_reproduced_at_the_recorded_scope():
    summary = json.loads((bench.REPO / "docs/agents/observation/examples/cartographer_zone_summary.json").read_text())
    import hashlib
    for src in summary["sources"]:
        if src["path"].startswith("profile:"):
            continue
        if hashlib.sha256((bench.REPO / src["path"]).read_bytes()).hexdigest() != src["sha256"]:
            pytest.skip(f"{src['path']} changed since the recorded SHA; rerun under a new mission")
    m = bench.finalize(json.loads(bench.ZONE_MISSION.read_text()))
    report = rc.audit_zone(m, bench.REPO, bench.REPO)
    assert report["content"]["mission_id"] == summary["mission_id"]
    assert report["content_sha256"] == summary["content_sha256"]
    assert report["content"]["activity"] == summary["activity"]
