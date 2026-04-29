"""Tests unitaires — OpsWatchdog (crash guard, order monitor, heartbeat, session)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

from supervision.ops_watchdog import OpsWatchdog


@pytest.fixture
def notifier():
    return MagicMock()


@pytest.fixture
def dog(notifier):
    return OpsWatchdog(notifier=notifier)


@pytest.fixture
def dog_no_notifier():
    return OpsWatchdog(notifier=None)


# ── Instantiation ──────────────────────────────────────────────────────────────


class TestInit:
    def test_default_no_notifier(self):
        w = OpsWatchdog()
        assert w._notifier is None

    def test_with_notifier(self, notifier):
        w = OpsWatchdog(notifier=notifier)
        assert w._notifier is notifier

    def test_heartbeat_disabled_by_default(self, dog):
        assert dog._heartbeat_interval == 0.0


# ── cycle_guard ────────────────────────────────────────────────────────────────


class TestCycleGuard:
    def test_no_exception_passes_through(self, dog):
        with dog.cycle_guard("test"):
            result = 42
        assert result == 42

    def test_exception_notifies_and_reraises(self, dog, notifier):
        with pytest.raises(ValueError, match="boom"):
            with dog.cycle_guard("cycle 1"):
                raise ValueError("boom")
        notifier.crash.assert_called_once()
        args = notifier.crash.call_args[0]
        assert "cycle 1" in args[0]
        assert isinstance(args[1], ValueError)

    def test_keyboard_interrupt_not_caught(self, dog, notifier):
        with pytest.raises(KeyboardInterrupt):
            with dog.cycle_guard("test"):
                raise KeyboardInterrupt
        notifier.crash.assert_not_called()

    def test_exception_without_notifier_still_reraises(self, dog_no_notifier):
        with pytest.raises(RuntimeError):
            with dog_no_notifier.cycle_guard("x"):
                raise RuntimeError("no notifier")

    def test_exception_without_notifier_no_crash(self, dog_no_notifier):
        try:
            with dog_no_notifier.cycle_guard("x"):
                raise RuntimeError("silent")
        except RuntimeError:
            pass  # notifier is None — no AttributeError expected


# ── on_order_result ────────────────────────────────────────────────────────────


class TestOnOrderResult:
    def test_rejected_non_duplicate_fires_alert(self, dog, notifier):
        dog.on_order_result(
            {
                "mode": "rejected",
                "symbol": "BTCUSDT",
                "action": "BUY",
                "size": 100.0,
                "error": "session halted",
            }
        )
        notifier.order_rejected.assert_called_once()

    def test_rejected_duplicate_suppressed(self, dog, notifier):
        dog.on_order_result(
            {
                "mode": "rejected",
                "symbol": "BTCUSDT",
                "action": "BUY",
                "size": 100.0,
                "error": "duplicate order within 30s window",
            }
        )
        notifier.order_rejected.assert_not_called()

    def test_live_failed_fires_alert(self, dog, notifier):
        dog.on_order_result(
            {
                "mode": "live_failed",
                "symbol": "ETHUSDT",
                "action": "SELL",
                "size": 50.0,
                "error": "timeout",
            }
        )
        notifier.live_order_failed.assert_called_once()

    def test_paper_mode_no_alert(self, dog, notifier):
        dog.on_order_result(
            {"mode": "paper", "symbol": "BTC", "action": "BUY", "size": 1.0}
        )
        notifier.order_rejected.assert_not_called()
        notifier.live_order_failed.assert_not_called()

    def test_empty_result_no_crash(self, dog, notifier):
        dog.on_order_result({})
        dog.on_order_result(None)
        notifier.order_rejected.assert_not_called()

    def test_no_notifier_no_crash_on_rejected(self, dog_no_notifier):
        dog_no_notifier.on_order_result(
            {
                "mode": "rejected",
                "symbol": "X",
                "action": "BUY",
                "size": 1.0,
                "error": "halt",
            }
        )

    def test_no_notifier_no_crash_on_live_failed(self, dog_no_notifier):
        dog_no_notifier.on_order_result(
            {
                "mode": "live_failed",
                "symbol": "X",
                "action": "BUY",
                "size": 1.0,
                "error": "net",
            }
        )


# ── on_session_guard ──────────────────────────────────────────────────────────


class TestOnSessionGuard:
    def _mock_guard(self, halted: bool, reason: str = ""):
        g = MagicMock()
        g.is_halted = halted
        g.halt_reason = reason
        g.state.return_value = {"halted": halted, "halt_reason": reason}
        return g

    def test_not_halted_no_notification(self, dog, notifier):
        g = self._mock_guard(False)
        dog.on_session_guard(g)
        notifier.session_halt.assert_not_called()

    def test_halted_fires_notification(self, dog, notifier):
        g = self._mock_guard(True, "drawdown exceeded")
        dog.on_session_guard(g)
        notifier.session_halt.assert_called_once()

    def test_same_halt_notified_only_once(self, dog, notifier):
        g = self._mock_guard(True, "same reason")
        dog.on_session_guard(g)
        dog.on_session_guard(g)
        assert notifier.session_halt.call_count == 1

    def test_different_halt_reason_notifies_again(self, dog, notifier):
        g1 = self._mock_guard(True, "reason A")
        g2 = self._mock_guard(True, "reason B")
        dog.on_session_guard(g1)
        dog.on_session_guard(g2)
        assert notifier.session_halt.call_count == 2

    def test_none_guard_no_crash(self, dog):
        dog.on_session_guard(None)

    def test_no_notifier_halted_no_crash(self, dog_no_notifier):
        g = self._mock_guard(True, "x")
        dog_no_notifier.on_session_guard(g)


# ── check_ws_staleness ─────────────────────────────────────────────────────────


class TestWsStaleness:
    def test_fresh_data_returns_false(self, dog, notifier):
        result = dog.check_ws_staleness("BTC", time.time(), threshold_seconds=120.0)
        assert result is False
        notifier.ws_disconnect.assert_not_called()

    def test_stale_data_returns_true(self, dog, notifier):
        old_ts = time.time() - 200.0
        result = dog.check_ws_staleness("BTC", old_ts, threshold_seconds=120.0)
        assert result is True
        notifier.ws_disconnect.assert_called_once()

    def test_stale_no_notifier_returns_true(self, dog_no_notifier):
        old_ts = time.time() - 200.0
        result = dog_no_notifier.check_ws_staleness(
            "BTC", old_ts, threshold_seconds=60.0
        )
        assert result is True

    def test_exactly_at_threshold_not_stale(self, dog):
        ts = time.time() - 119.9
        result = dog.check_ws_staleness("ETH", ts, threshold_seconds=120.0)
        assert result is False


# ── Heartbeat ──────────────────────────────────────────────────────────────────


class TestHeartbeat:
    def test_enable_sets_interval(self, dog):
        dog.enable_heartbeat(interval_seconds=60.0)
        assert dog._heartbeat_interval == 60.0

    def test_tick_before_interval_no_fire(self, dog, notifier):
        dog.enable_heartbeat(interval_seconds=9999.0)
        dog.tick_heartbeat()
        notifier.info.assert_not_called()

    def test_tick_after_interval_fires(self, dog, notifier):
        dog.enable_heartbeat(interval_seconds=1.0)
        dog._last_heartbeat = time.time() - 2.0
        dog.tick_heartbeat()
        notifier.info.assert_called_once()

    def test_tick_with_extra_text(self, dog, notifier):
        dog.enable_heartbeat(interval_seconds=1.0)
        dog._last_heartbeat = time.time() - 2.0
        dog.tick_heartbeat(extra="cycle 5")
        call_text = notifier.info.call_args[0][0]
        assert "cycle 5" in call_text

    def test_tick_disabled_heartbeat_no_fire(self, dog, notifier):
        dog.tick_heartbeat()
        notifier.info.assert_not_called()

    def test_no_notifier_heartbeat_no_crash(self, dog_no_notifier):
        dog_no_notifier.enable_heartbeat(1.0)
        dog_no_notifier._last_heartbeat = time.time() - 2.0
        dog_no_notifier.tick_heartbeat()


# ── Startup / shutdown ─────────────────────────────────────────────────────────


class TestStartupShutdown:
    def test_notify_startup_fires(self, dog, notifier):
        dog.notify_startup(mode="paper", symbols=["BTC/USDT"])
        notifier.info.assert_called_once()
        msg = notifier.info.call_args[0][0]
        assert "paper" in msg
        assert "BTC/USDT" in msg

    def test_notify_startup_no_symbols(self, dog, notifier):
        dog.notify_startup(mode="live")
        notifier.info.assert_called_once()

    def test_notify_shutdown_fires(self, dog, notifier):
        dog.notify_shutdown(reason="ctrl-c")
        notifier.info.assert_called_once()
        msg = notifier.info.call_args[0][0]
        assert "ctrl-c" in msg

    def test_no_notifier_startup_no_crash(self, dog_no_notifier):
        dog_no_notifier.notify_startup()

    def test_no_notifier_shutdown_no_crash(self, dog_no_notifier):
        dog_no_notifier.notify_shutdown()
