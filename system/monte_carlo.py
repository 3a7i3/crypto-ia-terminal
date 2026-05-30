"""
monte_carlo.py — Simulation Monte Carlo sur une séquence de trades (P12-C3).

Méthode :
  1000 simulations avec rééchantillonnage (bootstrap avec remise)
  des rendements de trades.

Sorties :
  - Distribution du drawdown maximum (P5/P25/P50/P75/P95)
  - Distribution du rendement total
  - Probabilité de ruine (equity < seuil)
  - Intervalle de confiance 95%

Usage :
    engine = MonteCarloEngine(n_sims=1000, ruin_threshold_pct=50.0)
    report = engine.run(trades, initial_capital=10000.0)
    print(f"P95 drawdown: {report.drawdown_p95:.1f}%")
    print(f"Ruin probability: {report.ruin_probability:.1%}")
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Optional

from system.strategy_metrics import Trade


@dataclass
class MonteCarloReport:
    n_simulations: int = 0
    n_trades: int = 0
    initial_capital: float = 0.0

    # Distribution du drawdown maximum
    drawdown_p5: float = 0.0
    drawdown_p25: float = 0.0
    drawdown_p50: float = 0.0
    drawdown_p75: float = 0.0
    drawdown_p95: float = 0.0
    drawdown_mean: float = 0.0

    # Distribution du rendement total
    return_p5: float = 0.0
    return_p25: float = 0.0
    return_p50: float = 0.0
    return_p75: float = 0.0
    return_p95: float = 0.0
    return_mean: float = 0.0

    # Probabilité de ruine
    ruin_probability: float = 0.0
    ruin_threshold_pct: float = 50.0  # seuil de perte pour "ruine"

    # Intervalle de confiance du rendement espéré
    ci_lower_95: float = 0.0
    ci_upper_95: float = 0.0

    def summary(self) -> str:
        return (
            f"sims={self.n_simulations} "
            f"dd_p50={self.drawdown_p50:.1f}% dd_p95={self.drawdown_p95:.1f}% "
            f"ret_p50={self.return_p50:.2f}% "
            f"ruin={self.ruin_probability:.1%}"
        )


class MonteCarloEngine:
    """
    Moteur Monte Carlo par bootstrap sans remise séquentiel.

    n_sims           : nombre de simulations (défaut 1000)
    ruin_threshold_pct: perte maximale avant "ruine" (défaut 50%)
    seed             : seed pour reproductibilité (None = aléatoire)
    """

    def __init__(
        self,
        n_sims: int = 1000,
        ruin_threshold_pct: float = 50.0,
        seed: Optional[int] = None,
    ) -> None:
        self._n_sims = n_sims
        self._ruin_threshold = ruin_threshold_pct
        self._rng = random.Random(seed)

    def run(
        self,
        trades: list[Trade],
        initial_capital: float = 10_000.0,
    ) -> MonteCarloReport:
        """
        Lance n_sims simulations par rééchantillonnage des trades.

        Chaque simulation réordonne aléatoirement les trades et calcule :
          - drawdown maximum
          - rendement total
          - si ruine atteinte
        """
        report = MonteCarloReport(
            n_simulations=self._n_sims,
            n_trades=len(trades),
            initial_capital=initial_capital,
            ruin_threshold_pct=self._ruin_threshold,
        )

        if not trades:
            return report

        returns = [t.pnl_pct for t in trades]
        pnls = [t.pnl for t in trades]
        ruin_threshold = initial_capital * (1 - self._ruin_threshold / 100)

        drawdowns: list[float] = []
        total_returns: list[float] = []
        ruin_count = 0

        for _ in range(self._n_sims):
            # Rééchantillonnage avec remise
            sim_pnls = self._rng.choices(pnls, k=len(pnls))
            sim_returns = self._rng.choices(returns, k=len(returns))

            # Calcul equity curve
            equity = initial_capital
            peak = equity
            max_dd = 0.0
            ruined = False

            for pnl in sim_pnls:
                equity += pnl
                if equity > peak:
                    peak = equity
                if peak > 0:
                    dd = (peak - equity) / peak * 100
                    if dd > max_dd:
                        max_dd = dd
                if equity <= ruin_threshold:
                    ruined = True

            drawdowns.append(max_dd)
            total_returns.append(sum(sim_returns))
            if ruined:
                ruin_count += 1

        drawdowns.sort()
        total_returns.sort()

        n = len(drawdowns)
        report.drawdown_p5 = self._percentile(drawdowns, 5)
        report.drawdown_p25 = self._percentile(drawdowns, 25)
        report.drawdown_p50 = self._percentile(drawdowns, 50)
        report.drawdown_p75 = self._percentile(drawdowns, 75)
        report.drawdown_p95 = self._percentile(drawdowns, 95)
        report.drawdown_mean = statistics.mean(drawdowns) if drawdowns else 0.0

        report.return_p5 = self._percentile(total_returns, 5)
        report.return_p25 = self._percentile(total_returns, 25)
        report.return_p50 = self._percentile(total_returns, 50)
        report.return_p75 = self._percentile(total_returns, 75)
        report.return_p95 = self._percentile(total_returns, 95)
        report.return_mean = statistics.mean(total_returns) if total_returns else 0.0

        report.ruin_probability = ruin_count / self._n_sims

        # Intervalle de confiance 95% sur le rendement espéré
        if len(total_returns) >= 2:
            std = statistics.stdev(total_returns)
            mean = statistics.mean(total_returns)
            margin = 1.96 * std / math.sqrt(n)
            report.ci_lower_95 = mean - margin
            report.ci_upper_95 = mean + margin

        return report

    @staticmethod
    def _percentile(sorted_data: list[float], pct: float) -> float:
        if not sorted_data:
            return 0.0
        n = len(sorted_data)
        idx = (pct / 100) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac
