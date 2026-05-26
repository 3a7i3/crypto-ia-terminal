"""
SessionGuard — session-level risk controls for live trading.

Enforces hard limits per trading session:
  - Max session drawdown        (default 5 %)  → halts all orders
  - Max session loss            (default 3 %)  → halts all orders
  - Max consecutive losses      (default 3)    → halts all orders
  - Max single order size (USD) (default 10 000) → rejects oversized orders

Usage:
    guard = SessionGuard()
    guard.start_session(equity=10_000.0)

    guard.check_order("BTC/USDT", "BUY", size_usd=500.0)  # raises if halted/oversized

    guard.record_trade(pnl=-50.0, equity=9_950.0)          # updates internal state
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.risk.session_guard")
# ── Exceptions ─────────────────────────────────────────────────────────────────


class SessionHaltedError(RuntimeError):
    """Raised when the session is halted due to a risk limit breach."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Trading session halted: {reason}")
        self.reason = reason


class OrderTooLargeError(ValueError):
    """Raised when a single order exceeds the maximum size limit."""

    def __init__(self, size_usd: float, limit_usd: float) -> None:
        super().__init__(f"Order size ${size_usd:,.2f} exceeds limit ${limit_usd:,.2f}")
        self.size_usd = size_usd
        self.limit_usd = limit_usd


# ── State snapshot ─────────────────────────────────────────────────────────────


@dataclass
class SessionState:
    start_equity: float = 0.0
    peak_equity: float = 0.0
    current_equity: float = 0.0
    session_pnl: float = 0.0
    consecutive_losses: int = 0
    total_trades: int = 0
    halted: bool = False
    halt_reason: str = ""
    halt_time: float = 0.0
    events: list[str] = field(default_factory=list)

    @property
    def drawdown(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return (self.peak_equity - self.current_equity) / self.peak_equity

    @property
    def loss_pct(self) -> float:
        if self.start_equity <= 0:
            return 0.0
        return (self.start_equity - self.current_equity) / self.start_equity

    def as_dict(self) -> dict:
        return {
            "start_equity": round(self.start_equity, 2),
            "current_equity": round(self.current_equity, 2),
            "session_pnl": round(self.session_pnl, 4),
            "drawdown_pct": round(self.drawdown * 100, 2),
            "loss_pct": round(self.loss_pct * 100, 2),
            "consecutive_losses": self.consecutive_losses,
            "total_trades": self.total_trades,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }


# ── SessionGuard ───────────────────────────────────────────────────────────────


class SessionGuard:
    """
    Enforces risk limits on a per-session basis.

    All monetary limits are in the base currency (USDT by default).
    """

    def __init__(
        self,
        max_session_drawdown: float = 0.05,
        max_session_loss: float = 0.03,
        max_consecutive_losses: int = 3,
        max_order_size_usd: float = 10_000.0,
    ) -> None:
        self._max_dd = max_session_drawdown
        self._max_loss = max_session_loss
        self._max_consec = max_consecutive_losses
        self._max_order_usd = max_order_size_usd
        self._state = SessionState()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start_session(self, equity: float) -> None:
        """Call once at the start of each trading session."""
        self._state = SessionState(
            start_equity=equity,
            peak_equity=equity,
            current_equity=equity,
        )
        _log.info("[SessionGuard] Session started — equity=%.2f", equity)

    # ── Per-order check ────────────────────────────────────────────────────────

    def check_order(self, symbol: str, action: str, size_usd: float) -> None:
        """
        Raises SessionHaltedError or OrderTooLargeError if limits are breached.
        Call this before every order; it is a no-op when everything is fine.
        """
        if self._state.halted:
            raise SessionHaltedError(self._state.halt_reason)

        if size_usd > self._max_order_usd:
            _log.warning(
                "[SessionGuard] Order too large: %s %s $%.2f > limit $%.2f",
                action,
                symbol,
                size_usd,
                self._max_order_usd,
            )
            raise OrderTooLargeError(size_usd, self._max_order_usd)

    # ── Post-trade update ──────────────────────────────────────────────────────

    def record_trade(self, pnl: float, equity: float) -> None:
        """
        Update internal state after a trade result is known.
        Triggers a halt automatically if any limit is now breached.
        """
        s = self._state
        s.session_pnl += pnl
        s.total_trades += 1
        s.current_equity = equity
        s.peak_equity = max(s.peak_equity, equity)

        if pnl < 0:
            s.consecutive_losses += 1
        else:
            s.consecutive_losses = 0

        self._check_limits()

    # ── Manual override ────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear the halt flag (operator override, use with caution)."""
        if self._state.halted:
            _log.warning(
                "[SessionGuard] Halt manually cleared (was: %s)",
                self._state.halt_reason,
            )
        self._state.halted = False
        self._state.halt_reason = ""
        self._state.consecutive_losses = 0

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def is_halted(self) -> bool:
        return self._state.halted

    @property
    def halt_reason(self) -> str:
        return self._state.halt_reason

    def state(self) -> dict:
        return self._state.as_dict()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _check_limits(self) -> None:
        s = self._state
        if s.halted:
            return

        if s.drawdown >= self._max_dd:
            self._halt(f"session_drawdown {s.drawdown:.1%} >= limit {self._max_dd:.1%}")
        elif s.loss_pct >= self._max_loss:
            self._halt(f"session_loss {s.loss_pct:.1%} >= limit {self._max_loss:.1%}")
        elif s.consecutive_losses >= self._max_consec:
            self._halt(
                f"{s.consecutive_losses} consecutive losses >= limit {self._max_consec}"
            )

    def _halt(self, reason: str) -> None:
        s = self._state
        s.halted = True
        s.halt_reason = reason
        s.halt_time = time.time()
        s.events.append(f"HALT: {reason}")
        _log.error("[SessionGuard] TRADING HALTED — %s", reason)
