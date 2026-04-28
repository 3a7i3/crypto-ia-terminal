"""Tests unitaires — OpsNotifier + OpsWatchdog."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from supervision.notifications.ops_notifier import OpsNotifier
from supervision.ops_watchdog import OpsWatchdog

# ── Helpers ───────────────────────────────────────────────────────────────────


def _notifier_with_mock() -> tuple[OpsNotifier, MagicMock]:
    """Retourne un OpsNotifier branché sur un TelegramNotifier mocké."""
    mock_tg = MagicMock()
    mock_tg.notify.return_value = True
    n = OpsNotifier.__new__(OpsNotifier)
    n._token = "tok"
    n._chat_id = "chat"
    n._cooldown = 0.0  # pas de rate-limiting dans les tests
    n._last_sent = {}
    n._notifier = mock_tg
    return n, mock_tg


# ── OpsNotifier — mode silencieux ─────────────────────────────────────────────


class TestOpsNotifierSilent:
    def setup_method(self):
        self.n = OpsNotifier(bot_token="", chat_id="")

    def test_not_enabled(self):
        assert not self.n.enabled

    def test_crash_no_exception(self):
        self.n.crash("ctx", ValueError("boom"))

    def test_session_halt_no_exception(self):
        self.n.session_halt("drawdown 6%")

    def test_session_halt_with_state(self):
        self.n.session_halt(
            "drawdown 6%",
            {
                "drawdown_pct": 6.0,
                "loss_pct": 2.0,
                "consecutive_losses": 1,
                "total_trades": 5,
            },
        )

    def test_ws_disconnect_no_exception(self):
        self.n.ws_disconnect("BTC/USDT", 90.0)

    def test_order_rejected_no_exception(self):
        self.n.order_rejected("BTC/USDT", "BUY", 0.1, "too large")

    def test_live_order_failed_no_exception(self):
        self.n.live_order_failed("BTC/USDT", "BUY", "InsufficientFunds")

    def test_info_no_exception(self):
        self.n.info("test message")

    def test_send_returns_false(self):
        assert self.n._send("crash", "msg") is False


# ── OpsNotifier — envoi réel (Telegram mocké) ─────────────────────────────────


class TestOpsNotifierSend:
    def test_enabled_when_token_set(self):
        n, _ = _notifier_with_mock()
        assert n.enabled

    def test_crash_calls_notify(self):
        n, mock_tg = _notifier_with_mock()
        n.crash("main loop", RuntimeError("oops"))
        mock_tg.notify.assert_called_once()
        msg = mock_tg.notify.call_args[0][0]
        assert "CRASH" in msg
        assert "main loop" in msg

    def test_session_halt_calls_notify(self):
        n, mock_tg = _notifier_with_mock()
        n.session_halt(
            "drawdown 7%",
            {
                "drawdown_pct": 7.0,
                "loss_pct": 3.0,
                "consecutive_losses": 2,
                "total_trades": 10,
            },
        )
        mock_tg.notify.assert_called_once()
        msg = mock_tg.notify.call_args[0][0]
        assert "HALT" in msg
        assert "drawdown 7%" in msg

    def test_session_halt_without_state(self):
        n, mock_tg = _notifier_with_mock()
        n.session_halt("consecutive losses")
        mock_tg.notify.assert_called_once()

    def test_ws_disconnect_calls_notify(self):
        n, mock_tg = _notifier_with_mock()
        n.ws_disconnect("ETH/USDT", stale_seconds=150.0)
        mock_tg.notify.assert_called_once()
        msg = mock_tg.notify.call_args[0][0]
        assert "ETH/USDT" in msg
        assert "150" in msg

    def test_order_rejected_calls_notify(self):
        n, mock_tg = _notifier_with_mock()
        n.order_rejected("SOL/USDT", "SELL", 5.0, "taille maximale dépassée")
        mock_tg.notify.assert_called_once()
        msg = mock_tg.notify.call_args[0][0]
        assert "SOL/USDT" in msg
        assert "REJECTED" in msg

    def test_live_order_failed_calls_notify(self):
        n, mock_tg = _notifier_with_mock()
        n.live_order_failed("BTC/USDT", "BUY", "InsufficientFunds")
        mock_tg.notify.assert_called_once()
        msg = mock_tg.notify.call_args[0][0]
        assert "LIVE_FAIL" in msg
        assert "InsufficientFunds" in msg

    def test_info_calls_notify(self):
        n, mock_tg = _notifier_with_mock()
        n.info("bot démarré")
        mock_tg.notify.assert_called_once()

    def test_failed_send_returns_false(self):
        n, mock_tg = _notifier_with_mock()
        mock_tg.notify.return_value = False
        result = n._send("crash", "msg")
        assert result is False


# ── OpsNotifier — rate-limiting ───────────────────────────────────────────────


class TestOpsNotifierRateLimiting:
    def test_same_event_rate_limited(self):
        n, mock_tg = _notifier_with_mock()
        n._cooldown = 60.0
        n.crash("ctx", ValueError("boom"))
        n.crash("ctx", ValueError("boom2"))
        assert mock_tg.notify.call_count == 1

    def test_different_event_not_rate_limited(self):
        n, mock_tg = _notifier_with_mock()
        n._cooldown = 60.0
        n.crash("ctx", ValueError("boom"))
        n.session_halt("drawdown")
        assert mock_tg.notify.call_count == 2

    def test_cooldown_zero_allows_resend(self):
        n, mock_tg = _notifier_with_mock()
        n._cooldown = 0.0
        n.crash("ctx", ValueError("1"))
        n.crash("ctx", ValueError("2"))
        assert mock_tg.notify.call_count == 2

    def test_cooldown_expires_allows_resend(self):
        n, mock_tg = _notifier_with_mock()
        n._cooldown = 0.05
        n.crash("ctx", ValueError("1"))
        time.sleep(0.1)
        n.crash("ctx", ValueError("2"))
        assert mock_tg.notify.call_count == 2

    def test_from_env_no_token(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        n = OpsNotifier.from_env()
        assert not n.enabled


# ── OpsWatchdog ───────────────────────────────────────────────────────────────


class TestOpsWatchdog:
    def setup_method(self):
        self.mock_notifier = MagicMock()
        self.w = OpsWatchdog(notifier=self.mock_notifier)

    # ── on_order_result ───────────────────────────────────────────────────────

    def test_paper_order_no_alert(self):
        self.w.on_order_result(
            {"mode": "paper", "symbol": "BTC/USDT", "action": "BUY", "size": 0.1}
        )
        self.mock_notifier.order_rejected.assert_not_called()
        self.mock_notifier.live_order_failed.assert_not_called()

    def test_live_order_no_alert(self):
        self.w.on_order_result(
            {"mode": "live", "symbol": "BTC/USDT", "action": "BUY", "size": 0.1}
        )
        self.mock_notifier.live_order_failed.assert_not_called()

    def test_rejection_non_duplicate_alerts(self):
        self.w.on_order_result(
            {
                "mode": "rejected",
                "symbol": "BTC/USDT",
                "action": "BUY",
                "size": 500.0,
                "error": "order too large",
            }
        )
        self.mock_notifier.order_rejected.assert_called_once()

    def test_rejection_duplicate_no_alert(self):
        self.w.on_order_result(
            {
                "mode": "rejected",
                "symbol": "BTC/USDT",
                "action": "BUY",
                "size": 0.1,
                "error": "duplicate within 30s window",
            }
        )
        self.mock_notifier.order_rejected.assert_not_called()

    def test_live_failed_alerts(self):
        self.w.on_order_result(
            {
                "mode": "live_failed",
                "symbol": "BTC/USDT",
                "action": "BUY",
                "size": 0.1,
                "error": "InsufficientFunds",
            }
        )
        self.mock_notifier.live_order_failed.assert_called_once()

    def test_none_result_ignored(self):
        self.w.on_order_result(None)  # ne doit pas planter
        self.w.on_order_result({})

    # ── on_session_guard ──────────────────────────────────────────────────────

    def test_not_halted_guard_no_alert(self):
        from quant_hedge_ai.agents.risk.session_guard import SessionGuard

        g = SessionGuard()
        g.start_session(1000.0)
        self.w.on_session_guard(g)
        self.mock_notifier.session_halt.assert_not_called()

    def test_halted_guard_alerts(self):
        from quant_hedge_ai.agents.risk.session_guard import SessionGuard

        g = SessionGuard(
            max_consecutive_losses=1, max_session_drawdown=0.99, max_session_loss=0.99
        )
        g.start_session(1000.0)
        g.record_trade(-10.0, 990.0)
        assert g.is_halted
        self.w.on_session_guard(g)
        self.mock_notifier.session_halt.assert_called_once()

    def test_same_halt_not_alerted_twice(self):
        from quant_hedge_ai.agents.risk.session_guard import SessionGuard

        g = SessionGuard(
            max_consecutive_losses=1, max_session_drawdown=0.99, max_session_loss=0.99
        )
        g.start_session(1000.0)
        g.record_trade(-10.0, 990.0)
        self.w.on_session_guard(g)
        self.w.on_session_guard(g)
        assert self.mock_notifier.session_halt.call_count == 1

    def test_none_guard_ignored(self):
        self.w.on_session_guard(None)  # ne doit pas planter

    # ── check_ws_staleness ────────────────────────────────────────────────────

    def test_fresh_data_returns_false(self):
        result = self.w.check_ws_staleness(
            "BTC/USDT", time.time() - 10, threshold_seconds=120.0
        )
        assert result is False
        self.mock_notifier.ws_disconnect.assert_not_called()

    def test_stale_data_returns_true(self):
        result = self.w.check_ws_staleness(
            "BTC/USDT", time.time() - 200, threshold_seconds=120.0
        )
        assert result is True
        self.mock_notifier.ws_disconnect.assert_called_once()

    def test_stale_data_passes_symbol(self):
        self.w.check_ws_staleness(
            "ETH/USDT", time.time() - 200, threshold_seconds=120.0
        )
        call_args = self.mock_notifier.ws_disconnect.call_args[0]
        assert call_args[0] == "ETH/USDT"

    # ── heartbeat ─────────────────────────────────────────────────────────────

    def test_heartbeat_disabled_by_default(self):
        self.w.tick_heartbeat()
        self.mock_notifier.info.assert_not_called()

    def test_heartbeat_fires_after_interval(self):
        self.w.enable_heartbeat(interval_seconds=0.05)
        time.sleep(0.1)
        self.w.tick_heartbeat("cycle=1")
        self.mock_notifier.info.assert_called_once()

    def test_heartbeat_not_fired_before_interval(self):
        self.w.enable_heartbeat(interval_seconds=9999.0)
        self.w.tick_heartbeat()
        self.mock_notifier.info.assert_not_called()

    # ── notify_startup / shutdown ─────────────────────────────────────────────

    def test_notify_startup_calls_info(self):
        self.w.notify_startup(mode="paper", symbols=["BTC/USDT", "ETH/USDT"])
        self.mock_notifier.info.assert_called_once()
        msg = self.mock_notifier.info.call_args[0][0]
        assert "paper" in msg
        assert "BTC/USDT" in msg

    def test_notify_shutdown_calls_info(self):
        self.w.notify_shutdown("test fin")
        self.mock_notifier.info.assert_called_once()
        msg = self.mock_notifier.info.call_args[0][0]
        assert "test fin" in msg

    # ── from_env ──────────────────────────────────────────────────────────────

    def test_from_env_creates_watchdog(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        w = OpsWatchdog.from_env()
        assert isinstance(w, OpsWatchdog)
        assert w._notifier is not None

    # ── cycle_guard ───────────────────────────────────────────────────────────

    def test_cycle_guard_no_exception_passes(self):
        with self.w.cycle_guard("test cycle"):
            x = 1 + 1
        assert x == 2

    def test_cycle_guard_notifies_on_exception(self):
        n, mock_tg = _notifier_with_mock()
        n._cooldown = 0.0
        w = OpsWatchdog(notifier=n)
        with pytest.raises(ValueError):
            with w.cycle_guard("test"):
                raise ValueError("boom")
        mock_tg.notify.assert_called_once()
        msg = mock_tg.notify.call_args[0][0]
        assert "CRASH" in msg

    def test_cycle_guard_reraises(self):
        with pytest.raises(RuntimeError, match="test_error"):
            with self.w.cycle_guard("test"):
                raise RuntimeError("test_error")

    def test_cycle_guard_does_not_catch_keyboard_interrupt(self):
        with pytest.raises(KeyboardInterrupt):
            with self.w.cycle_guard("test"):
                raise KeyboardInterrupt()
        self.mock_notifier.crash.assert_not_called()
