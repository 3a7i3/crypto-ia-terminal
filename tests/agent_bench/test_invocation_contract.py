"""Contrat d'invocation v1 : exécuteur, verrou, publication et lecteur.

Attendus écrits avant les corrections (revue de 33b1ec03) :

| Défaut / cas | Résultat exigé |
|---|---|
| Verrou d'un autre runner, d'une autre mission, sans invocation, bail de 24 h | jamais EN_COURS |
| Dates de verrou incohérentes ou futures | jamais EN_COURS, motif |
| Bail valide sans processus vivant (arrêté, PID réutilisé) | INDETERMINE, jamais EN_COURS |
| Rapport d'un autre agent, autre SHA analysé, profil incohérent | INVALID même si le sceau est recalculé |
| État / code de sortie incohérents | INVALID |
| Git indisponible, HEAD invérifiable, checkout modifié, code exécuté ≠ référence | refus avant verrou |
| Deux processus concurrents, deux reprises simultanées d'un état abandonné | une seule exécution |
| Arrêt brutal | verrou libéré par le noyau, invocation consignée ABANDONED ensuite |
| Interruption contrôlée (SIGTERM) | INTERRUPTED publié, verrou libéré |
| Échec de publication | refus explicite, verrou libéré, ABANDONED à la suite |
| Nom déjà présent | ancien fichier préservé |
| Lien symbolique dans un dossier parent | refus |
| Plus de 200 entrées | énumération refusée explicitement |
| Nom de fichier ≠ enveloppe | INVALID |
| Dernière mission > 36 h | rouge, libellé « plus de 36 h » |
| Relecture d'un ancien rapport | date d'activité inchangée |
| Lecteur | aucun fichier modifié, aucun verrou pris |
"""
import copy
import json
import multiprocessing as mp
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from invocation_bench import AGENT, RUNNER, git, lock_content, wait_until

from agent_bench.observation import contract as c
from agent_bench.observation import executor as ex
from agent_bench.observation import invocation as inv
from agent_bench.observation import invocation_reader as rd


def _read(genv, now=None, **kw):
    return rd.read_status(genv.reports, mission_id=genv.mission["mission_id"], agent_id=AGENT,
                          runner_id=RUNNER, now_ts=time.time() if now is None else now, **kw)


def _reseal(env):
    rep = env["report"]
    rep["content_sha256"] = c.sha256_json(rep["content"])
    rep["report_sha256"] = c.sha256_json({k: rep[k] for k in ("content", "content_sha256", "run")})
    env["content_sha256"], env["report_sha256"] = rep["content_sha256"], rep["report_sha256"]
    return env


def _validate(env, genv, **kw):
    return inv.validate_envelope(env, agent_id=AGENT, runner_id=RUNNER, mission_id=genv.mission["mission_id"],
                                 now_ts=time.time() + 5, **kw)


# === 2. Validation stricte des preuves d'exécution =====================================

@pytest.mark.parametrize("over,why", [
    ({"runner_id": "autre-runner-01"}, "autre runner"),
    ({"agent_id": "observability-cartographer"}, "autre agent"),
    ({"mission_id": "0" * 64}, "autre mission"),
    ({"invocation_id": None}, "schéma"),
    ({"invocation_id": "zz"}, "identifiant"),
    ({"lease_until_utc": "LEASE_24H"}, "bail excessif"),
    ({"lease_until_utc": "BEFORE_START"}, "bail antérieur"),
    ({"started_utc": "FUTURE"}, "futur"),
    ({"started_utc": "2026-13-40T99:00:00Z"}, "dates"),
])
def test_lock_held_but_invalid_is_never_en_cours(genv, holders, over, why):
    now = time.time()
    special = {"LEASE_24H": inv.utc_iso(now + 86400), "BEFORE_START": inv.utc_iso(now - 60),
               "FUTURE": inv.utc_iso(now + 3600)}
    over = {k: special.get(v, v) for k, v in over.items()}
    holders(genv.reports, lock_content(genv.mission["mission_id"], now, **over))
    st = _read(genv, now)
    assert st["activity"] != "EN_COURS"
    assert st["life_observed"] is True
    assert why in st["activity_reason"]
    assert st["display"]["light"] == "GRAY"


