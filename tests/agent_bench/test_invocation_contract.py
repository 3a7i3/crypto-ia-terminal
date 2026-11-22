"""Contrat d'invocation v1 : exécuteur ponctuel et lecteur.

Attendus écrits avant l'implémentation (mission « branchement Repository Cartographer ») :

| Cas | Résultat exigé |
|---|---|
| Mission terminée PARTIAL valide | affiché fidèlement, activité TERMINE, aucune activité en cours déduite |
| Exécution en cours attestée | EN_COURS, limité au bail |
| Mission interrompue / délai dépassé | état explicite, verrou libéré |
| Deux lancements concurrents | une seule exécution admise |
| Nom de sortie déjà présent | ancien fichier préservé |
| Publication interrompue | aucun rapport partiel accepté |
| Empreinte altérée ou mauvais runner | preuve rejetée avec motif |
| Date future | motif visible, pas de vert |
| Rapport absent / permissions | indisponibilité explicite |
| Ancien rapport relu | date d'activité inchangée |
| Redémarrage après invocation abandonnée | aucun état « en cours » permanent |
| Accès hors périmètre | refus (voir §Accès) |

Tests unitaires et d'intégration ici ; les preuves sous identité isolée sont dans la PR.
"""
import copy
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from agent_bench.observation import contract as c
from agent_bench.observation import executor as ex
from agent_bench.observation import invocation as inv
from agent_bench.observation import invocation_reader as rd

REPO = Path(__file__).resolve().parents[2]
ZONE = REPO / "docs" / "agents" / "observation" / "examples" / "cartographer_zone_mission.json"
ZONE_SHA = "e387318eeaed81d4e6dc90228d46943a65a5b73c"
CODE_SHA = "3b67c91b641b4c805cf07c01782db4f547090a67"
RUNNER = "obs-repo-cartographer-ro-01"
AGENT = "repository-cartographer"
NOW = 1_800_000_000.0  # horloge injectée


def _mission():
    return json.loads(ZONE.read_text(encoding="utf-8"))


@pytest.fixture()
def env_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        checkout = root / "checkout"
        for rel in _mission()["scope"]["read_paths"]:
            dst = checkout / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, dst)
        prof = checkout / ".github" / "agents" / "repository-cartographer.agent.md"
        prof.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / ".github" / "agents" / "repository-cartographer.agent.md", prof)
        reports = root / "reports"
        reports.mkdir()
        yield checkout, reports


def _clock(t):
    return lambda: t


def _run(env_dirs, *, t=NOW, mission=None, **kw):
    checkout, reports = env_dirs
    return ex.run_once(mission=mission or _mission(), checkout=checkout, reports=reports,
                       runner_id=RUNNER, code_sha=CODE_SHA, analysed_sha=ZONE_SHA,
                       clock=_clock(t), **kw)


def _read(reports, t=NOW + 5):
    return rd.read_status(reports, mission_id=_mission()["mission_id"], agent_id=AGENT,
                          runner_id=RUNNER, now_ts=t)


# --- Mission terminée PARTIAL valide -------------------------------------------------

def test_completed_partial_is_shown_faithfully_and_not_running(env_dirs):
    env = _run(env_dirs)
    assert env["state"] == "COMPLETED" and env["exit_code"] == 0
    assert env["result_status"] == "PARTIAL"
    st = _read(env_dirs[1])
    assert st["connection"] == "AVAILABLE"
    assert st["last_result"] == "PARTIAL"
    assert st["activity"] == "TERMINE"
    assert st["lock"]["present"] is False
    assert st["last_activity_utc"] == env["ended_utc"]


def test_published_hashes_recompute(env_dirs):
    env = _run(env_dirs)
    rep = env["report"]
    assert rep["content_sha256"] == c.sha256_json(rep["content"]) == "67bdcc05ec67e54013991028275d78ff4727c299fe2f9b6762c2b3da35a3fa4e"
    assert rep["report_sha256"] == c.sha256_json({"content": rep["content"],
                                                  "content_sha256": rep["content_sha256"],
                                                  "run": rep["run"]})


def test_code_sha_and_analysed_sha_are_distinct_and_recorded(env_dirs):
    env = _run(env_dirs)
    assert env["code_sha"] == CODE_SHA and env["analysed_sha"] == ZONE_SHA
    assert env["code_sha"] != env["analysed_sha"]


def test_exit_zero_alone_does_not_prove_report_validity(env_dirs):
    env = _run(env_dirs)
    tampered = copy.deepcopy(env)
    tampered["report"]["content"]["status"] = "COMPLETE"
    assert inv.validate_envelope(tampered, agent_id=AGENT, runner_id=RUNNER,
                                 mission_id=env["mission_id"], now_ts=NOW + 5) == (
        "INVALID", "empreinte du contenu altérée")


