"""Tests GlobalRiskGate — checklist pré-trade en 5 conditions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.decision_packet import (
    ConvictionLevel,
    DecisionPacket,
    DecisionSide,
    DecisionState,
    MarketRegime,
)
from quant_hedge_ai.agents.risk.global_risk_gate import GateResult, GlobalRiskGate
from quant_hedge_ai.agents.risk.session_guard import SessionGuard

# ── Helpers ───────────────────────────────────────────────────────────────────


def _signal(
    score: int = 80,
    confirmed: bool = True,
    regime: str = "bull_trend",
    signal: str = "BUY",
    symbol: str = "BTCUSDT",
):
    s = MagicMock()
    s.score = score
    s.confirmed = confirmed
    s.regime = regime
    s.signal = signal
    s.symbol = symbol
    return s


@pytest.fixture
def gate():
    return GlobalRiskGate(min_signal_score=70, require_confirmed=True)


# ── Tests GateResult ──────────────────────────────────────────────────────────


class TestGateResult:
    def test_allowed_true_summary(self, gate):
        r = gate.check(_signal())
        assert r.allowed is True
        assert "PASS" in r.summary()

    def test_as_dict_keys(self, gate):
        r = gate.check(_signal())
        d = r.as_dict()
        for k in ("allowed", "conditions", "failed", "warnings"):
            assert k in d

    def test_summary_contains_failed(self, gate):
        r = gate.check(_signal(score=40))
        assert "BLOCK" in r.summary()
        assert "signal_score" in r.summary()


# ── Tests condition 1 : session_active ───────────────────────────────────────


class TestSessionCondition:
    def test_no_session_guard_passes(self, gate):
        r = gate.check(_signal())
        assert r.conditions["session_active"] is True

    def test_active_session_passes(self):
        guard = SessionGuard()
        guard.start_session(10_000.0)
        gate = GlobalRiskGate(session_guard=guard)
        r = gate.check(_signal(), order_size_usd=500.0)
        assert r.conditions["session_active"] is True

    def test_halted_session_blocks(self):
        guard = SessionGuard()
        guard.start_session(10_000.0)
        guard._state.halted = True
        guard._state.halt_reason = "test_halt"
        gate = GlobalRiskGate(session_guard=guard)
        r = gate.check(_signal(), order_size_usd=500.0)
        assert r.conditions["session_active"] is False
        assert "session_active" in r.failed

    def test_oversized_order_blocks_session(self):
        guard = SessionGuard(max_order_size_usd=1000.0)
        guard.start_session(10_000.0)
        gate = GlobalRiskGate(session_guard=guard)
        r = gate.check(_signal(), order_size_usd=5000.0)
        assert r.conditions["session_active"] is False


# ── Tests condition 2 : drawdown_ok ──────────────────────────────────────────


class TestDrawdownCondition:
    def test_zero_drawdown_passes(self, gate):
        r = gate.check(_signal(), portfolio_drawdown=0.0)
        assert r.conditions["drawdown_ok"] is True

    def test_small_drawdown_passes(self, gate):
        r = gate.check(_signal(), portfolio_drawdown=0.05)
        assert r.conditions["drawdown_ok"] is True

    def test_above_max_drawdown_blocks(self):
        gate = GlobalRiskGate(max_portfolio_drawdown=0.10)
        r = gate.check(_signal(), portfolio_drawdown=0.15)
        assert r.conditions["drawdown_ok"] is False
        assert "drawdown_ok" in r.failed

    def test_near_max_drawdown_warning(self):
        gate = GlobalRiskGate(max_portfolio_drawdown=0.10)
        r = gate.check(_signal(), portfolio_drawdown=0.08)  # 80% du max
        assert len(r.warnings) > 0
        assert any("Drawdown" in w for w in r.warnings)

    def test_drawdown_guard_integrated(self):
        from quant_hedge_ai.agents.risk.drawdown_guard import DrawdownGuard

        dg = DrawdownGuard()
        gate = GlobalRiskGate(drawdown_guard=dg, max_portfolio_drawdown=0.5)
        # Drawdown de 40% → DrawdownGuard réduit la taille à 0.1 → BLOCK
        r = gate.check(_signal(), portfolio_drawdown=0.40)
        assert r.conditions["drawdown_ok"] is False


# ── Tests condition 3 : signal_score ─────────────────────────────────────────


class TestSignalScoreCondition:
    def test_score_above_min_passes(self, gate):
        r = gate.check(_signal(score=75))
        assert r.conditions["signal_score"] is True

    def test_score_exactly_at_min_passes(self, gate):
        # sideways regime threshold (66) < min_signal_score (70), so floor=70 applies
        r = gate.check(_signal(score=70, regime="sideways"))
        assert r.conditions["signal_score"] is True

    def test_score_below_min_blocks(self, gate):
        r = gate.check(_signal(score=65))
        assert r.conditions["signal_score"] is False
        assert any("signal_score" in f for f in r.failed)

    def test_custom_min_score(self):
        import unittest.mock as mock

        import quant_hedge_ai.agents.risk.global_risk_gate as _gate_mod

        gate = GlobalRiskGate(min_signal_score=85)
        with mock.patch.object(_gate_mod, "_regime_clf", None):
            r = gate.check(_signal(score=80))
        assert r.conditions["signal_score"] is False


# ── Tests condition 4 : signal_confirmed ─────────────────────────────────────


class TestSignalConfirmedCondition:
    def test_confirmed_true_passes(self, gate):
        r = gate.check(_signal(confirmed=True))
        assert r.conditions["signal_confirmed"] is True

    def test_unconfirmed_blocks_when_required(self, gate):
        r = gate.check(_signal(confirmed=False))
        assert r.conditions["signal_confirmed"] is False
        assert "signal_confirmed" in r.failed

    def test_unconfirmed_passes_when_not_required(self):
        gate = GlobalRiskGate(require_confirmed=False)
        r = gate.check(_signal(confirmed=False))
        assert r.conditions["signal_confirmed"] is True


# ── Tests condition 5 : regime_allowed ───────────────────────────────────────


class TestRegimeCondition:
    def test_normal_regime_passes(self, gate):
        r = gate.check(_signal(regime="bull_trend"))
        assert r.conditions["regime_allowed"] is True

    def test_blacklisted_regime_blocks(self):
        gate = GlobalRiskGate(blacklisted_regimes={"flash_crash"})
        r = gate.check(_signal(regime="flash_crash"))
        assert r.conditions["regime_allowed"] is False
        assert any("regime_blacklisted" in f for f in r.failed)

    def test_legacy_check_blacklist_accepts_packet_regime_name(self):
        gate = GlobalRiskGate(blacklisted_regimes={"TREND_BULL"})
        r = gate.check(_signal(regime="bull_trend"))
        assert r.conditions["regime_allowed"] is False
        assert any("regime_blacklisted" in f for f in r.failed)

    def test_packet_check_blacklist_accepts_legacy_regime_name(self):
        gate = GlobalRiskGate(blacklisted_regimes={"flash_crash"})
        packet = DecisionPacket(
            symbol="BTCUSDT",
            side=DecisionSide.LONG,
            confidence=90.0,
            regime=MarketRegime.VOLATILE,
            conviction=ConvictionLevel.HIGH,
            lifecycle_state=DecisionState.CONTEXT_ENRICHED,
            metadata={"mtf_confirmed": True},
        )
        r = gate.check_packet(packet)
        assert r.conditions["regime_allowed"] is False
        assert any("regime_blacklisted" in f for f in r.failed)
        assert packet.lifecycle_state == DecisionState.REJECTED

    def test_blacklist_regime_method(self, gate):
        gate.blacklist_regime("high_volatility_regime")
        r = gate.check(_signal(regime="high_volatility_regime"))
        assert r.conditions["regime_allowed"] is False

    def test_unblacklist_regime_method(self, gate):
        gate.blacklist_regime("high_volatility_regime")
        gate.unblacklist_regime("high_volatility_regime")
        r = gate.check(_signal(regime="high_volatility_regime"))
        assert r.conditions["regime_allowed"] is True


# ── Tests multi-conditions échouées ──────────────────────────────────────────


class TestMultipleFailures:
    def test_all_conditions_can_fail(self):
        guard = SessionGuard()
        guard.start_session(10_000.0)
        guard._state.halted = True
        guard._state.halt_reason = "test"
        gate = GlobalRiskGate(
            session_guard=guard,
            min_signal_score=90,
            require_confirmed=True,
            blacklisted_regimes={"flash_crash"},
            max_portfolio_drawdown=0.02,
        )
        r = gate.check(
            _signal(score=40, confirmed=False, regime="flash_crash"),
            portfolio_drawdown=0.15,
            order_size_usd=99999.0,
        )
        assert r.allowed is False
        assert len(r.failed) >= 3

    def test_all_pass_gives_allowed_true(self):
        gate = GlobalRiskGate(min_signal_score=70, require_confirmed=True)
        r = gate.check(
            _signal(score=80, confirmed=True, regime="bull_trend"),
            portfolio_drawdown=0.02,
        )
        assert r.allowed is True
        assert r.failed == []


# ── Tests EventBus ────────────────────────────────────────────────────────────


class TestEventBus:
    def test_blocked_emits_event(self):
        gate = GlobalRiskGate(min_signal_score=90)
        with patch("event_bus.bus.EventBus.get") as mock_bus:
            mock_inst = MagicMock()
            mock_bus.return_value = mock_inst
            gate.check(_signal(score=40))
            assert mock_inst.emit.called

    def test_allowed_does_not_emit(self):
        gate = GlobalRiskGate(min_signal_score=70)
        with patch("event_bus.bus.EventBus.get") as mock_bus:
            mock_inst = MagicMock()
            mock_bus.return_value = mock_inst
            gate.check(_signal(score=80, confirmed=True))
            mock_inst.emit.assert_not_called()

    def test_eventbus_exception_does_not_crash(self):
        gate = GlobalRiskGate(min_signal_score=90)
        with patch("event_bus.bus.EventBus.get", side_effect=RuntimeError("bus error")):
            r = gate.check(_signal(score=40))
            assert isinstance(r, GateResult)


# ── Tests anti-bruit journal (2026-07-21 : ~43k WARNING/24h) ─────────────────


class TestLogNoise:
    def test_refus_routinier_en_debug_pas_warning(self, gate):
        """Un refus ordinaire ne pollue plus le journal en WARNING —
        sa visibilité passe par BLOCK STATS / gate_csv / rejection_store."""
        import quant_hedge_ai.agents.risk.global_risk_gate as grg

        with patch.object(grg, "_log") as log:
            gate.check(_signal(score=40))  # refus routinier
        assert log.debug.called
        assert not log.warning.called

    def test_pass_reste_en_info(self, gate):
        import quant_hedge_ai.agents.risk.global_risk_gate as grg

        with patch.object(grg, "_log") as log:
            gate.check(_signal())
        assert log.info.called

    def test_warn_throttled_deduplique(self):
        import quant_hedge_ai.agents.risk.global_risk_gate as grg

        grg._last_warn_ts.clear()
        with patch.object(grg, "_log") as log:
            grg._warn_throttled("drawdown proche")
            grg._warn_throttled("drawdown proche")  # même msg → supprimé
            grg._warn_throttled("autre alerte")  # msg différent → émis
        assert log.warning.call_count == 2

    def test_warn_throttled_reemet_apres_fenetre(self):
        import quant_hedge_ai.agents.risk.global_risk_gate as grg

        grg._last_warn_ts.clear()
        with patch.object(grg, "_log") as log:
            grg._warn_throttled("alerte")
            grg._last_warn_ts["alerte"] -= grg._WARN_THROTTLE_S + 1
            grg._warn_throttled("alerte")  # fenêtre expirée → réémis
        assert log.warning.call_count == 2