def test_valid_lock_held_by_live_process_is_en_cours_bounded(genv, holders):
    now = time.time()
    holders(genv.reports, lock_content(genv.mission["mission_id"], now))
    st = _read(genv, now)
    assert st["activity"] == "EN_COURS" and st["life_observed"] is True
    d = st["display"]
    assert d["light"] == "GREEN"
    assert inv.parse_utc(d["valid_until_utc"]) <= min(now + inv.DISPLAY_TTL_S, inv.parse_utc(st["lease_until_utc"]))


def test_stopped_process_releases_lock_and_is_not_en_cours(genv, holders):
    now = time.time()
    h = holders(genv.reports, lock_content(genv.mission["mission_id"], now))
    assert _read(genv, now)["activity"] == "EN_COURS"
    h.kill()  # arrêt brutal : le noyau libère le flock
    st = _read(genv, now)
    assert st["activity"] == "INDETERMINE" and "aucun processus" in st["activity_reason"]


def test_pid_reuse_cannot_fake_activity(genv, holders):
    now = time.time()
    # Contenu valide nommant un PID vivant (celui du test), sans aucun verrou tenu.
    (genv.reports / "locks").mkdir(parents=True)
    (genv.reports / "locks" / f"{RUNNER}.lock").write_text(
        json.dumps(dict(lock_content(genv.mission["mission_id"], now), pid=os.getpid())))
    assert _read(genv, now)["activity"] == "INDETERMINE"
    # Verrou tenu par un processus, contenu déclarant un autre PID vivant.
    holders(genv.reports, dict(lock_content(genv.mission["mission_id"], now), pid=os.getpid()))
    st = _read(genv, now)
    assert st["activity"] == "INDETERMINE" and "détenteur" in st["activity_reason"]


def test_unreadable_proc_locks_is_indeterminate(genv, holders, tmp_path):
    now = time.time()
    holders(genv.reports, lock_content(genv.mission["mission_id"], now))
    st = _read(genv, now, proc_locks=tmp_path / "absent")
    assert st["activity"] == "INDETERMINE" and "non attestable" in st["activity_reason"]


# === 3. Cohérence enveloppe / rapport / sources =========================================

def test_valid_run_records_distinct_code_and_scope_verification(genv):
    env, name = ex.run_once(**genv.kwargs())
    assert env["state"] == "COMPLETED" and env["result_status"] == "PARTIAL"
    v = env["verification"]
    assert v["checkout_head"] == genv.sha
    assert set(v["scope_blobs"]) == set(genv.mission["scope"]["read_paths"])
    assert "agent_bench/observation/executor.py" in v["executed_modules"]
    assert _validate(env, genv) == ("VALID", "ok")
    assert name == inv.file_name(env)


@pytest.mark.parametrize("mutate,reason", [
    (lambda e: e["report"]["content"].update(agent_id="observability-cartographer"), "autre agent"),
    (lambda e: e["report"]["content"].update(analyzed_ref={"kind": "GIT_COMMIT", "sha": "1" * 40}), "SHA analysé"),
    (lambda e: e["report"]["content"].update(mission_id="2" * 64), "autre mission"),
    (lambda e: e["report"]["content"]["profile"].update(path="profile:.github/agents/autre.agent.md"), "profil du rapport"),
    (lambda e: e["report"]["content"].update(status="COMPLETE"), "résultat déclaré"),
])
def test_resealed_report_inconsistent_with_envelope_is_invalid(genv, mutate, reason):
    env, _ = ex.run_once(**genv.kwargs())
    bad = copy.deepcopy(env)
    mutate(bad)
    v, why = _validate(_reseal(bad), genv)
    assert v == "INVALID" and reason in why


@pytest.mark.parametrize("mutate,reason", [
    (lambda e: e.update(profile_blob_sha1="3" * 40), "profil"),
    (lambda e: e["verification"].update(checkout_head="4" * 40), "HEAD vérifié"),
    (lambda e: e.update(exit_code=1), "code de sortie 0"),
    (lambda e: e.update(state="FAILED", exit_code=0), "≥ 1"),
    (lambda e: e["limits"].update(max_run_s=9999), "bornes"),
])
def test_envelope_identity_state_and_limits_are_checked(genv, mutate, reason):
    env, _ = ex.run_once(**genv.kwargs())
    bad = copy.deepcopy(env)
    mutate(bad)
    v, why = _validate(bad, genv)
    assert v == "INVALID" and reason in why


