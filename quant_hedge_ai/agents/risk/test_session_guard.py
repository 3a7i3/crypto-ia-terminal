"""Tests unitaires — SessionGuard."""

from __future__ import annotations

import pytest

from quant_hedge_ai.agents.risk.session_guard import (
    OrderTooLargeError,
    SessionGuard,
    SessionHaltedError,
    SessionState,
)


@pytest.fixture
def guard():
    g = SessionGuard(
        max_session_drawdown=0.10,
        max_session_loss=0.05,
        max_consecutive_losses=3,
        max_order_size_usd=1000.0,
    )
    g.start_session(equity=10_000.0)
    return g


# ── SessionState ──────────────────────────────────────────────────────────────


class TestSessionState:
    def test_drawdown_zero_at_peak(self):
        s = SessionState(peak_equity=1000.0, current_equity=1000.0)
        assert s.drawdown == pytest.approx(0.0)

    def test_drawdown_calculation(self):
        s = SessionState(peak_equity=1000.0, current_equity=900.0)
        assert s.drawdown == pytest.approx(0.1)

    def test_drawdown_zero_equity(self):
        s = SessionState(peak_equity=0.0, current_equity=0.0)
        assert s.drawdown == pytest.approx(0.0)

    def test_loss_pct_calculation(self):
        s = SessionState(start_equity=1000.0, current_equity=950.0)
        assert s.loss_pct == pytest.approx(0.05)

    def test_loss_pct_zero_start(self):
        s = SessionState(start_equity=0.0, current_equity=100.0)
        assert s.loss_pct == pytest.approx(0.0)

    def test_as_dict_keys(self):
        s = SessionState(start_equity=1000.0, current_equity=1000.0)
        d = s.as_dict()
        assert "start_equity" in d
        assert "drawdown_pct" in d
        assert "consecutive_losses" in d
        assert "halted" in d


# ── start_session ─────────────────────────────────────────────────────────────


class TestStartSession:
    def test_resets_all_counters(self):
        g = SessionGuard()
        g.start_session(5000.0)
        g.record_trade(-100.0, 4900.0)
        g.start_session(6000.0)  # nouvelle session
        assert g.state()["consecutive_losses"] == 0
        assert g.state()["session_pnl"] == pytest.approx(0.0)
        assert not g.is_halted

    def test_sets_start_equity(self):
        g = SessionGuard()
        g.start_session(12345.0)
        assert g.state()["start_equity"] == pytest.approx(12345.0)


# ── check_order ───────────────────────────────────────────────────────────────


class TestCheckOrder:
    def test_valid_order_passes(self, guard):
        guard.check_order("BTC/USDT", "BUY", 500.0)  # pas d'exception

    def test_oversized_raises_order_too_large(self, guard):
        with pytest.raises(OrderTooLargeError) as exc_info:
            guard.check_order("BTC/USDT", "BUY", 1500.0)
        assert exc_info.value.size_usd == pytest.approx(1500.0)
        assert exc_info.value.limit_usd == pytest.approx(1000.0)

    def test_halted_session_raises_session_halted(self, guard):
        # Forcer le halt
        guard._state.halted = True
        guard._state.halt_reason = "test halt"
        with pytest.raises(SessionHaltedError) as exc_info:
            guard.check_order("BTC/USDT", "BUY", 100.0)
        assert "test halt" in str(exc_info.value)

    def test_halted_takes_priority_over_size(self, guard):
        guard._state.halted = True
        guard._state.halt_reason = "drawdown"
        with pytest.raises(SessionHaltedError):
            guard.check_order("BTC/USDT", "BUY", 9999.0)  # aussi trop grand


# ── record_trade ──────────────────────────────────────────────────────────────


class TestRecordTrade:
    def test_win_resets_consecutive_losses(self, guard):
        guard.record_trade(-50.0, 9950.0)
        guard.record_trade(-50.0, 9900.0)
        guard.record_trade(100.0, 10000.0)  # win → reset
        assert guard.state()["consecutive_losses"] == 0

    def test_session_pnl_accumulates(self, guard):
        guard.record_trade(-100.0, 9900.0)
        guard.record_trade(50.0, 9950.0)
        assert guard.state()["session_pnl"] == pytest.approx(-50.0)

    def test_peak_equity_tracked(self, guard):
        guard.record_trade(200.0, 10200.0)
        guard.record_trade(-100.0, 10100.0)
        # Peak = 10200, current = 10100 → drawdown = 100/10200
        assert guard.state()["drawdown_pct"] == pytest.approx(
            100.0 / 10200.0 * 100, rel=1e-3
        )

    def test_total_trades_counted(self, guard):
        guard.record_trade(10.0, 10010.0)
        guard.record_trade(-5.0, 10005.0)
        assert guard.state()["total_trades"] == 2


