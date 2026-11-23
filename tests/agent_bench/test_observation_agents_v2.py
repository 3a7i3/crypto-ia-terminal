"""Agents d'observation restants : banc v2, exécuteur commun et dossier de stockage par agent.

Attendus écrits avant l'exécution :

| Cas | Résultat exigé |
|---|---|
| Matrices OBS_1–8 et ARCH_1–7 | attendu = obtenu, cas par cas |
| Type v2 sous contrat v1 (ou inverse) | MISSION_SCHEMA_VIOLATION |
| Surface hors périmètre | SURFACE_OUT_OF_SCOPE |
| Carte du cartographe d'un autre SHA que la base | UPSTREAM_MAP_SHA_MISMATCH |
| Diff dont l'empreinte diffère de la mission | refus avant verrou, rien de publié |
| DPA, observability-cartographer, repo-architect par l'exécuteur | une enveloppe VALID dans le dossier de l'agent |
| Agent par défaut de l'exécuteur | repository-cartographer (unité installée inchangée) |
| Résumé de stockage : dossier absent / vide / > 200 entrées | jamais des zéros sur panne ; refus explicite |
| repo-architect suivi de main | refusé (mission à la demande) |
"""
import copy
import json
import shutil
import time
from pathlib import Path

import pytest
from invocation_bench import git

from agent_bench.observation import agents as ag
from agent_bench.observation import change_mission as cm
from agent_bench.observation import contract as c
from agent_bench.observation import executor as ex
from agent_bench.observation import follow_main as fm
from agent_bench.observation import invocation as inv
from agent_bench.observation import observability_cartographer as oc
from agent_bench.observation import repo_architect as ra

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "docs" / "agents" / "observation" / "examples"
CODE = ["agent_bench/__init__.py"] + [f"agent_bench/observation/{p.name}"
                                      for p in sorted((REPO / "agent_bench/observation").glob("*.py"))]


# --------------------------------------------------------------------------- matrices

@pytest.mark.parametrize("row", oc.matrix(), ids=lambda r: r["id"])
def test_observability_matrix(row):
    assert row["passed"], row


@pytest.mark.parametrize("row", ra.matrix(), ids=lambda r: r["id"])
def test_architect_matrix(row):
    assert row["passed"], row


# --------------------------------------------------------------------------- contrat v2

def _surface_mission():
    return json.loads((EXAMPLES / "observability_surface_mission.json").read_text(encoding="utf-8"))


def _refresh(m):
    m["mission_id"] = c.compute_mission_id(m)
    return m


def _rejected(m):
    with pytest.raises(c.MissionRejected) as exc:
        c.validate_mission(_refresh(m))
    return exc.value.code


def test_examples_are_valid_missions():
    c.validate_mission(_surface_mission())
    c.validate_mission(json.loads((EXAMPLES / "repo_architect_change_mission.json").read_text(encoding="utf-8")))


def test_v2_kind_requires_v2_contract_and_v1_kinds_stay_v1():
    m = _surface_mission()
    m["contract"] = c.MISSION_CONTRACT
    assert _rejected(m) == "MISSION_SCHEMA_VIOLATION"
    zone = json.loads((EXAMPLES / "cartographer_zone_mission.json").read_text(encoding="utf-8"))
    zone["contract"] = c.MISSION_CONTRACT_V2
    assert _rejected(zone) == "MISSION_SCHEMA_VIOLATION"


def test_surface_must_be_in_scope():
    m = _surface_mission()
    m["question"]["surface_path"] = "frontend/src/views/Other.tsx"
    assert _rejected(m) == "SURFACE_OUT_OF_SCOPE"