def test_expected_profile_blob_is_enforced(genv):
    env, _ = ex.run_once(**genv.kwargs())
    v, why = _validate(env, genv, expected_profile_blob="5" * 40)
    assert v == "INVALID" and "profil qualifié" in why


def test_git_unavailable_is_refused(genv, monkeypatch):
    monkeypatch.setattr(ex, "GIT", "/nonexistent/git")
    with pytest.raises(ex.Refused) as err:
        ex.run_once(**genv.kwargs())
    assert err.value.code == "GIT_UNAVAILABLE"
    assert not (genv.reports / "locks").exists()


def test_checkout_without_git_is_refused(genv):
    import shutil
    shutil.rmtree(genv.checkout / ".git")
    with pytest.raises(ex.Refused) as err:
        ex.run_once(**genv.kwargs())
    assert err.value.code == "HEAD_UNVERIFIABLE"


def test_modified_scope_file_is_refused(genv):
    p = genv.checkout / genv.mission["scope"]["read_paths"][0]
    p.write_text(p.read_text() + "\n# modifié\n")
    with pytest.raises(ex.Refused) as err:
        ex.run_once(**genv.kwargs())
    assert err.value.code == "CHECKOUT_MODIFIED"


def test_head_different_from_declared_code_is_refused(genv):
    with pytest.raises(ex.Refused) as err:
        ex.run_once(**genv.kwargs(code_sha="6" * 40))
    assert err.value.code == "CHECKOUT_SHA_MISMATCH"


def test_executed_code_not_matching_declared_reference_is_refused(genv):
    p = genv.checkout / "agent_bench/observation/executor.py"
    p.write_text(p.read_text() + "\n# variante commitée\n")
    git(genv.checkout, "commit", "-qam", "variante")
    new_head = git(genv.checkout, "rev-parse", "HEAD")
    with pytest.raises(ex.Refused) as err:
        ex.run_once(**genv.kwargs(code_sha=new_head))
    assert err.value.code == "CODE_MISMATCH"


def test_modified_profile_is_refused(genv):
    p = genv.checkout / genv.mission["profile"]["source_path"]
    p.write_text(p.read_text() + "\nmodifié\n")
    with pytest.raises(ex.Refused) as err:
        ex.run_once(**genv.kwargs())
    assert err.value.code == "PROFILE_MISMATCH"


# === 4. Verrouillage concurrent : vrais processus =======================================

def _slow_runner(genv_root, barrier, queue, delay):
    from invocation_bench import GitEnv  # noqa: F401 — même interpréteur

    from agent_bench.observation import executor as exx
    from agent_bench.observation import repository_cartographer as rcc
    real = rcc.audit_zone

    def slow(*a, **k):
        time.sleep(delay)
        return real(*a, **k)
    rcc.audit_zone = slow
    g = _restore(genv_root)
    barrier.wait(10)
    try:
        env, _ = exx.run_once(**g.kwargs())
        queue.put(("OK", env["invocation_id"]))
    except exx.Refused as exc:
        queue.put(("REFUSED", exc.code))


def _restore(root):
    """Rouvre un GitEnv existant (dans un processus fils)."""
    from invocation_bench import GitEnv
    g = GitEnv.__new__(GitEnv)
    g.root, g.checkout, g.reports = Path(root), Path(root) / "checkout", Path(root) / "reports"
    g.sha = git(g.checkout, "rev-parse", "HEAD")
    g.mission = json.loads((Path(root) / "mission.json").read_text())
    return g


