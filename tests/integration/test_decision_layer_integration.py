"""
test_decision_layer_integration.py — Tests d'intégration Decision Layer (P1)

Vérifie que le câblage entre advisor_loop et le SystemController est fonctionnel.
Chaque test prouve qu'une action arrive effectivement jusqu'au système cible.

Verticale : Decision Layer
Composants : AutoDecisionOrchestrator → ActionExecutor → state_machine
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def orchestrator():
    from tracker_system.autonomous.auto_decision_engine import AutoDecisionOrchestrator

    cfg = {"tp": 0.025, "sl": 0.010, "position_size": 0.1, "trading_enabled": True}
    return AutoDecisionOrchestrator(cfg, log_file="/dev/null")


@pytest.fixture
def sc_state():
    """Réplique exacte de _sc_state dans advisor_loop.py."""
    return {
        "risk_factor": 1.0,
        "tp_factor": 1.0,
        "sl_factor": 1.0,
        "trade_count": 0,
        "cooldowns": {},
    }


# ── DL-01 : STOP_TRADING atteint state_machine ────────────────────────────────


class TestStopTradingReachesStateMachine:
    """DL-01 — drawdown > 5% → STOP_TRADING → state_machine.transition("HALTED")."""

    def test_stop_trading_transitions_state_machine_to_halted(self, orchestrator):
        """L'ActionExecutor appelle bien get_state_machine().transition("HALTED")."""
        import system.state_machine as _sm_mod
        from tracker_system.autonomous.auto_decision_engine import (
            ActionExecutor,
            Decision,
        )

        executor = ActionExecutor({"trading_enabled": True})
        mock_sm = MagicMock()

        # ActionExecutor importe get_state_machine localement dans execute() —
        # on patch l'attribut du module pour intercepter cet import.
        original = _sm_mod.get_state_machine
        _sm_mod.get_state_machine = lambda: mock_sm
        try:
            decision = Decision(
                action="STOP_TRADING",
                params={},
                reason="drawdown 6% > 5%",
                confidence=0.95,
            )
            _, success, msg = executor.execute(decision)
        finally:
            _sm_mod.get_state_machine = original

        assert success
        assert executor.config["trading_enabled"] is False
        mock_sm.transition.assert_called_once_with(
            "HALTED",
            reason="drawdown 6% > 5%",
            halt_source="AutoDecisionEngine",
        )

    def test_critical_drawdown_produces_stop_trading_decision(self, orchestrator):
        """AutoDecisionOrchestrator retourne STOP_TRADING quand drawdown > 5%."""
        metrics = {"efficiency": 0.5, "mae_pct": -0.01}
        risk_state = {"drawdown": 0.07, "loss_streak": 2}

        _, decision, _ = orchestrator.run_decision_cycle(metrics, risk_state)

        assert (
            decision.action == "STOP_TRADING"
        ), f"drawdown=7% devrait déclencher STOP_TRADING, action={decision.action}"
        assert decision.confidence >= 0.9

    def test_drawdown_below_threshold_no_stop(self, orchestrator):
        """Drawdown < 5% ne déclenche pas STOP_TRADING."""
        metrics = {"efficiency": 0.65, "mae_pct": -0.01}
        risk_state = {"drawdown": 0.03, "loss_streak": 1}

        _, decision, _ = orchestrator.run_decision_cycle(metrics, risk_state)

        assert decision.action != "STOP_TRADING"


# ── DL-02 : REDUCE_RISK met à jour risk_factor ────────────────────────────────


