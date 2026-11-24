"""Fenêtre SIGTERM de l'exécuteur : verrou EN_COURS publié avant le gestionnaire.

Défaut corrigé (diagnostic CI 2026-11-24) : `run_once` écrivait le verrou (lisible EN_COURS)
puis installait le gestionnaire SIGTERM. Un SIGTERM reçu entre les deux tuait le processus
(code -15, aucune enveloppe). Attendus :

| SIGTERM reçu | Résultat exigé |
|---|---|
| pendant l'écriture du verrou (avant pwrite) | INTERRUPTED publié, verrou libéré |
| après l'écriture, avant le gestionnaire (délai injecté) | INTERRUPTED publié, verrou libéré |
| après le gestionnaire (pendant l'audit) | INTERRUPTED publié, verrou libéré |
| avant le verrouillage | mort par défaut, aucun verrou écrit, aucune enveloppe ; la suivante COMPLETED sans ABANDONED |
| aucun (chemin normal ou exception) | masque de signaux et gestionnaire SIGTERM initiaux rétablis |

Les signaux sont toujours envoyés à un processus fils : un échec ne peut pas tuer pytest.
"""
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from invocation_bench import AGENT, RUNNER, wait_until

from agent_bench.observation import executor as ex
from agent_bench.observation import invocation_reader as rd

HERE = Path(__file__).parent
REPO = Path(__file__).parents[2]

# Fils : audit lent (20 s), crochet `hook` exécuté avant l'invocation, marqueur `marker` posé
# par le crochet quand le point d'interruption visé est atteint.
CHILD = (
    "import sys, time, os; sys.path.insert(0, %r);"
    "from agent_bench.observation import executor as ex, repository_cartographer as rc;"
    "real = rc.audit_zone\n"
    "def slow(*a, **k):\n    open(%r, 'w').close(); time.sleep(20); return real(*a, **k)\n"
    "rc.audit_zone = slow\n"
    "MARK = %r\n"
    "%s\n"
    "from test_invocation_contract import _restore\n"
    "g = _restore(%r); env, _ = ex.run_once(**g.kwargs()); print(env['state'])\n"
)

HOOKS = {
    # Marqueur puis délai AVANT l'écriture du verrou (SIGTERM reçu pendant RunnerLock.write).
    "during_write": (
        "_w = ex.RunnerLock.write\n"
        "def w(self, body):\n    open(MARK, 'w').close(); time.sleep(0.3); _w(self, body)\n"
        "ex.RunnerLock.write = w\n"),
    # Délai APRÈS l'écriture (verrou déjà lisible EN_COURS), avant le gestionnaire : la fenêtre du défaut.
    "after_write": (
        "_w = ex.RunnerLock.write\n"
        "def w(self, body):\n    _w(self, body); open(MARK, 'w').close(); time.sleep(0.3)\n"
        "ex.RunnerLock.write = w\n"),
    # Avant tout verrouillage : pendant la vérification du checkout.
    "before_lock": (
        "_v = ex.verify_checkout\n"
        "def v(*a, **k):\n    open(MARK, 'w').close(); time.sleep(5); return _v(*a, **k)\n"
        "ex.verify_checkout = v\n"),
    # Aucun délai : SIGTERM pendant l'audit, gestionnaire installé.
    "after_handler": "",
}


def _read(genv):
    return rd.read_status(genv.reports, mission_id=genv.mission["mission_id"], agent_id=AGENT,
                          runner_id=RUNNER, now_ts=time.time())


def _spawn(genv, hook):
    (genv.root / "mission.json").write_text(json.dumps(genv.mission))
    mark, audit = genv.root / "hook.mark", genv.root / "audit.mark"
    code = CHILD % (str(HERE), str(audit), str(mark), HOOKS[hook], str(genv.root))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), str(HERE)]))
    p = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE, cwd=str(REPO))
    return p, (audit if hook == "after_handler" else mark)


def _lock_is_free(genv):
    path = genv.reports / "locks" / f"{RUNNER}.lock"
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # lève si un processus le tient encore
        return True
    finally:
        os.close(fd)


def _envelopes(genv):
    return [json.loads(f.read_text()) for f in genv.runs_dir().glob("*.json")]


@pytest.mark.parametrize("hook", ["during_write", "after_write", "after_handler"])
def test_sigterm_after_lock_acquired_publishes_interrupted_and_releases(genv, hook):
    p, point = _spawn(genv, hook)
    assert wait_until(point.exists, 30)
    if hook == "after_write":  # la fenêtre exacte du défaut : le lecteur voit déjà EN_COURS
        assert _read(genv)["activity"] == "EN_COURS"
    p.send_signal(signal.SIGTERM)
    out, _ = p.communicate(timeout=30)
    assert (out.decode().strip(), p.returncode) == ("INTERRUPTED", 0)
    envs = _envelopes(genv)
    assert [e["state"] for e in envs] == ["INTERRUPTED"]
    assert envs[0]["interruption_reason"] == "interruption contrôlée (SIGTERM/SIGINT)"
    assert envs[0]["report"] is None
    assert _lock_is_free(genv)
    assert _read(genv)["activity"] == "TERMINE"
    assert not list(genv.runs_dir().glob("*.partial*"))


def test_sigterm_before_lock_leaves_no_lock_content_and_no_orphan(genv):
    p, point = _spawn(genv, "before_lock")
    assert wait_until(point.exists, 30)
    p.send_signal(signal.SIGTERM)
    p.communicate(timeout=30)
    assert p.returncode == -signal.SIGTERM  # refus implicite avant verrou : comportement par défaut
    lock = genv.reports / "locks" / f"{RUNNER}.lock"
    assert not lock.exists() or lock.stat().st_size == 0
    assert not genv.runs_dir().exists() or not any(genv.runs_dir().iterdir())
    env, _ = ex.run_once(**genv.kwargs())  # aucune invocation à consigner ABANDONED
    assert [e["state"] for e in _envelopes(genv)] == ["COMPLETED"] and env["state"] == "COMPLETED"


def _signal_state():
    return signal.pthread_sigmask(signal.SIG_BLOCK, []), signal.getsignal(signal.SIGTERM)


def test_mask_and_handler_restored_after_completed_run(genv):
    before = _signal_state()
    env, _ = ex.run_once(**genv.kwargs())
    assert env["state"] == "COMPLETED"
    assert _signal_state() == before
    assert signal.SIGTERM not in before[0]


def test_mask_and_handler_restored_when_lock_write_fails(genv, monkeypatch):
    def boom(self, body):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(ex.RunnerLock, "write", boom)
    before = _signal_state()
    with pytest.raises(OSError):
        ex.run_once(**genv.kwargs())
    assert _signal_state() == before
    monkeypatch.undo()
    assert _lock_is_free(genv)


def test_mask_and_handler_restored_when_publication_fails(genv, monkeypatch):
    def boom(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(ex.os, "link", boom)
    before = _signal_state()
    with pytest.raises(ex.Refused):
        ex.run_once(**genv.kwargs())
    assert _signal_state() == before


def test_lock_written_only_while_sigterm_blocked(genv, monkeypatch):
    seen = []
    real = ex.RunnerLock.write

    def spy(self, body):
        seen.append(signal.SIGTERM in signal.pthread_sigmask(signal.SIG_BLOCK, []))
        return real(self, body)
    monkeypatch.setattr(ex.RunnerLock, "write", spy)
    ex.run_once(**genv.kwargs())
    assert seen == [True]