def test_upstream_map_must_describe_the_base():
    m = json.loads((EXAMPLES / "repo_architect_change_mission.json").read_text(encoding="utf-8"))
    m["question"]["upstream_map"] = {"agent_id": "repository-cartographer", "content_sha256": "a" * 64,
                                     "analysed_sha": "b" * 40, "mapped_paths": ["agent_bench/"]}
    assert _rejected(m) == "UPSTREAM_MAP_SHA_MISMATCH"
    m["question"]["upstream_map"]["agent_id"] = "data-provenance-auditor"
    m["question"]["upstream_map"]["analysed_sha"] = m["question"]["base_sha"]
    assert _rejected(m) == "MISSION_SCHEMA_VIOLATION"


def test_change_scope_equals_changed_paths():
    m = json.loads((EXAMPLES / "repo_architect_change_mission.json").read_text(encoding="utf-8"))
    m["scope"]["read_paths"] = sorted(m["scope"]["read_paths"] + ["zzz/other.py"])
    assert _rejected(m) == "MISSION_SCHEMA_VIOLATION"


def test_surface_report_on_the_real_storage_view_is_sealed_and_cites_sources():
    rep = oc.audit_surface(_surface_mission(), REPO, REPO)
    ct = rep["content"]
    assert ct["status"] in ("COMPLETE", "PARTIAL") and ct["errors"] == []
    assert rep["content_sha256"] == c.sha256_json(ct)
    assert ct["sources"][0]["path"] == "profile:.github/agents/observability-cartographer.agent.md"
    assert any(e["endpoint"] == "/api/operator/v1/storage" and e["route"] for e in ct["endpoints"])
    assert "REPORT_IS_NOT_SELF_CERTIFYING" in ct["limits"]


def test_architect_never_says_safe_without_map():
    rows = {r["id"]: r for r in ra.matrix()}
    assert rows["ARCH_5_sans_carte"]["obtained"]["status"] == "PARTIAL"
    assert rows["ARCH_4_hors_zone"]["obtained"]["status"] == "PARTIAL"


# --------------------------------------------------------------------------- exécuteur, vrais dépôts git

class Repo:
    def __init__(self, root: Path, files: dict):
        self.root, self.checkout, self.reports = root, root / "checkout", root / "reports"
        for rel in CODE + [s.profile_path for s in ag.AGENTS.values()]:
            dst = self.checkout / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, dst)
        self.write(files)
        git(self.checkout, "init", "-q", "-b", "main")
        self.base = self.commit("base")
        self.reports.mkdir()

    def write(self, files):
        for rel, data in files.items():
            dst = self.checkout / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, Path):
                shutil.copy(data, dst)
            else:
                dst.write_bytes(data)

    def commit(self, msg):
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", msg)
        return git(self.checkout, "rev-parse", "HEAD")

    def run(self, mission, agent_id, sha):
        return ex.run_once(mission=mission, checkout=self.checkout, reports=self.reports,
                           runner_id=ag.spec(agent_id).runner_id, agent_id=agent_id, code_sha=sha, analysed_sha=sha)


def _valid(env, agent_id):
    return inv.validate_envelope(env, agent_id=agent_id, runner_id=ag.spec(agent_id).runner_id,
                                 mission_id=env["mission_id"], now_ts=time.time() + 5,
                                 expected_profile_blob=env["profile_blob_sha1"])


def test_executor_runs_the_data_provenance_auditor(tmp_path):
    pilot = json.loads((EXAMPLES / "pilot_mission.json").read_text(encoding="utf-8"))
    r = Repo(tmp_path, {p: REPO / p for p in pilot["scope"]["read_paths"]})
    m = copy.deepcopy(pilot)
    m["analyzed_ref"] = {"kind": "GIT_COMMIT", "sha": r.base}
    _refresh(m)
    env, name = r.run(m, "data-provenance-auditor", r.base)
    assert env["state"] == "COMPLETED" and env["result_status"] in ("COMPLETE", "PARTIAL")
    assert _valid(env, "data-provenance-auditor") == ("VALID", "ok")
    assert (r.reports / "runs" / m["mission_id"] / name).is_file()