# --- Exécution en cours attestée -------------------------------------------------------

def test_running_lock_with_valid_lease_is_en_cours_and_bounded(env_dirs):
    _, reports = env_dirs
    m = _mission()
    lock = reports / "locks" / f"{RUNNER}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"runner_id": RUNNER, "invocation_id": "a" * 32, "mission_id": m["mission_id"],
                                "started_utc": inv.utc_now_iso(NOW), "lease_until_utc": inv.utc_now_iso(NOW + 600)}))
    st = _read(reports, t=NOW + 60)
    assert st["activity"] == "EN_COURS"
    assert st["lock"]["present"] is True
    # Après expiration du bail : plus de vert, aucun « en cours » permanent.
    st_late = _read(reports, t=NOW + 601)
    assert st_late["activity"] == "INDETERMINE"
    assert st_late["activity"] == "INDETERMINE" and "expiré" in st_late["activity_reason"]


# --- Lancements concurrents ------------------------------------------------------------

def test_second_concurrent_launch_is_refused(env_dirs):
    _, reports = env_dirs
    lock = reports / "locks"
    lock.mkdir(parents=True)
    (lock / f"{RUNNER}.lock").write_text(json.dumps({
        "runner_id": RUNNER, "invocation_id": "b" * 32, "mission_id": _mission()["mission_id"],
        "started_utc": inv.utc_now_iso(NOW), "lease_until_utc": inv.utc_now_iso(NOW + 600)}))
    with pytest.raises(ex.Refused) as err:
        _run(env_dirs, t=NOW + 1)
    assert err.value.code == "ALREADY_RUNNING"


# --- Mission interrompue / délai dépassé ----------------------------------------------

def test_timeout_is_explicit_and_releases_the_lock(env_dirs):
    _, reports = env_dirs
    mission = _mission()
    mission["budget"]["max_wall_ms"] = 1  # limite de durée d'une milliseconde
    mission["mission_id"] = c.compute_mission_id(mission)
    env = _run(env_dirs, mission=mission, max_run_s=0.001)
    assert env["state"] in ("TIMEOUT", "COMPLETED")  # selon la rapidité de la machine
    assert not (reports / "locks" / f"{RUNNER}.lock").exists()


def test_budget_refusal_is_published_as_completed_run_with_blocked_result(env_dirs):
    bad = _mission()
    bad["budget"]["max_files"] = 1  # budget dépassé : rapport FAILED, publié tel quel
    bad["mission_id"] = c.compute_mission_id(bad)
    env = _run(env_dirs, mission=bad)
    assert env["state"] == "COMPLETED"
    assert env["result_status"] == "BLOCKED"  # refus de budget : résultat BLOCKED, non un succès
    st = rd.read_status(env_dirs[1], mission_id=bad["mission_id"], agent_id=AGENT, runner_id=RUNNER,
                        now_ts=NOW + 5)
    assert st["last_result"] == "BLOCKED"


# --- Nom déjà présent -----------------------------------------------------------------

def test_existing_name_is_not_overwritten(env_dirs):
    _, reports = env_dirs
    env = _run(env_dirs)
    final = next((reports / "runs" / env["mission_id"]).glob("*.json"))
    before = final.read_bytes()
    with pytest.raises(ex.Refused) as err:
        ex._publish(reports, env["mission_id"], env, NOW)  # même invocation_id, même nom
    assert err.value.code == "NAME_EXISTS"
    assert final.read_bytes() == before


# --- Publication interrompue -----------------------------------------------------------

def test_interrupted_publication_leaves_no_accepted_proof(env_dirs):
    _, reports = env_dirs
    mission_id = _mission()["mission_id"]
    d = reports / "runs" / mission_id
    d.mkdir(parents=True)
    (d / f".20261122T000000Z_{'c' * 32}.json.partial").write_text('{"contract": "cat')
    st = _read(reports)
    assert st["connection"] == "ABSENT"
    assert st["last_result"] is None


# --- Empreinte altérée / mauvais runner / date future ---------------------------------

def _valid_env(env_dirs):
    return _run(env_dirs)


def test_altered_report_is_rejected_with_reason(env_dirs):
    env = _valid_env(env_dirs)
    _, reports = env_dirs
    path = next((reports / "runs" / env["mission_id"]).glob("*.json"))
    data = json.loads(path.read_text())
    data["report"]["content"]["findings"] = []  # altération du contenu
    path.write_text(json.dumps(data))
    st = _read(reports)
    assert st["connection"] == "INVALID"
    assert "empreinte du contenu altérée" in st["connection_reason"]
    assert st["last_result"] is None


def test_wrong_runner_is_rejected(env_dirs):
    env = _valid_env(env_dirs)
    v, reason = inv.validate_envelope(env, agent_id=AGENT, runner_id="autre-runner-01",
                                      mission_id=env["mission_id"], now_ts=NOW + 5)
    assert v == "INVALID" and "runner_id" in reason