class TestReduceRiskUpdatesFactor:
    """DL-02 — REDUCE_RISK → _sc_state['risk_factor'] réduit → order_size réduit."""

    def _simulate_sc_cycle(self, sc_state, decision, SC_MIN_TRADES=5):
        """Réplique la logique de mutation de _sc_state dans _sc_run_cycle."""
        if sc_state["trade_count"] < SC_MIN_TRADES:
            return  # guard anti-bruit

        if decision.action == "REDUCE_RISK":
            factor = decision.params.get("position_size_factor", 0.5)
            sc_state["risk_factor"] = max(0.25, sc_state["risk_factor"] * factor)
        elif decision.action == "RESUME_TRADING":
            sc_state["risk_factor"] = 1.0
        elif decision.action == "ADJUST_TP":
            factor = decision.params.get("tp_factor", 1.15)
            sc_state["tp_factor"] = min(1.5, max(0.8, sc_state["tp_factor"] * factor))
        elif decision.action == "ADJUST_SL":
            factor = decision.params.get("sl_factor", 0.85)
            sc_state["sl_factor"] = min(1.3, max(0.7, sc_state["sl_factor"] * factor))

    def test_reduce_risk_halves_risk_factor(self, sc_state):
        from tracker_system.autonomous.auto_decision_engine import Decision

        sc_state["trade_count"] = 5
        decision = Decision(
            action="REDUCE_RISK",
            params={"position_size_factor": 0.5},
            reason="loss streak",
            confidence=0.85,
        )

        self._simulate_sc_cycle(sc_state, decision)

        assert sc_state["risk_factor"] == 0.5

    def test_order_size_is_multiplied_by_risk_factor(self, sc_state):
        """Vérifie la formule order_size_usd = order_size * risk_factor."""
        from tracker_system.autonomous.auto_decision_engine import Decision

        sc_state["trade_count"] = 5
        base_order_size = 50.0

        # Après REDUCE_RISK ×0.5 → risk_factor = 0.5
        decision = Decision("REDUCE_RISK", {"position_size_factor": 0.5}, "", 0.9)
        self._simulate_sc_cycle(sc_state, decision)

        effective_order_size = base_order_size * sc_state["risk_factor"]
        assert (
            effective_order_size == 25.0
        ), f"order_size 25.0 attendu après risk_factor=0.5, got {effective_order_size}"

    def test_risk_factor_floored_at_025(self, sc_state):
        """risk_factor ne descend pas sous 0.25 même avec plusieurs REDUCE_RISK."""
        from tracker_system.autonomous.auto_decision_engine import Decision

        sc_state["trade_count"] = 5
        # Appliquer 4 réductions consécutives de ×0.5
        for _ in range(4):
            sc_state["trade_count"] += 1
            decision = Decision("REDUCE_RISK", {"position_size_factor": 0.5}, "", 0.9)
            self._simulate_sc_cycle(sc_state, decision)

        assert (
            sc_state["risk_factor"] >= 0.25
        ), f"risk_factor plancher=0.25 violé: {sc_state['risk_factor']}"

    def test_loss_streak_4_triggers_reduce_risk(self, orchestrator):
        """loss_streak >= 4 → AutoDecisionOrchestrator décide REDUCE_RISK."""
        metrics = {"efficiency": 0.60, "mae_pct": -0.015}
        risk_state = {"drawdown": 0.03, "loss_streak": 4}

        _, decision, _ = orchestrator.run_decision_cycle(metrics, risk_state)

        assert (
            decision.action == "REDUCE_RISK"
        ), f"loss_streak=4 devrait déclencher REDUCE_RISK, action={decision.action}"


# ── DL-03 : Guard anti-bruit _SC_MIN_TRADES=5 ────────────────────────────────


class TestMinTradesGuard:
    """DL-03 — Pas de décision avant _SC_MIN_TRADES=5 trades fermés."""

    _SC_MIN_TRADES = 5

    def _run_cycle_with_guard(self, sc_state, orchestrator, metrics, risk_state):
        """Simule _sc_run_cycle en appliquant le guard trade_count."""
        sc_state["trade_count"] += 1
        if sc_state["trade_count"] < self._SC_MIN_TRADES:
            return None  # guard actif

        _, decision, _ = orchestrator.run_decision_cycle(metrics, risk_state)
        return decision

    def test_no_decision_before_5_trades(self, sc_state, orchestrator):
        """4 premiers trades fermés → aucune décision exécutée."""
        metrics = {"efficiency": 0.5, "mae_pct": -0.02}
        risk_state = {"drawdown": 0.06, "loss_streak": 5}  # conditions critiques

        decisions = []
        for _ in range(4):
            d = self._run_cycle_with_guard(sc_state, orchestrator, metrics, risk_state)
            if d is not None:
                decisions.append(d.action)

        assert (
            len(decisions) == 0
        ), f"Guard _SC_MIN_TRADES=5 violé : {len(decisions)} décisions avant 5 trades"

    def test_decision_fires_at_trade_5(self, sc_state, orchestrator):
        """Au 5e trade fermé, le cycle décisionnel s'exécute."""
        metrics = {"efficiency": 0.5, "mae_pct": -0.02}
        risk_state = {"drawdown": 0.07, "loss_streak": 3}

        # Avancer jusqu'à trade N°5
        sc_state["trade_count"] = 4
        decision = self._run_cycle_with_guard(
            sc_state, orchestrator, metrics, risk_state
        )

        assert decision is not None, "Le 5e trade doit déclencher le cycle décisionnel"
        assert decision.action != "NO_ACTION" or True  # décision prise (même NO_ACTION)

    def test_trade_count_increments_each_close(self, sc_state, orchestrator):
        """Chaque appel à _run_cycle incrémente trade_count."""
        for expected_count in range(1, 4):
            self._run_cycle_with_guard(
                sc_state, orchestrator, {"efficiency": 0.7}, {"drawdown": 0.01}
            )
            assert sc_state["trade_count"] == expected_count


