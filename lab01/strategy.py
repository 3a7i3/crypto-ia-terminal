"""Signal de démonstration : cassure haussière d'une bande de volatilité.

Stratégie de LAB, non liée aux stratégies actives ni à leurs seuils.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from lab01.synthetic import Bar


@dataclass(frozen=True)
class SignalConfig:
    lookback: int = 20
    k_sigma: float = 2.0
    stop_bps: float = 100.0
    take_profit_bps: float = 200.0
    max_hold_bars: int = 30


@dataclass(frozen=True)
class Signal:
    bar_index: int
    side: str  # "LONG"
    price: float
    z_score: float
    confidence: float
    stop_loss: float
    take_profit: float
    realized_vol_bps: float


def realized_vol_bps(closes: list[float]) -> float:
    rets = [(b / a - 1.0) * 10_000.0 for a, b in zip(closes, closes[1:])]
    return statistics.pstdev(rets) if len(rets) >= 2 else 0.0


def evaluate(bars: list[Bar], i: int, cfg: SignalConfig) -> Signal | None:
    if i < cfg.lookback:
        return None
    window = [b.close for b in bars[i - cfg.lookback : i]]
    mean = statistics.fmean(window)
    sd = statistics.pstdev(window)
    if sd <= 0:
        return None
    price = bars[i].close
    z = (price - mean) / sd
    if z < cfg.k_sigma:
        return None
    return Signal(
        bar_index=i,
        side="LONG",
        price=price,
        z_score=round(z, 4),
        confidence=round(min(100.0, 50.0 + 10.0 * z), 4),
        stop_loss=round(price * (1 - cfg.stop_bps / 10_000.0), 6),
        take_profit=round(price * (1 + cfg.take_profit_bps / 10_000.0), 6),
        realized_vol_bps=round(realized_vol_bps(window + [price]), 4),
    )
