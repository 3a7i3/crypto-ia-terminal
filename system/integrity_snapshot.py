"""
system/integrity_snapshot.py — Capture normalisée de l'état runtime.

StateSnapshot.capture() lit toutes les sources d'état, normalise les valeurs
(tri, arrondi, pas de timestamps variables), puis produit un hash déterministe.

Invariant : deux snapshots identiques → même hash, quel que soit l'ordre
d'insertion interne ou les microfluctuations float.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class StateSnapshot:
    """Vue normalisée et hashable de l'état runtime complet."""

    captured_at: float
    cycle: int

    # ── Signal state ──────────────────────────────────────────────────────────
    last_trade_signal: dict[str, str]  # sym -> "BUY"|"SELL"
    last_loss_timestamps: dict[str, float]  # sym -> unix timestamp
    trades_this_hour: dict[str, int]  # sym -> nb trades dans la dernière heure

    # ── Position state ────────────────────────────────────────────────────────
    open_positions_local: list[dict]  # [{symbol, side, size_usd}] de snapshot()
    open_count_stats: int  # de pos_manager.stats()
    open_pnl_usd: float
    total_pnl_usd: float
    win_rate: float

    # ── Capital state ─────────────────────────────────────────────────────────
    real_capital: float
    portfolio_free_capital: float  # budget max déployable (40% cap)
    portfolio_exposure_pct: float  # exposition actuelle 0-1
    portfolio_n_positions: int  # positions selon portfolio brain

    # ── Order state ───────────────────────────────────────────────────────────
    pending_order_count: int  # ordres en attente (si tracking disponible)

    @classmethod
    def capture(
        cls,
        cycle: int,
        real_capital: float,
        last_trade_signal: dict[str, str],
        last_loss_time: dict[str, float],
        trades_this_hour: dict[str, list[float]],
        pos_manager: Any,
        portfolio_brain: Any,
        pending_orders: list | None = None,
    ) -> StateSnapshot:
        now = time.time()
        hour_ago = now - 3600.0

        # ── Normaliser trades_this_hour : timestamps → comptage fenêtré ──────
        normalized_tth: dict[str, int] = {
            sym: sum(1 for t in times if isinstance(t, (int, float)) and t > hour_ago)
            for sym, times in trades_this_hour.items()
        }

        # ── Positions ─────────────────────────────────────────────────────────
        open_pos: list[dict] = []
        open_count = 0
        open_pnl = 0.0
        total_pnl = 0.0
        win_rate = 0.0

        if pos_manager is not None:
            try:
                stats = pos_manager.stats()
                open_count = int(stats.get("open_count", 0))
                open_pnl = float(stats.get("open_pnl_usd", 0.0))
                total_pnl = float(stats.get("total_pnl_usd", 0.0))
                win_rate = float(stats.get("win_rate", 0.0))
            except Exception:
                pass

            try:
                raw = pos_manager.snapshot()
                for p in raw or []:
                    if isinstance(p, dict):
                        open_pos.append(
                            {
                                "symbol": str(p.get("symbol", "")),
                                "side": str(p.get("side", "")),
                                "size_usd": round(float(p.get("size_usd", 0.0)), 2),
                            }
                        )
            except Exception:
                pass

        # ── Portfolio Brain ───────────────────────────────────────────────────
        pb_free = 0.0
        pb_exposure = 0.0
        pb_n = 0

        if portfolio_brain is not None:
            try:
                open_list = (
                    pos_manager.get_open()
                    if pos_manager is not None and hasattr(pos_manager, "get_open")
                    else []
                )
                health = portfolio_brain.portfolio_health(open_list)
                pb_free = float(health.get("free_capital", 0.0))
                pb_exposure = float(health.get("total_exposure_pct", 0.0))
                pb_n = int(health.get("n_positions", 0))
            except Exception:
                pass

        return cls(
            captured_at=now,
            cycle=cycle,
            last_trade_signal=dict(last_trade_signal),
            last_loss_timestamps=dict(last_loss_time),
            trades_this_hour=normalized_tth,
            open_positions_local=open_pos,
            open_count_stats=open_count,
            open_pnl_usd=round(open_pnl, 2),
            total_pnl_usd=round(total_pnl, 2),
            win_rate=round(win_rate, 3),
            real_capital=round(real_capital, 2),
            portfolio_free_capital=round(pb_free, 2),
            portfolio_exposure_pct=round(pb_exposure, 4),
            portfolio_n_positions=pb_n,
            pending_order_count=len(pending_orders) if pending_orders else 0,
        )

    def normalized_dict(self) -> dict:
        """Dict déterministe pour hashing — timestamps et champs volatils exclus."""
        return {
            "last_trade_signal": dict(sorted(self.last_trade_signal.items())),
            "trades_this_hour": dict(sorted(self.trades_this_hour.items())),
            "open_positions_local": sorted(
                self.open_positions_local, key=lambda p: p.get("symbol", "")
            ),
            "open_count_stats": self.open_count_stats,
            "real_capital": self.real_capital,
            "portfolio_free_capital": self.portfolio_free_capital,
            "portfolio_exposure_pct": self.portfolio_exposure_pct,
            "portfolio_n_positions": self.portfolio_n_positions,
            "pending_order_count": self.pending_order_count,
        }

    def compute_hash(self) -> str:
        """SHA-256 (16 car) sur l'état normalisé. Deux états identiques → même hash."""
        nd = self.normalized_dict()
        serialized = json.dumps(nd, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]