def test_executor_runs_the_observability_cartographer(tmp_path):
    files = {"web/Panel.tsx": b'const U = "/api/v1/panel";\nexport function P({d}) { return <b>{d.win_rate_pct ?? 0}</b>; }\n',
             "api/app.py": b'@app.get("/api/v1/panel")\ndef panel():\n    return {"win_rate_pct": 1}\n'}
    r = Repo(tmp_path, files)
    s = ag.spec("observability-cartographer")
    m = _refresh({"contract": c.MISSION_CONTRACT_V2, "agent_id": s.agent_id,
                  "profile": {"source_path": s.profile_path,
                              "blob_sha1": c.git_blob_sha1((REPO / s.profile_path).read_bytes())},
                  "mission_id": None, "analyzed_ref": {"kind": "GIT_COMMIT", "sha": r.base},
                  "scope": {"read_paths": ["api/app.py", "web/Panel.tsx"]},
                  "question": {"kind": "METRIC_SURFACE_MAP", "surface_id": "panel", "surface_path": "web/Panel.tsx",
                               "text": "Que mesure la vue Panel et d'où vient chaque chiffre ?", "upstream_reports": []},
                  "budget": {"max_files": 2, "max_bytes": 100000, "max_wall_ms": 10000}, "capture": None})
    env, _ = r.run(m, s.agent_id, r.base)
    assert _valid(env, s.agent_id) == ("VALID", "ok")
    ct = env["report"]["content"]
    assert [x["classification"] for x in ct["metrics"]] == ["CANONICAL_EXISTING"]
    assert {f["code"] for f in ct["findings"]} == {"NULL_ZERO_AMBIGUITY"}


def _change_repo(tmp_path):
    r = Repo(tmp_path, {"risk/limits.py": b"MAX_DRAWDOWN_THRESHOLD = 0.1\n", "api/old.py": b"x = 1\n"})
    r.write({"risk/limits.py": b"MAX_DRAWDOWN_THRESHOLD = 0.2\n"})
    (r.checkout / "api/old.py").unlink()
    head = r.commit("change")
    return r, head


def test_executor_runs_the_repo_architect_on_a_real_diff(tmp_path):
    r, head = _change_repo(tmp_path)
    m = cm.build(r.checkout, base=r.base, head=head, change_id="seuil",
                 text="Ce changement touche-t-il un seuil gelé ou une autorité ?")
    assert m["question"]["changed_paths"] == ["api/old.py", "risk/limits.py"]
    env, _ = r.run(m, "repo-architect", head)
    assert _valid(env, "repo-architect") == ("VALID", "ok")
    ct = env["report"]["content"]
    assert ct["boundaries_crossed"] == ["FROZEN_OBJECT_TOUCHED"]
    assert ct["status"] == "PARTIAL"  # sans carte : jamais « sans risque »
    assert {u["reason"] for u in ct["unknowns"]} == {"REPOSITORY_MAP_NOT_PROVIDED"}


def test_executor_refuses_a_diff_that_does_not_match_the_mission(tmp_path):
    r, head = _change_repo(tmp_path)
    m = cm.build(r.checkout, base=r.base, head=head, change_id="seuil",
                 text="Ce changement touche-t-il un seuil gelé ou une autorité ?")
    m["question"]["diff_sha256"] = "0" * 64
    _refresh(m)
    with pytest.raises(ex.Refused) as exc:
        r.run(m, "repo-architect", head)
    assert exc.value.code == "DIFF_FINGERPRINT_MISMATCH"
    assert not (r.reports / "runs").exists()


def test_executor_default_agent_stays_the_cartographer(tmp_path):
    r, head = _change_repo(tmp_path)
    m = cm.build(r.checkout, base=r.base, head=head, change_id="seuil",
                 text="Ce changement touche-t-il un seuil gelé ou une autorité ?")
    with pytest.raises(ex.Refused) as exc:
        ex.run_once(mission=m, checkout=r.checkout, reports=r.reports, runner_id="obs-repo-architect-ro-01",
                    code_sha=head, analysed_sha=head)
    assert exc.value.code == "AGENT_NOT_QUALIFIED"