def _spawn_pair(genv, delay=1.0):
    (genv.root / "mission.json").write_text(json.dumps(genv.mission))
    ctx = mp.get_context("fork")
    barrier, queue = ctx.Barrier(2), ctx.Queue()
    procs = [ctx.Process(target=_slow_runner, args=(str(genv.root), barrier, queue, delay)) for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    return sorted(queue.get(timeout=5) for _ in procs)


def test_two_concurrent_processes_only_one_runs(genv):
    results = _spawn_pair(genv)
    assert [r[0] for r in results] == ["OK", "REFUSED"]
    assert results[1][1] == "ALREADY_RUNNING"
    published = list(genv.runs_dir().glob("*.json"))
    assert len(published) == 1


def _killed_mid_run(genv):
    """Lance un exécuteur réel, attend qu'il tienne le verrou, puis SIGKILL."""
    (genv.root / "mission.json").write_text(json.dumps(genv.mission))
    code = (  # noqa: UP031 — script injecté, %r garantit les littéraux
        "import sys, time, json; sys.path.insert(0, %r);"
        "from agent_bench.observation import executor as ex, repository_cartographer as rc;"
        "real = rc.audit_zone\n"
        "def slow(*a, **k):\n    time.sleep(30); return real(*a, **k)\n"
        "rc.audit_zone = slow\n"
        "from invocation_bench import GitEnv\n"
        "from test_invocation_contract import _restore\n"
        "g = _restore(%r); ex.run_once(**g.kwargs())\n"
    ) % (str(Path(__file__).parent), str(genv.root))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(Path(__file__).parents[2]), str(Path(__file__).parent)]))
    p = subprocess.Popen([sys.executable, "-c", code], env=env, cwd=str(Path(__file__).parents[2]))
    lock = genv.reports / "locks" / f"{RUNNER}.lock"
    assert wait_until(lambda: lock.exists() and lock.stat().st_size > 0 and _read(genv)["activity"] == "EN_COURS", 30)
    inv_id = json.loads(lock.read_text())["invocation_id"]
    p.send_signal(signal.SIGKILL)
    p.wait(10)
    return inv_id, p


def test_hard_kill_then_two_simultaneous_resumptions(genv):
    killed_id, _ = _killed_mid_run(genv)
    st = _read(genv)
    assert st["activity"] != "EN_COURS"  # disparition immédiate : le noyau a libéré le verrou
    results = _spawn_pair(genv)
    assert [r[0] for r in results] == ["OK", "REFUSED"]
    envs = [json.loads(p.read_text()) for p in genv.runs_dir().glob("*.json")]
    abandoned = [e for e in envs if e["state"] == "ABANDONED"]
    assert len(abandoned) == 1 and abandoned[0]["invocation_id"] == killed_id
    assert abandoned[0]["report"] is None and abandoned[0]["code_sha"] is None
    assert len([e for e in envs if e["state"] == "COMPLETED"]) == 1


def test_controlled_interruption_publishes_interrupted_and_releases(genv):
    (genv.root / "mission.json").write_text(json.dumps(genv.mission))
    code = (  # noqa: UP031 — script injecté, %r garantit les littéraux
        "import sys, time; sys.path.insert(0, %r);"
        "from agent_bench.observation import executor as ex, repository_cartographer as rc;"
        "real = rc.audit_zone\n"
        "def slow(*a, **k):\n    time.sleep(20); return real(*a, **k)\n"
        "rc.audit_zone = slow\n"
        "from test_invocation_contract import _restore\n"
        "g = _restore(%r); env, _ = ex.run_once(**g.kwargs()); print(env['state'])\n"
    ) % (str(Path(__file__).parent), str(genv.root))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(Path(__file__).parents[2]), str(Path(__file__).parent)]))
    p = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE,
                         cwd=str(Path(__file__).parents[2]))
    assert wait_until(lambda: _read(genv)["activity"] == "EN_COURS", 30)
    p.send_signal(signal.SIGTERM)
    out, _ = p.communicate(timeout=30)
    assert out.decode().strip() == "INTERRUPTED"
    envs = [json.loads(f.read_text()) for f in genv.runs_dir().glob("*.json")]
    assert [e["state"] for e in envs] == ["INTERRUPTED"]
    assert _validate(envs[0], genv)[0] == "VALID"
    assert _read(genv)["activity"] == "TERMINE"
    assert _read(genv)["display"]["label"] == "Inactif · échec"


