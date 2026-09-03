"""
test_system_controller_authority.py — S-02B.1 SystemController Authority Closure

Vérifie que FEATURE_ADAPTIVE_DECISION_FEEDBACK=false ne désactive JAMAIS les
actions de sécurité/récupération/risque (STOP_TRADING, RESUME_TRADING,
REDUCE_RISK) mais rend ADJUST_TP / ADJUST_SL / APPLY_META strictement
contrefactuelles : décision/raison/confiance/params toujours générés et
observables, mais jamais appliqués à l'état effectif ni comptés comme
exécutés — à la fois dans ActionExecutor.execute()
(tracker_system/autonomous/auto_decision_engine.py) et dans la mutation de
_sc_state (core/advisor_loop.py::_sc_run_cycle).

Vérifie aussi que l'API publique elle-même est fail-closed :
ActionExecutor et AutoDecisionOrchestrator défaultent à
adaptive_decision_feedback=False — un appelant qui omet ce paramètre obtient
le mode passif, jamais l'autorité adaptative par accident. Seul `True`
explicite restaure l'application legacy (jamais par omission).

Hors périmètre (ne pas toucher/tester ici) : FEATURE_REGRET_DECISION_FEEDBACK,
FEATURE_AUTO_CALIBRATION, RegretEngine, RegretScheduler, REGIME_MISMATCH,
contrats scientifiques S-01.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tracker_system.autonomous.auto_decision_engine import (
    ActionExecutor,
    AutoDecisionOrchestrator,
    Decision,
)


# ── Groupe A : actions de sécurité/récupération/risque — non affectées ───────


class TestSafetyActionsUnaffectedByFlag:
    """STOP_TRADING / RESUME_TRADING / REDUCE_RISK restent pleinement
    autoritaires quelle que soit la valeur de adaptive_decision_feedback."""

    def test_stop_trading_applies_when_flag_false(self):
        import system.state_machine as _sm_mod

        executor = ActionExecutor(
            {"trading_enabled": True}, adaptive_decision_feedback=False
        )
        mock_sm = MagicMock()
        original = _sm_mod.get_state_machine
        _sm_mod.get_state_machine = lambda: mock_sm
        try:
            decision = Decision("STOP_TRADING", {}, "dd>5%", confidence=0.95)
            new_config, executed, _msg = executor.execute(decision)
        finally:
            _sm_mod.get_state_machine = original

        assert executed is True
        assert new_config["trading_enabled"] is False
        mock_sm.transition.assert_called_once_with(
            "HALTED", reason="dd>5%", halt_source="AutoDecisionEngine"
        )

    def test_resume_trading_applies_when_flag_false(self):
        import system.state_machine as _sm_mod

        executor = ActionExecutor(
            {"trading_enabled": False}, adaptive_decision_feedback=False
        )
        mock_sm = MagicMock()
        original = _sm_mod.get_state_machine
        _sm_mod.get_state_machine = lambda: mock_sm
        try:
            decision = Decision("RESUME_TRADING", {}, "recovered", confidence=0.9)
            new_config, executed, _msg = executor.execute(decision)
        finally:
            _sm_mod.get_state_machine = original

        assert executed is True
        assert new_config["trading_enabled"] is True
        mock_sm.transition.assert_called_once()

    def test_reduce_risk_applies_when_flag_false(self):
        executor = ActionExecutor(
            {"position_size": 0.1}, adaptive_decision_feedback=False
        )
        decision = Decision(
            "REDUCE_RISK", {"position_size_factor": 0.5}, "loss streak", confidence=0.85
        )
        new_config, executed, _msg = executor.execute(decision)

        assert executed is True
        assert new_config["position_size"] == pytest.approx(0.05)

    def test_stop_trading_applies_under_default_constructor(self):
        """Omettre adaptive_decision_feedback ne désactive jamais STOP_TRADING
        (SAFETY AUTHORITY != ADAPTIVE AUTHORITY)."""
        import system.state_machine as _sm_mod

        executor = ActionExecutor({"trading_enabled": True})  # pas de flag passé
        mock_sm = MagicMock()
        original = _sm_mod.get_state_machine
        _sm_mod.get_state_machine = lambda: mock_sm
        try:
            decision = Decision("STOP_TRADING", {}, "dd>5%", confidence=0.95)
            new_config, executed, _msg = executor.execute(decision)
        finally:
            _sm_mod.get_state_machine = original

        assert executed is True
        assert new_config["trading_enabled"] is False
        mock_sm.transition.assert_called_once()

    def test_resume_trading_applies_under_default_constructor(self):
        import system.state_machine as _sm_mod

        executor = ActionExecutor({"trading_enabled": False})  # pas de flag passé
        mock_sm = MagicMock()
        original = _sm_mod.get_state_machine
        _sm_mod.get_state_machine = lambda: mock_sm
        try:
            decision = Decision("RESUME_TRADING", {}, "recovered", confidence=0.9)
            new_config, executed, _msg = executor.execute(decision)
        finally:
            _sm_mod.get_state_machine = original

        assert executed is True
        assert new_config["trading_enabled"] is True
        mock_sm.transition.assert_called_once()

    def test_reduce_risk_applies_under_default_constructor(self):
        executor = ActionExecutor({"position_size": 0.1})  # pas de flag passé
        decision = Decision(
            "REDUCE_RISK", {"position_size_factor": 0.5}, "loss streak", confidence=0.85
        )
        new_config, executed, _msg = executor.execute(decision)

        assert executed is True
        assert new_config["position_size"] == pytest.approx(0.05)


# ── Groupe A-bis : défauts publics fail-closed (omission == passif) ──────────


class TestPublicApiDefaultsAreFailClosed:
    """ActionExecutor et AutoDecisionOrchestrator doivent être fail-closed par
    défaut : un appelant qui omet adaptive_decision_feedback ne doit jamais
    obtenir l'autorité adaptative par accident (S-02B.1, LEARNING != AUTHORITY).
    Seul `adaptive_decision_feedback=True` explicite restaure l'application
    legacy."""

    def test_orchestrator_default_is_passive_for_adjust_tp(self):
        orchestrator = AutoDecisionOrchestrator(
            {"tp": 0.02, "sl": 0.01, "position_size": 0.1, "trading_enabled": True},
            log_file="/dev/null",
        )  # pas de adaptive_decision_feedback passé
        metrics = {"efficiency": 0.40, "mae_pct": -0.01}
        risk_state = {"drawdown": 0.01, "loss_streak": 0}

        new_config, decision, executed = orchestrator.run_decision_cycle(
            metrics, risk_state
        )

        assert decision.action == "ADJUST_TP"  # decision toujours générée/observable
        assert executed is False
        assert new_config["tp"] == 0.02  # jamais appliqué par omission

    def test_orchestrator_explicit_true_applies_adjust_tp(self):
        orchestrator = AutoDecisionOrchestrator(
            {"tp": 0.02, "sl": 0.01, "position_size": 0.1, "trading_enabled": True},
            log_file="/dev/null",
            adaptive_decision_feedback=True,
        )
        metrics = {"efficiency": 0.40, "mae_pct": -0.01}
        risk_state = {"drawdown": 0.01, "loss_streak": 0}

        new_config, decision, executed = orchestrator.run_decision_cycle(
            metrics, risk_state
        )

        assert decision.action == "ADJUST_TP"
        assert executed is True
        assert new_config["tp"] == pytest.approx(0.02 * 1.15)

    def test_executor_explicit_true_applies_adjust_tp(self):
        """Pendant de test_default_constructor_is_passive_fail_closed : l'opt-in
        explicite restaure bien l'application legacy."""
        executor = ActionExecutor({"tp": 0.02}, adaptive_decision_feedback=True)
        decision = Decision("ADJUST_TP", {"tp_factor": 1.20}, "x", confidence=0.72)
        new_config, executed, _msg = executor.execute(decision)

        assert executed is True
        assert new_config["tp"] == pytest.approx(0.024)

    def test_orchestrator_default_still_executes_stop_trading(self):
        """La passivité par défaut ne s'étend jamais aux actions de sécurité."""
        orchestrator = AutoDecisionOrchestrator(
            {"tp": 0.02, "sl": 0.01, "position_size": 0.1, "trading_enabled": True},
            log_file="/dev/null",
        )  # pas de adaptive_decision_feedback passé
        metrics = {"efficiency": 0.5, "mae_pct": -0.01}
        risk_state = {"drawdown": 0.07, "loss_streak": 2}  # drawdown > 5%

        new_config, decision, executed = orchestrator.run_decision_cycle(
            metrics, risk_state
        )

        assert decision.action == "STOP_TRADING"
        assert executed is True
        assert new_config["trading_enabled"] is False