# --------------------------------------------------------------------------- dossier de stockage

def test_every_agent_has_its_own_storage_dir_and_manifest():
    dirs = [s.storage_dir for s in ag.AGENTS.values()]
    assert len(set(dirs)) == len(ag.AGENTS) == 5
    assert ag.spec("repository-cartographer").storage_dir == "/srv/cat-obs/reports"
    for aid in ag.AGENTS:
        mf = ag.manifest(aid)
        assert mf["git_policy"] == "NEVER" and mf["retention"] == {"kind": "KEEP_LAST", "n": 20, "archive": "NONE"}
        assert mf["question_kind"] == c.QUESTION_KIND_BY_AGENT.get(aid, "MARKET_RUNTIME_OBSERVATION")
    assert {s.runner_id for s in ag.AGENTS.values()} == {
        "obs-repo-cartographer-ro-01", "obs-data-provenance-ro-01", "obs-observability-ro-01", "obs-repo-architect-ro-01",
        "obs-market-ro-01"}


def test_summary_never_turns_a_read_failure_into_zeros(tmp_path):
    s = ag.summary("repo-architect", tmp_path / "absent", now_ts=0)
    assert s["readable"] is False and s["reason"] == "DOSSIER_ABSENT" and s["envelopes"] is None
    (tmp_path / "vide").mkdir()
    s = ag.summary("repo-architect", tmp_path / "vide", now_ts=0)
    assert s["readable"] is True and s["reason"] == "AUCUN_PASSAGE" and s["envelopes"] == 0


def test_summary_counts_published_envelopes(tmp_path):
    r, head = _change_repo(tmp_path)
    m = cm.build(r.checkout, base=r.base, head=head, change_id="seuil",
                 text="Ce changement touche-t-il un seuil gelé ou une autorité ?")
    _env, name = r.run(m, "repo-architect", head)
    s = ag.summary("repo-architect", r.reports)
    assert s["readable"] and s["missions"] == 1 and s["envelopes"] == 1 and s["bytes"] > 0
    assert s["latest"]["file"] == name and s["latest"]["state"] == "COMPLETED"
    assert s["latest"]["result_status"] == "PARTIAL"


def test_summary_refuses_an_overflowing_directory(tmp_path):
    runs = tmp_path / "runs"
    for i in range(inv.MAX_DIR_ENTRIES + 1):
        (runs / f"{i:064x}").mkdir(parents=True)
    s = ag.summary("data-provenance-auditor", tmp_path)
    assert s["readable"] is False and s["reason"] == "REPORTS_DIR_OVERFLOW" and s["envelopes"] is None