def test_publication_failure_is_explicit_and_leaves_no_running_state(genv, monkeypatch):
    def boom(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(ex.os, "link", boom)
    with pytest.raises(ex.Refused) as err:
        ex.run_once(**genv.kwargs())
    assert err.value.code == "PUBLICATION_FAILED"
    assert not any(genv.runs_dir().iterdir())          # aucun fichier, aucun .partial
    assert _read(genv)["activity"] != "EN_COURS"
    monkeypatch.undo()
    _env, _ = ex.run_once(**genv.kwargs())             # l'invocation suivante consigne l'abandon
    states = sorted(json.loads(f.read_text())["state"] for f in genv.runs_dir().glob("*.json"))
    assert states == ["ABANDONED", "COMPLETED"]


def test_running_holder_blocks_and_its_lock_is_untouched(genv, holders):
    now = time.time()
    holders(genv.reports, lock_content(genv.mission["mission_id"], now))
    lock = genv.reports / "locks" / f"{RUNNER}.lock"
    before = lock.read_bytes()
    with pytest.raises(ex.Refused) as err:
        ex.run_once(**genv.kwargs())
    assert err.value.code == "ALREADY_RUNNING"
    assert lock.read_bytes() == before


def test_lock_file_is_never_deleted(genv):
    ex.run_once(**genv.kwargs())
    assert (genv.reports / "locks" / f"{RUNNER}.lock").exists()
    assert _read(genv)["activity"] == "TERMINE"


def test_reader_is_strictly_passive(genv, holders):
    ex.run_once(**genv.kwargs())
    holders(genv.reports, lock_content(genv.mission["mission_id"], time.time()))

    def snap():
        return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in genv.reports.rglob("*") if p.is_file()}
    before = snap()
    _read(genv)
    assert snap() == before
    assert str(os.getpid()) not in Path("/proc/locks").read_text().split()


# === 6. Point d'entrée, publication, lecture bornée ======================================

def _cli(genv, *extra, pythonpath=None):
    mission = genv.root / "mission.json"
    mission.write_text(json.dumps(genv.mission))
    env = dict(os.environ, PYTHONPATH=pythonpath or str(genv.checkout))
    out = subprocess.run([sys.executable, "-m", "agent_bench.observation.executor", "--mission", str(mission),
                          "--checkout", str(genv.checkout), "--reports", str(genv.reports), "--runner-id", RUNNER,
                          "--code-sha", genv.sha, "--analysed-sha", genv.sha, *extra],
                         capture_output=True, env=env, cwd=str(genv.root), timeout=120, check=False)
    return out.returncode, json.loads(out.stdout.decode().strip().splitlines()[-1])


def test_cli_end_to_end_from_the_checkout(genv):
    code, out = _cli(genv)
    assert code == 0 and out["outcome"] == "PUBLISHED" and out["state"] == "COMPLETED"
    assert out["result_status"] == "PARTIAL" and out["code_sha"] == genv.sha
    st = _read(genv)
    assert st["connection"] == "AVAILABLE" and st["last_result"] == "PARTIAL"


def test_cli_cannot_raise_limits(genv):
    code, _out = _cli(genv, "--max-run-s", "99999")
    assert code == 0
    env = json.loads(next(genv.runs_dir().glob("*.json")).read_text())
    assert env["limits"]["max_run_s"] <= min(inv.MAX_RUN_S, genv.mission["budget"]["max_wall_ms"] / 1000)


def test_cli_refuses_unverifiable_configuration(genv):
    code, out = _cli(genv, "--code-sha", "7" * 40)
    assert code == ex.EXIT_REFUSED and out["outcome"] == "REFUSED" and out["code"] == "CHECKOUT_SHA_MISMATCH"
    assert not (genv.reports / "runs").exists()


def test_existing_name_is_preserved(genv):
    env, name = ex.run_once(**genv.kwargs())
    path = genv.runs_dir() / name
    before = path.read_bytes()
    with pytest.raises(ex.Refused) as err:
        ex.publish(genv.reports, env)
    assert err.value.code == "NAME_EXISTS" and path.read_bytes() == before
    assert not [p for p in genv.runs_dir().iterdir() if p.name.startswith(".")]


def test_parent_symlink_is_refused_by_reader_and_publisher(genv, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / genv.mission["mission_id"]).mkdir(parents=True)
    os.symlink(elsewhere, genv.reports / "runs")
    st = _read(genv)
    assert st["connection"] == "UNREADABLE" and "lien" in st["connection_reason"]
    with pytest.raises(ex.Refused) as err:
        ex.run_once(**genv.kwargs())
    assert err.value.code == "PUBLICATION_FAILED"
    assert not any((elsewhere / genv.mission["mission_id"]).iterdir())


