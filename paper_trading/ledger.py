"""
paper_trading/ledger.py — Registre des trades paper avec P&L réaliste.

PaperTrade : un trade complet (entry + exit) avec slippage et fees.
PaperLedger : registre thread-safe de tous les trades ouverts et fermés.

Le P&L est calculé en deux versions :
  pnl_gross_pct  : sans coûts (ce que la stratégie croit faire)
  pnl_net_pct    : avec slippage + spread + fees des deux côtés (réalité)

L'écart gross - net = alpha perdu à l'exécution. Mesure critique P5.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PaperTrade:
    """Un trade paper complet — entry jusqu'à exit."""

    trade_id: str
    symbol: str
    side: str  # "buy" | "sell"
    size_usd: float  # taille en USD

    # Entry
    signal_price: float  # prix au signal (théorique)
    entry_price: float  # prix réel après slippage entry
    entry_slippage_bps: float
    entry_latency_ms: float
    entry_fee_usd: float
    entry_ts: float  # timestamp unix

    # Exit (rempli à la clôture)
    exit_price: Optional[float] = None
    exit_slippage_bps: float = 0.0
    exit_latency_ms: float = 0.0
    exit_fee_usd: float = 0.0
    exit_ts: Optional[float] = None
    exit_reason: str = ""

    # Méta
    regime: str = "unknown"
    strategy_id: str = ""
    is_open: bool = True

    @property
    def duration_s(self) -> float:
        if self.exit_ts is None:
            return time.time() - self.entry_ts
        return self.exit_ts - self.entry_ts

    @property
    def pnl_gross_pct(self) -> float:
        """P&L sans coûts — ce que la stratégie théorique réalise."""
        if self.exit_price is None:
            return 0.0
        if self.side == "buy":
            return (self.exit_price - self.signal_price) / self.signal_price * 100.0
        return (self.signal_price - self.exit_price) / self.signal_price * 100.0

    @property
    def pnl_net_pct(self) -> float:
        """P&L avec slippage + fees — réalité exécution."""
        if self.exit_price is None:
            return 0.0
        if self.side == "buy":
            raw = (self.exit_price - self.entry_price) / self.entry_price * 100.0
        else:
            raw = (self.entry_price - self.exit_price) / self.entry_price * 100.0
        total_fees_pct = (
            (self.entry_fee_usd + self.exit_fee_usd) / self.size_usd * 100.0
        )
        return raw - total_fees_pct

    @property
    def pnl_net_usd(self) -> float:
        return self.pnl_net_pct / 100.0 * self.size_usd

    @property
    def execution_cost_pct(self) -> float:
        """Coût total d'exécution = gross - net."""
        return self.pnl_gross_pct - self.pnl_net_pct

    @property
    def is_win(self) -> bool:
        return self.pnl_net_pct > 0

    def as_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "size_usd": round(self.size_usd, 2),
            "signal_price": round(self.signal_price, 4),
            "entry_price": round(self.entry_price, 4),
            "exit_price": round(self.exit_price, 4) if self.exit_price else None,
            "entry_slippage_bps": round(self.entry_slippage_bps, 2),
            "exit_slippage_bps": round(self.exit_slippage_bps, 2),
            "entry_fee_usd": round(self.entry_fee_usd, 4),
            "exit_fee_usd": round(self.exit_fee_usd, 4),
            "pnl_gross_pct": round(self.pnl_gross_pct, 4),
            "pnl_net_pct": round(self.pnl_net_pct, 4),
            "pnl_net_usd": round(self.pnl_net_usd, 4),
            "execution_cost_pct": round(self.execution_cost_pct, 4),
            "duration_s": round(self.duration_s, 1),
            "regime": self.regime,
            "exit_reason": self.exit_reason,
            "is_open": self.is_open,
            "entry_ts": self.entry_ts,
            "exit_ts": self.exit_ts,
        }


