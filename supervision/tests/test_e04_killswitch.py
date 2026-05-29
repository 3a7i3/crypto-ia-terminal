"""
supervision/tests/test_e04_killswitch.py — E-04 Telegram KillSwitch Redundancy

Tests de certification :
  - Thread daemon indépendant
  - État persistant (survit aux redémarrages)
  - Acknowledgement des commandes destructives
  - force_halt() programmique
  - Mesure du temps de réponse

Total : 11 tests
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from supervision.killswitch_hardened import HardenedKSState, KillSwitchHardened


class TestKillSwitchBasic:
    def test_initial_state_not_halted(self, tmp_path):
        """État initial : pas de halt."""
        ks = KillSwitchHardened(state_path=tmp_path / "ks.json")
        assert not ks.is_halted()
        assert not ks.is_safe_mode()

    def test_force_halt_sets_halted(self, tmp_path):
        """force_halt() active le halt immédiatement."""
        ks = KillSwitchHardened(state_path=tmp_path / "ks.json")
        ks.force_halt("test reason")
        assert ks.is_halted()
        assert ks.halt_reason() == "test reason"

    def test_state_snapshot_complete(self, tmp_path):
        """state_snapshot() retourne tous les champs requis."""
        ks = KillSwitchHardened(state_path=tmp_path / "ks.json")
        snap = ks.state_snapshot()
        assert "halted" in snap
        assert "safe_mode" in snap
        assert "halt_reason" in snap
        assert "pending_command" in snap
        assert "avg_response_time_ms" in snap


class TestStatePersistence:
    def test_state_persisted_after_halt(self, tmp_path):
        """L'état halted est persisté sur disque après force_halt()."""
        state_path = tmp_path / "ks.json"
        ks = KillSwitchHardened(state_path=state_path)
        ks.force_halt("test persistence")
        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert data["halted"] is True
        assert data["halt_reason"] == "test persistence"

    def test_state_restored_after_reload(self, tmp_path):
        """État halted restauré au rechargement."""
        state_path = tmp_path / "ks.json"
        ks1 = KillSwitchHardened(state_path=state_path)
        ks1.force_halt("crash simulé")

        # Recréer depuis disque
        ks2 = KillSwitchHardened(state_path=state_path)
        assert ks2.is_halted(), "État halted doit être restauré depuis disque"
        assert ks2.halt_reason() == "crash simulé"

    def test_empty_state_file_handled(self, tmp_path):
        """Fichier d'état invalide → KS démarre proprement avec état par défaut."""
        state_path = tmp_path / "ks.json"
        state_path.write_text("not_json", encoding="utf-8")
        ks = KillSwitchHardened(state_path=state_path)  # ne doit pas crasher
        assert not ks.is_halted()


class TestCommandHandling:
    def test_dispatch_stop_all_without_confirmation(self, tmp_path):
        """Sans confirmation requise, STOP_ALL s'exécute directement."""
        ks = KillSwitchHardened(
            state_path=tmp_path / "ks.json",
            require_confirm=False,
        )
        ks._dispatch("/STOP_ALL", time.time())
        assert ks.is_halted()

    def test_dispatch_stop_all_with_confirmation_pending(self, tmp_path):
        """Avec confirmation requise, STOP_ALL est mis en attente."""
        ks = KillSwitchHardened(
            state_path=tmp_path / "ks.json",
            require_confirm=True,
        )
        ks._dispatch("/STOP_ALL", time.time())
        # Pas encore exécuté — en attente
        assert not ks.is_halted()
        with ks._lock:
            assert ks._state.pending_command == "/STOP_ALL"

    def test_confirm_executes_pending_command(self, tmp_path):
        """CONFIRM avec commande en attente → commande exécutée."""
        ks = KillSwitchHardened(
            state_path=tmp_path / "ks.json",
            require_confirm=True,
        )
        t0 = time.time()
        ks._dispatch("/STOP_ALL", t0)
        assert not ks.is_halted()
        # Confirmer
        ks._cmd_confirm(time.time())
        assert ks.is_halted()

    def test_cancel_clears_pending(self, tmp_path):
        """CANCEL efface la commande en attente."""
        ks = KillSwitchHardened(
            state_path=tmp_path / "ks.json",
            require_confirm=True,
        )
        ks._dispatch("/STOP_ALL", time.time())
        ks._cmd_cancel()
        with ks._lock:
            assert ks._state.pending_command == ""
        assert not ks.is_halted()

    def test_confirmation_expiry(self, tmp_path):
        """Confirmation expirée → commande annulée."""
        ks = KillSwitchHardened(
            state_path=tmp_path / "ks.json",
            require_confirm=True,
        )
        with ks._lock:
            ks._state.pending_command = "/STOP_ALL"
            ks._state.pending_command_ts = time.time() - 200  # bien expiré
        ks._expire_pending_confirm()
        with ks._lock:
            assert ks._state.pending_command == ""


class TestKillSwitchState:
    def test_hardened_ks_state_serialization(self):
        """HardenedKSState → to_dict() → from_dict() round-trip."""
        state = HardenedKSState(
            halted=True,
            halt_reason="test",
            halt_time=12345.0,
        )
        d = state.to_dict()
        restored = HardenedKSState.from_dict(d)
        assert restored.halted is True
        assert restored.halt_reason == "test"
        assert restored.halt_time == 12345.0