def test_reader_needs_only_traverse_right_on_reports_root(genv):
    """Le compte API n'a que `x` sur la racine des rapports (pas de listage) : lecture possible.

    Sous root la permission est contournée ; ce test est discriminant en CI (compte non root).
    La vérification sous deux comptes distincts avec ACL est consignée dans la PR #599.
    """
    ex.run_once(**genv.kwargs())
    os.chmod(genv.reports, 0o100)
    try:
        st = _read(genv)
    finally:
        os.chmod(genv.reports, 0o750)
    assert st["connection"] == "AVAILABLE" and st["activity"] == "TERMINE"


def test_directory_enumeration_is_really_bounded(genv):
    d = genv.runs_dir()
    d.mkdir(parents=True)
    for i in range(inv.MAX_DIR_ENTRIES + 1):
        (d / f"bruit-{i}.txt").write_text("")
    st = _read(genv)
    assert st["connection"] == "UNREADABLE" and "énumération refusée" in st["connection_reason"]


def test_executor_refuses_an_unbounded_reports_directory(genv):
    d = genv.runs_dir()
    d.mkdir(parents=True)
    for i in range(inv.MAX_DIR_ENTRIES + 1):
        (d / f"bruit-{i}.txt").write_text("")
    with pytest.raises(ex.Refused) as err:
        ex.run_once(**genv.kwargs())
    assert err.value.code == "REPORTS_DIR_OVERFLOW"
    assert not any(inv.NAME_RE.match(n) for n in os.listdir(d))


def test_file_name_must_match_envelope(genv):
    env, name = ex.run_once(**genv.kwargs())
    p = genv.runs_dir() / name
    p.rename(genv.runs_dir() / name.replace(env["invocation_id"], "f" * 32))
    st = _read(genv)
    assert st["connection"] == "INVALID" and "nom de fichier" in st["connection_reason"]


def test_partial_file_is_ignored_then_cleaned(genv):
    d = genv.runs_dir()
    d.mkdir(parents=True)
    (d / f".20261122T000000Z_{'c' * 32}.json.partial").write_text('{"contract": "cat')
    assert _read(genv)["connection"] == "ABSENT"
    ex.run_once(**genv.kwargs())
    assert not [p for p in d.iterdir() if p.name.endswith(".partial")]


def test_absence_rule_36h_and_old_report_never_rejuvenated(genv):
    env, _ = ex.run_once(**genv.kwargs())
    ended = inv.parse_utc(env["ended_utc"])
    fresh = _read(genv, ended + 60)
    old = _read(genv, ended + inv.ABSENCE_WINDOW_S + 60)
    assert fresh["last_activity_utc"] == old["last_activity_utc"] == env["ended_utc"]
    assert fresh["mission_overdue"] is False and old["mission_overdue"] is True
    assert old["display"]["light"] == "RED" and "36 h" in old["display"]["label"]
    assert fresh["server_observed_at_utc"] != old["server_observed_at_utc"]


def test_completed_partial_is_red_normal_end_not_running(genv):
    ex.run_once(**genv.kwargs())
    st = _read(genv)
    assert st["activity"] == "TERMINE" and st["last_result"] == "PARTIAL"
    assert st["display"]["light"] == "RED" and st["display"]["label"] == "Inactif · fin normale"
    assert st["display"]["valid_until_utc"] is not None


def test_invalid_proof_with_live_lock_is_gray(genv, holders):
    _env, name = ex.run_once(**genv.kwargs())
    p = genv.runs_dir() / name
    data = json.loads(p.read_text())
    data["report"]["content"]["findings"] = []
    p.write_text(json.dumps(data))
    holders(genv.reports, lock_content(genv.mission["mission_id"], time.time()))
    st = _read(genv)
    assert st["activity"] == "EN_COURS" and st["connection"] == "INVALID"
    assert st["display"]["light"] == "GRAY"


def test_missing_reports_root_is_explicit(genv, tmp_path):
    st = rd.read_status(tmp_path / "absent", mission_id=genv.mission["mission_id"], agent_id=AGENT,
                        runner_id=RUNNER, now_ts=time.time())
    assert st["connection"] == "ABSENT" and st["display"]["light"] == "GRAY"