class PaperLedger:
    """
    Registre thread-safe de tous les trades paper.

    Gère les positions ouvertes (max 1 par symbole) et l'historique fermé.
    Calcule les métriques agrégées en temps réel.
    """

    def __init__(self, initial_capital: float = 10_000.0) -> None:
        self._lock = threading.Lock()
        self._open: dict[str, PaperTrade] = {}  # symbol → trade ouvert
        self._closed: list[PaperTrade] = []
        self.initial_capital = initial_capital
        self._capital = initial_capital  # capital courant (après P&L)

    # ------------------------------------------------------------------
    # Opérations
    # ------------------------------------------------------------------

    def open_trade(self, trade: PaperTrade) -> None:
        with self._lock:
            self._open[trade.symbol] = trade

    def close_trade(
        self,
        symbol: str,
        exit_price: float,
        exit_slippage_bps: float = 0.0,
        exit_latency_ms: float = 0.0,
        exit_fee_usd: float = 0.0,
        exit_reason: str = "signal",
    ) -> Optional[PaperTrade]:
        with self._lock:
            trade = self._open.pop(symbol, None)
            if trade is None:
                return None
            trade.exit_price = exit_price
            trade.exit_slippage_bps = exit_slippage_bps
            trade.exit_latency_ms = exit_latency_ms
            trade.exit_fee_usd = exit_fee_usd
            trade.exit_ts = time.time()
            trade.exit_reason = exit_reason
            trade.is_open = False
            self._closed.append(trade)
            self._capital += trade.pnl_net_usd
            return trade

    def get_open(self, symbol: str) -> Optional[PaperTrade]:
        with self._lock:
            return self._open.get(symbol)

    # ------------------------------------------------------------------
    # Métriques
    # ------------------------------------------------------------------

    @property
    def capital(self) -> float:
        with self._lock:
            return self._capital

    @property
    def closed_trades(self) -> list[PaperTrade]:
        with self._lock:
            return list(self._closed)

    @property
    def open_trades(self) -> list[PaperTrade]:
        with self._lock:
            return list(self._open.values())

    def summary(self) -> dict:
        with self._lock:
            closed = list(self._closed)
            open_ = list(self._open.values())

        if not closed:
            return {
                "n_trades": 0,
                "n_open": len(open_),
                "capital": round(self._capital, 2),
                "pnl_net_usd": 0.0,
                "pnl_net_pct": 0.0,
                "win_rate": 0.0,
                "avg_pnl_net_pct": 0.0,
                "avg_execution_cost_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "total_fees_usd": 0.0,
            }

        wins = [t for t in closed if t.is_win]
        pnl_net_vals = [t.pnl_net_pct for t in closed]
        cost_vals = [t.execution_cost_pct for t in closed]
        fees = sum(t.entry_fee_usd + t.exit_fee_usd for t in closed)

        # Drawdown sur courbe de capital
        equity = self.initial_capital
        peak = equity
        max_dd = 0.0
        for t in closed:
            equity += t.pnl_net_usd
            peak = max(peak, equity)
            dd = (equity - peak) / peak * 100.0
            max_dd = min(max_dd, dd)

        pnl_net_usd = sum(t.pnl_net_usd for t in closed)
        pnl_net_pct = pnl_net_usd / self.initial_capital * 100.0

        return {
            "n_trades": len(closed),
            "n_open": len(open_),
            "capital": round(self._capital, 2),
            "pnl_net_usd": round(pnl_net_usd, 2),
            "pnl_net_pct": round(pnl_net_pct, 4),
            "win_rate": round(len(wins) / len(closed) * 100, 1),
            "avg_pnl_net_pct": round(sum(pnl_net_vals) / len(pnl_net_vals), 4),
            "avg_execution_cost_pct": round(sum(cost_vals) / len(cost_vals), 4),
            "max_drawdown_pct": round(max_dd, 4),
            "total_fees_usd": round(fees, 4),
        }
