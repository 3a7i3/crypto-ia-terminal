"""
OpsNotifier — typed Telegram alerts for operational events.

Provides one method per event type so call sites are readable.
Silently no-ops if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set.
Rate-limits: same event_type not re-sent within `cooldown_seconds` (default 60s).

Usage:
    notifier = OpsNotifier.from_env()
    notifier.crash("main loop", exc)
    notifier.session_halt("drawdown 6% >= 5%", state)
    notifier.ws_disconnect("BTC/USDT", stale_seconds=90)
    notifier.order_rejected("BTC/USDT", "BUY", 0.1, "duplicate within 30s")
    notifier.live_order_failed("BTC/USDT", "BUY", error="InsufficientFunds")
"""

from __future__ import annotations

import os
import time
import traceback

from observability.json_logger import get_logger

_log = get_logger("supervision.notifications.ops_notifier")
_ICON = {
    "crash": "[CRASH]",
    "session_halt": "[HALT]",
    "ws_disconnect": "[WS_DOWN]",
    "order_rejected": "[REJECTED]",
    "live_failed": "[LIVE_FAIL]",
    "info": "[INFO]",
}


class OpsNotifier:
    """
    Sends Telegram notifications for critical operational events.

    Graceful degradation: if no bot token is configured, all methods
    are silent no-ops — the system still runs normally.
    """

    def __init__(
        self,
        bot_token: str = "",
        chat_id: str = "",
        cooldown_seconds: float = 60.0,
    ) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._cooldown = cooldown_seconds
        self._last_sent: dict[str, float] = {}
        self._notifier = None
        if bot_token and chat_id:
            try:
                from supervision.notifications.telegram_notifier import TelegramNotifier

                self._notifier = TelegramNotifier(bot_token, chat_id)
                _log.info("[OpsNotifier] Telegram configured — alerts enabled")
            except Exception as exc:
                _log.warning("[OpsNotifier] Could not init TelegramNotifier: %s", exc)

    @classmethod
    def from_env(cls) -> "OpsNotifier":
        """Build from TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars."""
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            cooldown_seconds=float(os.getenv("OPS_ALERT_COOLDOWN", "60")),
        )

    @property
    def enabled(self) -> bool:
        return self._notifier is not None

    # ── Typed event methods ────────────────────────────────────────────────────

    def crash(self, context: str, exc: BaseException) -> None:
        """Unhandled exception — sends traceback excerpt."""
        tb = traceback.format_exc()
        # Keep last 10 lines of traceback to stay within Telegram 4096 char limit
        tb_short = "\n".join(tb.splitlines()[-10:])
        self._send(
            "crash",
            f"{_ICON['crash']} BOT CRASH\n"
            f"Context : {context}\n"
            f"Error   : {type(exc).__name__}: {exc}\n"
            f"---\n{tb_short}",
        )

    def session_halt(self, reason: str, state: dict | None = None) -> None:
        """SessionGuard triggered a trading halt."""
        lines = [f"{_ICON['session_halt']} SESSION HALTED", f"Reason : {reason}"]
        if state:
            lines += [
                f"Drawdown : {state.get('drawdown_pct', 0):.2f}%",
                f"Session loss : {state.get('loss_pct', 0):.2f}%",
                f"Consec losses : {state.get('consecutive_losses', 0)}",
                f"Trades : {state.get('total_trades', 0)}",
            ]
        self._send("session_halt", "\n".join(lines))

    def ws_disconnect(self, symbol: str, stale_seconds: float) -> None:
        """WebSocket / StreamBus data is stale."""
        self._send(
            "ws_disconnect",
            f"{_ICON['ws_disconnect']} WS DATA STALE\n"
            f"Symbol : {symbol}\n"
            f"Last data : {stale_seconds:.0f}s ago (threshold exceeded)",
        )

    def order_rejected(
        self,
        symbol: str,
        action: str,
        size: float,
        reason: str,
    ) -> None:
        """Order blocked by safety layer (dedup, guard, oversized)."""
        self._send(
            "order_rejected",
            f"{_ICON['order_rejected']} ORDER REJECTED\n"
            f"{action} {size:.4f} {symbol}\n"
            f"Reason : {reason}",
        )

    def live_order_failed(
        self,
        symbol: str,
        action: str,
        error: str,
    ) -> None:
        """Live order sent to exchange but returned an error."""
        self._send(
            "live_failed",
            f"{_ICON['live_failed']} LIVE ORDER FAILED\n"
            f"{action} {symbol}\n"
            f"Error : {error}",
        )

    def info(self, message: str, key: str = "info") -> None:
        """Generic informational alert (not rate-limited by default key)."""
        self._send(key, f"{_ICON['info']} {message}")

    # ── Core send + rate limiting ──────────────────────────────────────────────

    def _send(self, event_type: str, message: str) -> bool:
        if self._notifier is None:
            return False
        now = time.time()
        last = self._last_sent.get(event_type, 0.0)
        if (now - last) < self._cooldown:
            _log.debug(
                "[OpsNotifier] Rate-limited %s (%.0fs < cooldown %.0fs)",
                event_type,
                now - last,
                self._cooldown,
            )
            return False
        self._last_sent[event_type] = now
        ok = self._notifier.notify(message)
        if not ok:
            _log.warning("[OpsNotifier] Failed to send %s alert", event_type)
        return ok
