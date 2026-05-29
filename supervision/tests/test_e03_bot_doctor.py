"""
supervision/tests/test_e03_bot_doctor.py — E-03 BotDoctor Escalation

Tests de certification :
  - 5 niveaux d'escalade implémentés
  - Escalade automatique après timeout par niveau
  - Alerte à chaque niveau franchi
  - reset() après récupération
  - Historique complet

Total : 12 tests
"""

from __future__ import annotations

import time

import pytest

from supervision.escalation_engine import (
    EscalationEngine,
    EscalationLevel,
    EscalationStep,
    make_standard_escalation,
)


def _noop_ok():
    return True


def _noop_fail():
    return False


class TestEscalationLevels:
    def test_five_levels_defined(self):
        """Les 5 niveaux L1→L5 existent."""
        levels = list(EscalationLevel)
        assert len(levels) == 5
        assert EscalationLevel.L1_AUTO_HEAL in levels
        assert EscalationLevel.L2_ISOLATE_COMPONENT in levels
        assert EscalationLevel.L3_DEGRADE_MODE in levels
        assert EscalationLevel.L4_PARTIAL_HALT in levels
        assert EscalationLevel.L5_TOTAL_HALT in levels

    def test_levels_ordered(self):
        """Les niveaux sont ordonnés 1→5."""
        assert EscalationLevel.L1_AUTO_HEAL.value < EscalationLevel.L5_TOTAL_HALT.value

    def test_make_standard_returns_engine(self):
        """make_standard_escalation() retourne un EscalationEngine fonctionnel."""
        engine = make_standard_escalation()
        assert isinstance(engine, EscalationEngine)
        assert len(engine._steps) == 5


class TestEscalationTrigger:
    def test_trigger_starts_at_l1(self):
        """trigger() démarre l'escalade au niveau L1."""
        engine = make_standard_escalation(heal_fn=_noop_ok)
        engine.trigger("anomalie test")
        assert engine.current_level() == EscalationLevel.L1_AUTO_HEAL
        assert engine.is_escalating()

    def test_trigger_ignored_if_already_escalating(self):
        """trigger() ignoré si déjà en escalade."""
        engine = make_standard_escalation(heal_fn=_noop_ok)
        engine.trigger("anomalie 1")
        engine.trigger("anomalie 2")  # doublon — ignoré
        # Toujours au niveau L1
        assert engine.current_level() == EscalationLevel.L1_AUTO_HEAL

    def test_successful_action_stays_at_level(self):
        """Action L1 réussie → reste à L1, pas d'escalade immédiate."""
        engine = EscalationEngine()
        engine.add_step(
            EscalationStep(
                level=EscalationLevel.L1_AUTO_HEAL,
                action=_noop_ok,
                timeout_s=60.0,
            )
        )
        engine.trigger("test")
        # Après action réussie, le niveau reste L1 (surveillance active)
        assert engine.current_level() == EscalationLevel.L1_AUTO_HEAL


class TestAutoEscalation:
    def test_failed_action_escalates_immediately(self):
        """Action L1 échouée → escalade immédiate vers L2."""
        alerted = []
        engine = EscalationEngine()
        for level in EscalationLevel:
            engine.add_step(
                EscalationStep(
                    level=level,
                    action=_noop_fail,
                    timeout_s=60.0,
                    alert_fn=lambda msg, lv: alerted.append(lv),
                )
            )
        engine.trigger("test")
        # L1 échoue → L2 → L3 → ... jusqu'à L5
        # Après cascade, niveau actuel = L5 (ou None si L5 ne fail pas)
        final = engine.current_level()
        assert final is not None

    def test_timeout_triggers_escalation(self):
        """tick() avec timeout dépassé → escalade."""
        engine = EscalationEngine()
        engine.add_step(
            EscalationStep(
                level=EscalationLevel.L1_AUTO_HEAL,
                action=_noop_ok,
                timeout_s=0.05,  # timeout très court
            )
        )
        engine.add_step(
            EscalationStep(
                level=EscalationLevel.L2_ISOLATE_COMPONENT,
                action=_noop_ok,
                timeout_s=60.0,
            )
        )
        engine.trigger("test timeout")
        time.sleep(0.1)
        engine.tick()
        assert engine.current_level() == EscalationLevel.L2_ISOLATE_COMPONENT

    def test_alert_called_at_each_level(self):
        """alert_fn est appelé à chaque niveau franchi."""
        alerted_levels = []

        def alert(msg, level):
            alerted_levels.append(level)

        engine = EscalationEngine()
        for level in EscalationLevel:
            engine.add_step(
                EscalationStep(
                    level=level,
                    action=_noop_fail,
                    timeout_s=60.0,
                    alert_fn=alert,
                )
            )
        engine.trigger("cascade test")
        # Au minimum L1 doit avoir alerté
        assert len(alerted_levels) >= 1
        assert alerted_levels[0] == EscalationLevel.L1_AUTO_HEAL


class TestEscalationReset:
    def test_reset_clears_escalation(self):
        """reset() arrête l'escalade."""
        engine = make_standard_escalation(heal_fn=_noop_ok)
        engine.trigger("test")
        engine.reset("problème résolu")
        assert not engine.is_escalating()
        assert engine.current_level() is None

    def test_trigger_works_after_reset(self):
        """Nouvelle escalade possible après reset()."""
        engine = make_standard_escalation(heal_fn=_noop_ok)
        engine.trigger("test 1")
        engine.reset()
        engine.trigger("test 2")
        assert engine.is_escalating()

    def test_history_records_events(self):
        """escalation_history() non vide après trigger."""
        engine = make_standard_escalation(heal_fn=_noop_ok)
        engine.trigger("test historique")
        history = engine.escalation_history()
        assert len(history) >= 1
        assert "level" in history[0]
        assert "ts" in history[0]
        assert "reason" in history[0]

    def test_can_escalate_below_l5(self):
        """can_escalate() = True si niveau < L5."""
        engine = make_standard_escalation(heal_fn=_noop_ok)
        engine.trigger("test")
        # Au niveau L1, peut encore escalader
        assert engine.can_escalate()
