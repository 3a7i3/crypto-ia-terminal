"""
src/analytics/is_oos_splitter.py — Séparateur IS/OOS temporel strict.

Pure function : aucune logique métier, aucun effet de bord.

Contrat Z3 (anti-leakage) — invariants formels :
  C1-I1 : IS ∪ OOS = input                                 (complétude)
  C1-I2 : IS ∩ OOS = ∅                                     (disjonction)
  C1-I3 : max(IS.closed_at) ≤ min(OOS.closed_at)           (monotonie temporelle)
  C1-I4 : ∀ u ∈ OOS, u ∉ IS                               (anti-leakage identitaire)
  C1-I5 : f(x) = f(x)                                      (déterminisme)
  C1-I6 : |n_is / n − is_ratio| ≤ 1/n                      (proximité du ratio)
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple, Optional

from src.domain.trade_event import TradeEvent


class SplitMetadata(NamedTuple):
    is_ratio: float
    cut_timestamp: Optional[datetime]
    n_is: int
    n_oos: int


class ISOOSSplit(NamedTuple):
    is_trades: list[TradeEvent]
    oos_trades: list[TradeEvent]
    metadata: SplitMetadata


def split_is_oos(
    trades: list[TradeEvent],
    is_ratio: float = 0.6,
) -> ISOOSSplit:
    """
    Séparation temporelle stricte IS/OOS.

    Sort par (closed_at, trade_id) pour garantir le déterminisme en cas d'égalité.
    Le cut_idx est le quantile temporel fixe is_ratio.
    """
    if not 0 < is_ratio <= 1:
        raise ValueError(f"is_ratio must be in (0, 1], got {is_ratio!r}")

    if not trades:
        return ISOOSSplit(
            is_trades=[],
            oos_trades=[],
            metadata=SplitMetadata(
                is_ratio=is_ratio,
                cut_timestamp=None,
                n_is=0,
                n_oos=0,
            ),
        )

    sorted_trades = sorted(trades, key=lambda t: (t.closed_at, t.trade_id))
    n = len(sorted_trades)
    cut_idx = max(1, round(n * is_ratio))

    is_trades = sorted_trades[:cut_idx]
    oos_trades = sorted_trades[cut_idx:]

    return ISOOSSplit(
        is_trades=is_trades,
        oos_trades=oos_trades,
        metadata=SplitMetadata(
            is_ratio=is_ratio,
            cut_timestamp=is_trades[-1].closed_at,
            n_is=len(is_trades),
            n_oos=len(oos_trades),
        ),
    )
