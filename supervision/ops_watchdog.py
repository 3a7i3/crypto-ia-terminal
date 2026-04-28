"""
OpsWatchdog — operational monitoring hub.

Connects OpsNotifier to the live trading system.  Designed for zero-friction
wiring: drop one instance into main_v91 and call the appropriate hooks.

Features:
  - Crash guard   : wrap_cycle(fn) catches unhandled exceptions, notifies, re-raises
  - Order monitor : on_order_result(result) detects rejections / live failures
  - WS staleness  : check_ws_staleness(symbol, last_ts) notifies when data is old
  - Session halt  : on_session_guard(guard) detects halts, notifies once per halt
  - Heartbeat     : periodic "bot alive" ping (optional, opt-in)

Usage in main_v91.py:
    watchdog = OpsWatchdog.from_env()

    # In the cycle loop:
    with watchdog.cycle_guard("cycle N"):
        ...
        r = eng.create_order(...)
        watchdog.on_order_result(r)
        watchdog.on_session_guard(eng._guard)
        watchdog.check_ws_staleness("BTC/USDT", last_data_ts)
"""

from __future__ import annotations

import contextlib
import logging
import time

logger = logging.getLogger(__name__)


class OpsWatchdog:
    """Orchestrates all operational monitoring hooks."""

    def __init__(self, notifier=None) -> None:
        self._notifier = notifier
        # Track the last halt reason we already notified, to avoid re-firing
        self._notified_halt: str = ""
        self._session_start_ts: float = time.time()
        self._heartbeat_interval: float = 0.0  # 0 = disabled
        self._last_heartbeat: float = 0.0

    @classmethod
    def from_env(cls) -> "OpsWatchdog":
        """Build with OpsNotifier auto-loaded from environment variables."""
        from supervision.notifications.ops_notifier import OpsNotifier
        notifier = OpsNotifier.from_env()
        return cls(notifier=notifier)

    # ── Crash guard ───────────────────────────────────────────────────────────

    @contextlib.contextmanager
    def cycle_guard(self, context: str = "main cycle"):
        """
        Context manager — wraps a trading cycle.
        On unhandled exception: logs, notifies Telegram, re-raises.

        Usage:
            with watchdog.cycle_guard(f"cycle {n}"):
                ... # all cycle code here
        """
        try:
            yield
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logger.error("[OpsWatchdog] Unhandled exception in %s: %s", context, exc)
            if self._notifier:
                self._notifier.crash(context, exc)
            raise

    # ── Order result monitor ──────────────────────────────────────────────────

    def on_order_result(self, result: dict) -> None:
        """
        Inspect an ExecutionEngine order result and fire alerts if needed.
        Call after every create_order().
        """
        if not result:
            return
        mode = result.get("mode", "")
        symbol = result.get("symbol", "?")
        action = result.get("action", "?")
        size = float(result.get("size", 0.0))

        if mode == "rejected" and self._notifier:
            error = result.get("error", "unknown reason")
            # Only alert for safety-layer rejections, not dedup noise
            if "duplicate" not in error.lower():
                self._notifier.order_rejected(symbol, action, size, error)

        elif mode == "live_failed" and self._notifier:
            error = result.get("error", "unknown error")
            self._notifier.live_order_failed(symbol, action, error)

    # ── Session guard monitor ─────────────────────────────────────────────────

    def on_session_guard(self, guard) -> None:
        """
        Check a SessionGuard instance and notify on first halt.
        Pass eng._guard directly; this is a read-only check.
        """
        if guard is None or not guard.is_halted:
            return
        reason = guard.halt_reason
        if reason == self._notified_halt:
            return  # already notified for this halt
        self._notified_halt = reason
        if self._notifier:
            self._notifier.session_halt(reason, guard.state())

    # ── WebSocket / data staleness ────────────────────────────────────────────

    def check_ws_staleness(
        self,
        symbol: str,
        last_data_ts: float,
        threshold_seconds: float = 120.0,
    ) -> bool:
        """
        Returns True (and notifies) if `last_data_ts` is older than `threshold_seconds`.
        `last_data_ts` is a Unix epoch float (time.time()-compatible).
        """
        age = time.time() - last_data_ts
        if age > threshold_seconds:
            logger.warning(
                "[OpsWatchdog] %s data stale: %.0fs old (threshold %.0fs)",
                symbol, age, threshold_seconds,
            )
            if self._notifier:
                self._notifier.ws_disconnect(symbol, age)
            return True
        return False

    # ── Heartbeat (optional) ──────────────────────────────────────────────────

    def enable_heartbeat(self, interval_seconds: float = 3600.0) -> None:
        """Send a periodic "bot alive" ping. Call once during setup."""
        self._heartbeat_interval = interval_seconds
        self._last_heartbeat = time.time()

    def tick_heartbeat(self, extra: str = "") -> None:
        """Call once per cycle. Fires heartbeat when interval elapsed."""
        if self._heartbeat_interval <= 0:
            return
        now = time.time()
        if (now - self._last_heartbeat) >= self._heartbeat_interval:
            self._last_heartbeat = now
            uptime = int(now - self._session_start_ts)
            msg = f"Bot alive — uptime {uptime//3600}h{(uptime%3600)//60}m"
            if extra:
                msg += f"\n{extra}"
            if self._notifier:
                self._notifier.info(msg, key="heartbeat")

    # ── Startup / shutdown ────────────────────────────────────────────────────

    def notify_startup(self, mode: str = "paper", symbols: list[str] | None = None) -> None:
        """Send a startup notification. Call once when the bot starts."""
        sym_str = ", ".join(symbols) if symbols else "?"
        msg = f"[START] Bot started\nMode: {mode}\nSymbols: {sym_str}"
        if self._notifier:
            self._notifier.info(msg, key="startup")

    def notify_shutdown(self, reason: str = "user stop") -> None:
        """Send a shutdown notification. Call in finally block."""
        msg = f"[STOP] Bot stopped\nReason: {reason}"
        if self._notifier:
            self._notifier.info(msg, key="shutdown")
