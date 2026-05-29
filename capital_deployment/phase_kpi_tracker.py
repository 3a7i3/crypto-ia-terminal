"""
capital_deployment/phase_kpi_tracker.py — Live KPI Tracker per Phase

Tracks per phase:
  - Win rate (fraction of profitable trades)
  - Sharpe ratio (annualized, daily-return based)
  - Max drawdown (fraction of peak equity)
  - Unsigned decisions (security violations)
  - Days elapsed since phase start

Phase criteria (minimum required to advance):
  F-01: win_rate > 45%, Sharpe > 1.0, max_DD < 2%, 7 days
  F-02: win_rate > 45%, Sharpe > 1.2, max_DD < 4%, 14 days
  F-03: win_rate > 45%, Sharpe > 1.5, max_DD < 8%, 21 days
  F-04: win_rate > 45%, Sharpe > 1.5, max_DD < 12%, 30 days
  F-05: Sharpe > 1.2, max_DD < 20%, ongoing
"""

from __future__ import annotations

import math
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("capital_deployment.phase_kpi_tracker")

PHASE_CRITERIA: dict[str, dict] = {
    "F-01": {
        "min_win_rate": 0.45,
        "min_sharpe": 1.0,
        "max_drawdown": 0.02,
        "min_duration_days": 7,
    },
    "F-02": {
        "min_win_rate": 0.45,
        "min_sharpe": 1.2,
        "max_drawdown": 0.04,
        "min_duration_days": 14,
    },
    "F-03": {
        "min_win_rate": 0.45,
        "min_sharpe": 1.5,
        "max_drawdown": 0.08,
        "min_duration_days": 21,
    },
    "F-04": {
        "min_win_rate": 0.45,
        "min_sharpe": 1.5,
        "max_drawdown": 0.12,
        "min_duration_days": 30,
    },
    "F-05": {
        "min_win_rate": 0.00,
        "min_sharpe": 1.2,
        "max_drawdown": 0.20,
        "min_duration_days": 0,
    },
}


@dataclass
class TradeRecord:
    ts: float
    pnl: float
    symbol: str
    side: str  # "buy" / "sell"
    entry_price: float
    exit_price: float
    signed: bool = True  # cryptographic signature verified


@dataclass
class KPISnapshot:
    phase: str
    win_rate: float
    sharpe: float
    max_drawdown: float
    current_drawdown: float
    total_trades: int
    unsigned_decisions: int
    days_elapsed: float
    ts: float = field(default_factory=time.time)

    def passes(self, phase: str) -> bool:
        return len(self.violations(phase)) == 0

    def violations(self, phase: str) -> list[str]:
        crit = PHASE_CRITERIA.get(phase, {})
        v: list[str] = []
        if self.win_rate < crit.get("min_win_rate", 0.0):
            v.append(f"win_rate {self.win_rate:.1%} < {crit['min_win_rate']:.1%}")
        if self.sharpe < crit.get("min_sharpe", 0.0):
            v.append(f"sharpe {self.sharpe:.3f} < {crit['min_sharpe']}")
        if self.max_drawdown > crit.get("max_drawdown", 1.0):
            v.append(
                f"max_drawdown {self.max_drawdown:.2%} > {crit['max_drawdown']:.2%}"
            )
        min_days = crit.get("min_duration_days", 0)
        if self.days_elapsed < min_days:
            v.append(f"elapsed {self.days_elapsed:.1f}d < {min_days}d required")
        if self.unsigned_decisions > 0:
            v.append(f"{self.unsigned_decisions} décision(s) non signée(s)")
        return v

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "win_rate": round(self.win_rate, 4),
            "sharpe": round(self.sharpe, 3),
            "max_drawdown": round(self.max_drawdown, 4),
            "current_drawdown": round(self.current_drawdown, 4),
            "total_trades": self.total_trades,
            "unsigned_decisions": self.unsigned_decisions,
            "days_elapsed": round(self.days_elapsed, 2),
            "ts": round(self.ts, 3),
        }


class PhaseKPITracker:
    """
    Tracks all live trading KPIs for a single deployment phase.

    Sharpe ratio: annualized from daily returns (sqrt(252) factor).
    Daily returns are accumulated each time a trade's timestamp crosses a 24h boundary.

    Usage:
        tracker = PhaseKPITracker(phase="F-01", initial_capital=100.0)
        tracker.record_trade(TradeRecord(...))
        snap = tracker.snapshot()
        ok, violations = tracker.meets_criteria()
    """

    def __init__(
        self,
        phase: str = "F-01",
        initial_capital: float = 100.0,
        started_at: Optional[float] = None,
    ) -> None:
        if phase not in PHASE_CRITERIA:
            raise ValueError(f"Phase inconnue: {phase}")
        self._phase = phase
        self._initial_capital = initial_capital
        self._started_at = started_at or time.time()
        self._trades: list[TradeRecord] = []
        self._equity = initial_capital
        self._peak_equity = initial_capital
        self._max_drawdown = 0.0
        self._daily_returns: deque[float] = deque(maxlen=365)
        self._last_day_equity = initial_capital
        self._last_day_ts = self._started_at
        self._unsigned_count = 0

    def record_trade(self, trade: TradeRecord) -> None:
        self._trades.append(trade)
        self._equity += trade.pnl
        if not trade.signed:
            self._unsigned_count += 1

        if self._equity > self._peak_equity:
            self._peak_equity = self._equity
        if self._peak_equity > 0:
            dd = (self._peak_equity - self._equity) / self._peak_equity
            self._max_drawdown = max(self._max_drawdown, dd)

        # Accumulate daily return when a day boundary is crossed
        if trade.ts - self._last_day_ts >= 86400.0:
            daily_ret = (self._equity - self._last_day_equity) / max(
                self._last_day_equity, 1e-9
            )
            self._daily_returns.append(daily_ret)
            self._last_day_equity = self._equity
            self._last_day_ts = trade.ts

    def win_rate(self) -> float:
        if not self._trades:
            return 0.0
        wins = sum(1 for t in self._trades if t.pnl > 0)
        return wins / len(self._trades)

    def sharpe_ratio(self) -> float:
        """Annualized Sharpe from daily returns (requires ≥ 2 daily data points)."""
        if len(self._daily_returns) < 2:
            return 0.0
        returns = list(self._daily_returns)
        mean_r = statistics.mean(returns)
        std_r = statistics.stdev(returns)
        if std_r < 1e-12:
            return 0.0
        return (mean_r / std_r) * math.sqrt(252)

    def max_drawdown(self) -> float:
        return self._max_drawdown

    def current_drawdown(self) -> float:
        if self._peak_equity <= 0:
            return 0.0
        return max(0.0, (self._peak_equity - self._equity) / self._peak_equity)

    def days_elapsed(self) -> float:
        return (time.time() - self._started_at) / 86400.0

    def unsigned_decisions(self) -> int:
        return self._unsigned_count

    def equity(self) -> float:
        return self._equity

    def snapshot(self) -> KPISnapshot:
        return KPISnapshot(
            phase=self._phase,
            win_rate=self.win_rate(),
            sharpe=self.sharpe_ratio(),
            max_drawdown=self.max_drawdown(),
            current_drawdown=self.current_drawdown(),
            total_trades=len(self._trades),
            unsigned_decisions=self._unsigned_count,
            days_elapsed=self.days_elapsed(),
        )

    def meets_criteria(self) -> tuple[bool, list[str]]:
        snap = self.snapshot()
        v = snap.violations(self._phase)
        return len(v) == 0, v