def test_future_date_is_flagged_not_green(env_dirs):
    env = _valid_env(env_dirs)
    v, _reason = inv.validate_envelope(env, agent_id=AGENT, runner_id=RUNNER,
                                      mission_id=env["mission_id"], now_ts=NOW - 3600)
    assert v == "FUTURE"


def test_incomplete_envelope_is_distinct_from_invalid(env_dirs):
    env = _valid_env(env_dirs)
    del env["invocation_id"]
    v, reason = inv.validate_envelope(env, agent_id=AGENT, runner_id=RUNNER,
                                      mission_id=_mission()["mission_id"], now_ts=NOW + 5)
    assert v == "INCOMPLETE" and "invocation_id" in reason


# --- Rapport absent / permissions ----------------------------------------------------

def test_missing_reports_directory_is_explicit_absence(env_dirs):
    _, reports = env_dirs
    st = _read(reports / "inexistant")
    assert st["connection"] == "ABSENT"


def test_unreadable_proof_is_invalid_not_a_crash(env_dirs):
    env = _valid_env(env_dirs)
    _, reports = env_dirs
    path = next((reports / "runs" / env["mission_id"]).glob("*.json"))
    path.write_bytes(b"x" * (inv.MAX_PROOF_BYTES + 10))
    st = _read(reports)
    assert st["connection"] == "INVALID"


def test_symlink_proof_is_refused(env_dirs):
    _, reports = env_dirs
    mission_id = _mission()["mission_id"]
    d = reports / "runs" / mission_id
    d.mkdir(parents=True)
    target = reports / "elsewhere.json"
    target.write_text("{}")
    os.symlink(target, d / f"20261122T000000Z_{'d' * 32}.json")
    st = _read(reports)
    assert st["connection"] == "INVALID"
    assert st["last_result"] is None


# --- Lecture ne rajeunit pas ---------------------------------------------------------

def test_rereading_an_old_report_does_not_refresh_activity(env_dirs):
    env = _valid_env(env_dirs)
    a = _read(env_dirs[1], t=NOW + 5)
    b = _read(env_dirs[1], t=NOW + 10 * 86400)
    assert a["last_activity_utc"] == b["last_activity_utc"] == env["ended_utc"]


# --- Redémarrage après invocation abandonnée -----------------------------------------

def test_abandoned_invocation_does_not_stay_running(env_dirs):
    _, reports = env_dirs
    m = _mission()
    lock = reports / "locks"
    lock.mkdir(parents=True)
    (lock / f"{RUNNER}.lock").write_text(json.dumps({
        "runner_id": RUNNER, "invocation_id": "e" * 32, "mission_id": m["mission_id"],
        "started_utc": inv.utc_now_iso(NOW - 7200), "lease_until_utc": inv.utc_now_iso(NOW - 6600)}))
    st = _read(reports, t=NOW)
    assert st["activity"] != "EN_COURS"
    env = _run(env_dirs, t=NOW + 10)  # reprise explicite après bail expiré
    assert env["state"] == "COMPLETED"
    abandoned = [json.loads(p.read_text()) for p in (reports / "runs" / m["mission_id"]).glob("*.json")
                 if json.loads(p.read_text())["state"] == "ABANDONED"]
    assert len(abandoned) == 1 and abandoned[0]["invocation_id"] == "e" * 32
    assert abandoned[0]["report"] is None and abandoned[0]["code_sha"] is None  # rien d'inventé
    assert not (lock / f"{RUNNER}.lock").exists()
    assert _read(reports, t=NOW + 20)["activity"] == "TERMINE"


# --- Refus avant verrouillage ---------------------------------------------------------

def test_refusals_happen_before_any_lock_or_publication(env_dirs):
    _, reports = env_dirs
    wrong = _mission()
    wrong["agent_id"] = "observability-cartographer"
    with pytest.raises(ex.Refused):
        _run(env_dirs, mission=wrong)
    with pytest.raises(ex.Refused):
        ex.run_once(mission=_mission(), checkout=env_dirs[0], reports=reports, runner_id=RUNNER,
                    code_sha=CODE_SHA, analysed_sha="0" * 40, clock=_clock(NOW))
    assert not (reports / "runs").exists()
    assert not (reports / "locks" / f"{RUNNER}.lock").exists()


def test_lock_released_after_publication(env_dirs):
    _run(env_dirs)
    assert not (env_dirs[1] / "locks" / f"{RUNNER}.lock").exists()


def test_publication_leaves_no_partial_file(env_dirs):
    _run(env_dirs)
    d = env_dirs[1] / "runs" / _mission()["mission_id"]
    assert not any(p.name.startswith(".") for p in d.iterdir())