# ── Halt conditions ───────────────────────────────────────────────────────────


class TestHaltConditions:
    def test_halt_on_consecutive_losses(self):
        g = SessionGuard(
            max_consecutive_losses=3, max_session_drawdown=0.99, max_session_loss=0.99
        )
        g.start_session(1000.0)
        g.record_trade(-1.0, 999.0)
        g.record_trade(-1.0, 998.0)
        assert not g.is_halted
        g.record_trade(-1.0, 997.0)
        assert g.is_halted
        assert "consecutive" in g.halt_reason

    def test_halt_on_session_drawdown(self):
        g = SessionGuard(
            max_session_drawdown=0.05, max_session_loss=0.99, max_consecutive_losses=99
        )
        g.start_session(1000.0)
        g.record_trade(-60.0, 940.0)  # 6% drawdown > 5%
        assert g.is_halted
        assert "drawdown" in g.halt_reason

    def test_halt_on_session_loss(self):
        g = SessionGuard(
            max_session_drawdown=0.99, max_session_loss=0.03, max_consecutive_losses=99
        )
        g.start_session(1000.0)
        g.record_trade(-35.0, 965.0)  # 3.5% loss > 3%
        assert g.is_halted
        assert "session_loss" in g.halt_reason

    def test_no_halt_below_all_thresholds(self):
        g = SessionGuard(
            max_session_drawdown=0.10, max_session_loss=0.05, max_consecutive_losses=5
        )
        g.start_session(1000.0)
        g.record_trade(-30.0, 970.0)  # 3% perte < 5%
        g.record_trade(-10.0, 960.0)  # 4% perte < 5%
        assert not g.is_halted

    def test_halt_fires_once_not_twice(self):
        g = SessionGuard(
            max_consecutive_losses=2, max_session_drawdown=0.99, max_session_loss=0.99
        )
        g.start_session(1000.0)
        g.record_trade(-10.0, 990.0)
        g.record_trade(-10.0, 980.0)
        assert g.is_halted
        first_reason = g.halt_reason
        g.record_trade(-10.0, 970.0)  # troisième perte, halt déjà actif
        assert g.halt_reason == first_reason  # reason ne change pas

    def test_no_check_limits_if_already_halted(self):
        g = SessionGuard(
            max_consecutive_losses=2, max_session_drawdown=0.99, max_session_loss=0.99
        )
        g.start_session(1000.0)
        g._state.halted = True
        g._state.halt_reason = "manual"
        g.record_trade(-500.0, 500.0)  # ne doit pas changer la raison
        assert g.halt_reason == "manual"


# ── reset ─────────────────────────────────────────────────────────────────────


class TestReset:
    def test_reset_clears_halt(self):
        g = SessionGuard(
            max_consecutive_losses=2, max_session_drawdown=0.99, max_session_loss=0.99
        )
        g.start_session(1000.0)
        g.record_trade(-10.0, 990.0)
        g.record_trade(-10.0, 980.0)
        assert g.is_halted
        g.reset()
        assert not g.is_halted
        assert g.halt_reason == ""

    def test_reset_allows_orders_again(self):
        g = SessionGuard(
            max_consecutive_losses=2, max_session_drawdown=0.99, max_session_loss=0.99
        )
        g.start_session(1000.0)
        g.record_trade(-10.0, 990.0)
        g.record_trade(-10.0, 980.0)
        g.reset()
        g.check_order("BTC/USDT", "BUY", 100.0)  # ne doit pas lever

    def test_reset_clears_consecutive_losses(self):
        g = SessionGuard(
            max_consecutive_losses=5, max_session_drawdown=0.99, max_session_loss=0.99
        )
        g.start_session(1000.0)
        g.record_trade(-10.0, 990.0)
        g.record_trade(-10.0, 980.0)
        g.reset()
        assert g.state()["consecutive_losses"] == 0


# ── state() ───────────────────────────────────────────────────────────────────


class TestState:
    def test_state_returns_dict(self, guard):
        s = guard.state()
        assert isinstance(s, dict)

    def test_state_not_halted_initially(self, guard):
        assert guard.state()["halted"] is False
        assert guard.state()["halt_reason"] == ""

    def test_is_halted_property(self, guard):
        assert guard.is_halted is False
        guard._state.halted = True
        assert guard.is_halted is True
