"""
src/analytics/bootstrap_stability.py — C2 : Estimateur de stabilité bootstrap.

Pure function — aucune décision, aucun filtrage, aucune mutation système.
Consomme list[TradeEvent] (typiquement ISOOSSplit.is_trades).
Produit une estimation distributionnelle de l'expectancy.

Contrat :
  - 0.0 ≤ p_value ≤ 1.0
  - ci_low ≤ ci_high
  - result.n == len(trades)
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from src.domain.trade_event import TradeEvent


@dataclass(frozen=True)
class BootstrapResult:
    mean_expectancy: float
    ci_low: float
    ci_high: float
    p_value: float
    n: int


def _extract_pnl(trades: list[TradeEvent]) -> list[float]:
    return [t.net_pnl_usd for t in trades]


def _expectancy(pnls: list[float]) -> float:
    return sum(pnls) / len(pnls) if pnls else 0.0


def _bootstrap_expectancy(
    pnls: list[float],
    n_resamples: int,
    seed: Optional[int],
) -> list[float]:
    if not pnls:
        return [0.0]
    rng = random.Random(seed)
    n = len(pnls)
    return [
        _expectancy([pnls[rng.randint(0, n - 1)] for _ in range(n)])
        for _ in range(n_resamples)
    ]


def _confidence_interval(values: list[float], alpha: float) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    s = sorted(values)
    m = len(s)
    low_idx = max(0, int(m * (alpha / 2)))
    high_idx = max(0, min(m - 1, int(m * (1 - alpha / 2)) - 1))
    return s[low_idx], s[high_idx]


def _p_value_positive(values: list[float]) -> float:
    if not values:
        return 1.0
    return 1.0 - sum(1 for v in values if v > 0) / len(values)


def run_bootstrap_stability(
    trades: list[TradeEvent],
    n_resamples: int = 30,
    alpha: float = 0.05,
    seed: Optional[int] = None,
) -> BootstrapResult:
    """
    Estimation bootstrap de l'expectancy sur IS uniquement.

    seed : fixe la reproductibilité (None = stochastique).
    """
    pnls = _extract_pnl(trades)
    base_mean = _expectancy(pnls)
    boot = _bootstrap_expectancy(pnls, n_resamples, seed)
    ci_low, ci_high = _confidence_interval(boot, alpha)
    p_value = _p_value_positive(boot)

    return BootstrapResult(
        mean_expectancy=base_mean,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=p_value,
        n=len(trades),
    )