def test_summary_does_not_follow_symlinks(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    s = ag.summary("data-provenance-auditor", tmp_path / "link")
    assert s["readable"] is False and s["reason"].startswith("ILLISIBLE")


def test_cli_manifest_writes_into_the_agent_dir(tmp_path, capsys):
    assert ag.main(["manifest", "--agent", "observability-cartographer", "--root", str(tmp_path), "--write"]) == 0
    doc = json.loads((tmp_path / "MANIFEST.json").read_text(encoding="utf-8"))
    assert doc["agent_id"] == "observability-cartographer" and doc["contract"] == ag.STORAGE_CONTRACT


# --------------------------------------------------------------------------- suivi de main

def test_follow_main_pointer_is_per_agent(tmp_path):
    pilot = json.loads((EXAMPLES / "pilot_mission.json").read_text(encoding="utf-8"))
    m = fm.publish(pilot, "c" * 40, tmp_path)
    assert (tmp_path / "data-provenance-auditor.mission").read_text().strip() == m["mission_id"]
    assert not (tmp_path / fm.POINTER).exists()


def test_follow_main_refuses_change_impact():
    m = json.loads((EXAMPLES / "repo_architect_change_mission.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="KIND_NOT_FOLLOWABLE"):
        fm.derive_mission(m, "c" * 40)


# --------------------------------------------------------------------------- bloc Système du DPA (API)

def test_dpa_api_target_matches_registry_and_profile():
    from observability.operator_api import agent_invocation_reader as air
    t, s = air.TARGETS["data-provenance-auditor"], ag.spec("data-provenance-auditor")
    assert t["runner_id"] == s.runner_id
    assert str(air.DPA_REPORTS_PATH) == s.storage_dir
    assert t["profile_blob_sha1"] == git(REPO, "hash-object", s.profile_path)
    assert air._paths("data-provenance-auditor") == (air.DPA_REPORTS_PATH, air.DPA_REPORTS_PATH / "mission")


def test_dpa_api_reads_its_own_folder_pointer_and_chain(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from agent_bench.observation import follow_main as fm
    from observability.operator_api import agent_invocation_reader as air
    from observability.operator_api import app as api

    pilot = json.loads((EXAMPLES / "pilot_mission.json").read_text(encoding="utf-8"))
    r = Repo(tmp_path, {p: REPO / p for p in pilot["scope"]["read_paths"]})
    (r.reports / "mission").mkdir()
    m = fm.publish(pilot, r.base, r.reports / "mission")  # pointeur de mission courante, comme l'unité
    env, _ = r.run(m, "data-provenance-auditor", r.base)
    monkeypatch.setattr(air, "DPA_REPORTS_PATH", r.reports)
    # Le cartographe garde son dossier : rien de ce dossier ne doit lui être attribué.
    monkeypatch.setattr(air, "DEFAULT_REPORTS_PATH", tmp_path / "absent")
    c = TestClient(api.app)
    base = "/api/operator/v1/agent-invocations/data-provenance-auditor"
    st = c.get(base).json()
    assert st["mission_id"] == m["mission_id"] and st["connection"] == "AVAILABLE"
    assert st["last_result"] == env["result_status"] and st["display"]["light"] == "RED"
    assert str(r.reports) not in json.dumps(st)
    h = c.get(f"{base}/history").json()
    assert h["total"] == 1 and h["items"][0]["verdict"] == "VALID"
    ch = h["items"][0]["summary"]["chain"]
    assert ch["links"] == len(env["report"]["content"]["chain"]) and ch["hops"][0]["level"]
    assert h["items"][0]["summary"]["seen"]["sources"] == len(env["report"]["content"]["sources_consulted"])
    carto = c.get("/api/operator/v1/agent-invocations/repository-cartographer").json()
    assert carto["connection"] == "ABSENT"


def test_dpa_schedule_route_and_offset_slots(tmp_path, monkeypatch):
    import calendar

    from fastapi.testclient import TestClient

    from observability.operator_api import agent_schedule as sch
    from observability.operator_api import app as api

    monkeypatch.setattr(sch, "CONTROL_PATH", tmp_path)
    c = TestClient(api.app)
    url = "/api/operator/v1/agent-invocations/data-provenance-auditor/schedule"
    assert c.post(url, json={"rhythm": "10min"}).status_code == 403
    assert c.post(url, json={"rhythm": "10min"}, headers={"x-cat-operator": "schedule"}).status_code == 202
    assert (tmp_path / "data-provenance-auditor.rhythm").read_text() == "10min\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data-provenance-auditor.rhythm"]
    at = calendar.timegm((2026, 11, 23, 1, 12, 0, 0, 0, 0))
    (tmp_path / "data-provenance-auditor.status.json").write_text('{"applied":"10min"}')
    assert sch.read_schedule("data-provenance-auditor", control=tmp_path, now_ts=at)["next_utc"] == "2026-11-23T01:15:00Z"
    (tmp_path / "data-provenance-auditor.status.json").write_text('{"applied":"1h"}')
    assert sch.read_schedule("data-provenance-auditor", control=tmp_path, now_ts=at)["next_utc"] == "2026-11-23T01:30:00Z"
    assert c.get("/api/operator/v1/agent-invocations/repo-architect/schedule").status_code == 404