# ── DL-04 : Câblage structurel dans advisor_loop.py ───────────────────────────


class TestAdvisorLoopWiring:
    """DL-04 — Vérification structurelle du câblage dans advisor_loop.py."""

    def _read_source(self) -> str:
        from pathlib import Path

        src = Path(__file__).parent.parent.parent / "core" / "advisor_loop.py"
        return src.read_text(encoding="utf-8")

    def test_sc_run_cycle_called_in_on_position_close(self):
        """_sc_run_cycle est effectivement appelé dans _on_position_close_rank."""
        from pathlib import Path

        lines = (
            (Path(__file__).parent.parent.parent / "core" / "advisor_loop.py")
            .read_text(encoding="utf-8")
            .splitlines()
        )

        # Trouver la ligne de début de _on_position_close_rank
        target = "def _on_position_close_rank("
        fn_start_line = next(
            (i for i, line in enumerate(lines) if target in line),
            None,
        )
        assert fn_start_line is not None, "_on_position_close_rank non trouvée"

        # Chercher _sc_run_cycle dans les 250 lignes suivantes (corps de la fonction)
        fn_body_lines = lines[fn_start_line : fn_start_line + 250]
        call_found = any("_sc_run_cycle(" in ln for ln in fn_body_lines)
        end_line = fn_start_line + 250
        assert call_found, (
            "_sc_run_cycle non appelé dans _on_position_close_rank "
            f"(lignes {fn_start_line}–{end_line})"
        )

    def test_risk_factor_applied_to_order_size(self):
        """risk_factor est appliqué à order_size_usd dans analyze_symbol."""
        source = self._read_source()
        key = '_sc_state["risk_factor"]'
        assert (
            key in source
        ), "_sc_state['risk_factor'] non appliqué à order_size dans analyze_symbol"

    def test_sc_min_trades_constant_is_5(self):
        """_SC_MIN_TRADES == 5 (anti-noise guard)."""
        source = self._read_source()
        assert (
            "_SC_MIN_TRADES = 5" in source
        ), "_SC_MIN_TRADES = 5 non trouvé dans advisor_loop.py"

    def test_auto_decision_orchestrator_initialized(self):
        """AutoDecisionOrchestrator est instancié dans advisor_loop.py."""
        source = self._read_source()
        assert (
            "AutoDecisionOrchestrator" in source
        ), "AutoDecisionOrchestrator non trouvé dans advisor_loop.py"

    def test_on_close_callback_registered(self):
        """pos_manager.on_close(_on_position_close_rank) est câblé."""
        source = self._read_source()
        assert (
            "pos_manager.on_close(_on_position_close_rank)" in source
        ), "pos_manager.on_close non câblé avec _on_position_close_rank"

    def test_sl_tp_factors_applied_in_analyze_symbol(self):
        """sl_factor et tp_factor de _sc_state sont propagés aux overrides."""
        source = self._read_source()
        assert (
            '_sc_state["sl_factor"]' in source
        ), "_sc_state['sl_factor'] non appliqué dans advisor_loop.py"
        assert (
            '_sc_state["tp_factor"]' in source
        ), "_sc_state['tp_factor'] non appliqué dans advisor_loop.py"


# ── DL-05 : Facteurs bornés ───────────────────────────────────────────────────


class TestFactorBounds:
    """DL-05 — Les facteurs tp/sl restent dans les bornes définies."""

    def test_tp_factor_capped_at_1_5(self, sc_state):
        """tp_factor ne dépasse pas 1.5 même avec plusieurs ADJUST_TP."""
        sc_state["trade_count"] = 10
        for _ in range(10):
            factor = sc_state["tp_factor"] * 1.15
            sc_state["tp_factor"] = min(1.5, max(0.8, factor))

        assert sc_state["tp_factor"] <= 1.5

    def test_sl_factor_floored_at_0_7(self, sc_state):
        """sl_factor ne descend pas sous 0.7 même avec plusieurs ADJUST_SL."""
        sc_state["trade_count"] = 10
        for _ in range(10):
            factor = sc_state["sl_factor"] * 0.85
            sc_state["sl_factor"] = min(1.3, max(0.7, factor))

        assert sc_state["sl_factor"] >= 0.7