# ── Groupe B : ADJUST_TP / ADJUST_SL / APPLY_META — passif vs actif ──────────


class TestAdjustTpPassiveVsActive:
    def test_passive_does_not_mutate_config_and_not_executed(self):
        executor = ActionExecutor({"tp": 0.02}, adaptive_decision_feedback=False)
        decision = Decision(
            "ADJUST_TP", {"tp_factor": 1.20}, "low efficiency", confidence=0.72
        )
        new_config, executed, msg = executor.execute(decision)

        assert executed is False
        assert new_config["tp"] == 0.02
        assert "not applied" in msg.lower()

    def test_active_mutates_config_legacy_behavior(self):
        executor = ActionExecutor({"tp": 0.02}, adaptive_decision_feedback=True)
        decision = Decision(
            "ADJUST_TP", {"tp_factor": 1.20}, "low efficiency", confidence=0.72
        )
        new_config, executed, _msg = executor.execute(decision)

        assert executed is True
        assert new_config["tp"] == pytest.approx(0.024)

    def test_default_constructor_is_passive_fail_closed(self):
        """Un appelant qui omet adaptive_decision_feedback obtient le mode
        passif — jamais l'application adaptative par omission (S-02B.1,
        LEARNING != AUTHORITY)."""
        executor = ActionExecutor({"tp": 0.02})  # pas de flag passé
        decision = Decision("ADJUST_TP", {"tp_factor": 1.20}, "x", confidence=0.72)
        new_config, executed, msg = executor.execute(decision)

        assert executed is False
        assert new_config["tp"] == 0.02
        assert "not applied" in msg.lower()


