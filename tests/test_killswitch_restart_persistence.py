"""
Test d'intégration : persistance d'état du KillSwitch après redémarrage.

Scénario critique :
  /STOP_ALL → état persisté → arrêt du processus → redémarrage
  → KillSwitch toujours HALTED → aucun ordre autorisé
  → /RESUME → reprise autorisée

Ces tests ne nécessitent pas de connexion Telegram : ils opèrent
directement via force_halt() et la restauration depuis JSON.
"""

import json
from pathlib import Path

from supervision.killswitch_hardened import KillSwitchHardened


def _make_ks(tmp_path: Path) -> KillSwitchHardened:
    return KillSwitchHardened(state_path=tmp_path / "ks.json")


# ── Persistance basique ────────────────────────────────────────────────────────


def test_state_persisted_after_force_halt(tmp_path):
    ks = _make_ks(tmp_path)
    ks.force_halt("test_incident")
    assert (tmp_path / "ks.json").exists()
    raw = json.loads((tmp_path / "ks.json").read_text())
    assert raw["halted"] is True
    assert raw["halt_reason"] == "test_incident"


def test_halted_state_survives_restart(tmp_path):
    """Simulation d'un crash : KS1 halt, KS2 redémarre depuis le même fichier."""
    ks1 = _make_ks(tmp_path)
    ks1.force_halt("crash_scenario")
    assert ks1.is_halted()

    # Redémarrage — nouvelle instance, même state_path
    ks2 = _make_ks(tmp_path)
    assert ks2.is_halted(), "Le halt doit survivre au redémarrage"
    assert ks2.halt_reason() == "crash_scenario"


def test_execution_blocked_after_restart(tmp_path):
    """Après redémarrage, aucun ordre ne doit être autorisé."""
    ks1 = _make_ks(tmp_path)
    ks1.force_halt("risk_breach")

    ks2 = _make_ks(tmp_path)
    assert not ks2.is_execution_allowed()


def test_safe_mode_survives_restart(tmp_path):
    """Le safe_mode persiste également après redémarrage."""
    ks1 = _make_ks(tmp_path)
    # Simulation directe de safe_mode via la mécanique interne
    with ks1._lock:
        ks1._state.safe_mode = True
    ks1._persist_state()

    ks2 = _make_ks(tmp_path)
    assert ks2.is_safe_mode()
    assert not ks2.is_execution_allowed()


# ── Reprise après persistance ──────────────────────────────────────────────────


def test_execution_restored_after_resume_from_persisted_halt(tmp_path):
    """
    Cycle complet : halt persisté → redémarrage → toujours bloqué
    → RESUME (via _cmd_resume) → exécution à nouveau autorisée.
    """
    ks1 = _make_ks(tmp_path)
    ks1.force_halt("planned_maintenance")

    ks2 = _make_ks(tmp_path)
    assert not ks2.is_execution_allowed()

    # Simule un /RESUME sans Telegram (timestamp factice)
    import time

    ks2._cmd_resume(received_at=time.time())

    assert ks2.is_execution_allowed()
    assert not ks2.is_halted()

    # L'état post-RESUME est également persisté
    ks3 = _make_ks(tmp_path)
    assert not ks3.is_halted()
    assert ks3.is_execution_allowed()


# ── Cohérence de l'état initial ───────────────────────────────────────────────


def test_fresh_instance_allows_execution(tmp_path):
    """Sans fichier d'état, exécution autorisée par défaut."""
    ks = _make_ks(tmp_path)
    assert not ks.is_halted()
    assert not ks.is_safe_mode()
    assert ks.is_execution_allowed()


def test_corrupt_state_file_falls_back_to_default(tmp_path):
    """Un fichier d'état corrompu ne doit pas crasher le système."""
    state_path = tmp_path / "ks.json"
    state_path.write_text("{ invalid json }", encoding="utf-8")

    ks = KillSwitchHardened(state_path=state_path)
    # Fallback vers l'état par défaut — pas de crash, pas de halt fantôme
    assert not ks.is_halted()
    assert ks.is_execution_allowed()