class TestAdjustSlPassiveVsActive:
    def test_passive_does_not_mutate_config_and_not_executed(self):
        executor = ActionExecutor({"sl": 0.01}, adaptive_decision_feedback=False)
        decision = Decision(
            "ADJUST_SL", {"sl_factor": 0.80}, "mae high", confidence=0.68
        )
        new_config, executed, msg = executor.execute(decision)

        assert executed is False
        assert new_config["sl"] == 0.01
        assert "not applied" in msg.lower()

    def test_active_mutates_config_legacy_behavior(self):
        executor = ActionExecutor({"sl": 0.01}, adaptive_decision_feedback=True)
        decision = Decision(
            "ADJUST_SL", {"sl_factor": 0.80}, "mae high", confidence=0.68
        )
        new_config, executed, _msg = executor.execute(decision)

        assert executed is True
        assert new_config["sl"] == pytest.approx(0.008)


class TestApplyMetaPassiveVsActive:
    def test_passive_does_not_mutate_config_and_not_executed(self):
        executor = ActionExecutor(
            {"trailing_pct": 0.01}, adaptive_decision_feedback=False
        )
        decision = Decision(
            "APPLY_META",
            {"trailing_pct": 0.02, "confidence": 0.6},
            "meta suggestion",
            confidence=0.6,
        )
        new_config, executed, msg = executor.execute(decision)

        assert executed is False
        assert new_config["trailing_pct"] == 0.01
        assert "not applied" in msg.lower()

    def test_active_mutates_config_legacy_behavior(self):
        executor = ActionExecutor(
            {"trailing_pct": 0.01}, adaptive_decision_feedback=True
        )
        decision = Decision(
            "APPLY_META",
            {"trailing_pct": 0.02, "confidence": 0.6},
            "meta suggestion",
            confidence=0.6,
        )
        new_config, executed, _msg = executor.execute(decision)

        assert executed is True
        assert new_config["trailing_pct"] == 0.02


# ── Groupe C : jamais compté/loggé comme exécuté avec succès ─────────────────


class TestPassiveNeverLoggedAsExecuted:
    def test_execution_history_marks_passive_as_not_success(self):
        executor = ActionExecutor({"tp": 0.02}, adaptive_decision_feedback=False)
        decision = Decision("ADJUST_TP", {"tp_factor": 1.20}, "x", confidence=0.72)
        executor.execute(decision)

        entry = executor.execution_history[-1]
        assert entry["success"] is False
        assert entry["passive"] is True

    def test_decision_logger_records_executed_false_for_passive_orchestrator_run(
        self, tmp_path
    ):
        log_file = tmp_path / "decisions.jsonl"
        orchestrator = AutoDecisionOrchestrator(
            {"tp": 0.02, "sl": 0.01, "position_size": 0.1, "trading_enabled": True},
            log_file=str(log_file),
            adaptive_decision_feedback=False,
        )
        metrics = {"efficiency": 0.40, "mae_pct": -0.01}
        risk_state = {"drawdown": 0.01, "loss_streak": 0}

        new_config, decision, executed = orchestrator.run_decision_cycle(
            metrics, risk_state
        )

        assert decision.action == "ADJUST_TP"
        assert executed is False
        assert new_config["tp"] == 0.02

        history = orchestrator.logger.get_decision_history(1)
        assert history[-1]["executed"] is False


# ── Groupe D : S-02 — sous-systèmes déjà acceptés, non régressés ─────────────


class TestS02SubsystemsUntouched:
    def test_mistake_memory_module_importable(self):
        import quant_hedge_ai.agents.intelligence.mistake_memory  # noqa: F401

    def test_meta_learner_module_importable(self):
        import tracker_system.meta_learner  # noqa: F401

    def test_strategy_memory_module_importable(self):
        import quant_hedge_ai.ai_evolution.strategy_memory  # noqa: F401

    def test_strategy_ranker_module_importable(self):
        import quant_hedge_ai.ai_evolution.strategy_ranker  # noqa: F401


# ── Groupe E : câblage structurel dans core/advisor_loop.py ──────────────────


class TestAdvisorLoopSystemControllerWiring:
    def _read_source(self) -> str:
        src = Path(__file__).parent.parent / "core" / "advisor_loop.py"
        return src.read_text(encoding="utf-8")

    def test_orchestrator_receives_adaptive_decision_feedback_flag(self):
        source = self._read_source()
        assert "adaptive_decision_feedback=FEATURE_ADAPTIVE_DECISION_FEEDBACK" in source

    def test_adjust_tp_mutation_gated_behind_flag(self):
        source = self._read_source()
        idx = source.index('elif decision.action == "ADJUST_TP":')
        window = source[idx : idx + 800]
        assert "if FEATURE_ADAPTIVE_DECISION_FEEDBACK:" in window
        assert "recommandation contrefactuelle" in window

    def test_adjust_sl_mutation_gated_behind_flag(self):
        source = self._read_source()
        idx = source.index('elif decision.action == "ADJUST_SL":')
        window = source[idx : idx + 800]
        assert "if FEATURE_ADAPTIVE_DECISION_FEEDBACK:" in window
        assert "recommandation contrefactuelle" in window

    def test_reduce_risk_remains_unconditional(self):
        source = self._read_source()
        idx = source.index('if decision.action == "REDUCE_RISK":')
        window = source[idx : idx + 400]
        assert "FEATURE_ADAPTIVE_DECISION_FEEDBACK" not in window

    def test_resume_trading_remains_unconditional(self):
        source = self._read_source()
        idx = source.index('elif decision.action == "RESUME_TRADING":')
        window = source[idx : idx + 300]
        assert "FEATURE_ADAPTIVE_DECISION_FEEDBACK" not in window
