"""
walk_forward/engine.py — Orchestrateur du walk-forward complet.

Pipeline :
  data (liste) → WindowSplitter → folds → WalkForwardLoop → FoldResult[]
                                                               ↓
                              DegradationTracker ← OOSMetrics par fold
                                                               ↓
                                              WalkForwardResult (agregat)

Usage minimal :
    from walk_forward.window_splitter import WindowSplitter
    from walk_forward.walk_forward_loop import WalkForwardLoop
    from walk_forward.engine import WalkForwardEngine
    from monitor.degradation_tracker import DegradationTracker

    splitter = WindowSplitter(n_samples=len(data), train_size=600, test_size=100)
    loop = WalkForwardLoop(optimizer=my_opt, validator=my_val)
    engine = WalkForwardEngine(splitter=splitter, loop=loop)
    result = engine.run(data)

    print(result.aggregate_metrics.sharpe_ratio)
    print(result.is_robust)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional

from metrics.oos_metrics import OOSMetrics, TradeResult, compute_oos_metrics
from metrics.stability_score import RegimeStability, compute_stability_score
from monitor.degradation_tracker import DegradationEvent, DegradationTracker
from walk_forward.walk_forward_loop import FoldResult, WalkForwardLoop
from walk_forward.window_splitter import WindowSplitter


@dataclass
class WalkForwardResult:
    """
    Resultat complet d'un run walk-forward.

    folds              : tous les FoldResult (un par fenetre)
    aggregate_metrics  : OOSMetrics sur l'ensemble des trades OOS concatenes
    stability          : score de stabilite inter-regimes
    degradation_events : alertes emises par le DegradationTracker
    is_robust          : True si tous les criteres de robustesse sont satisfaits
    """

    folds: list[FoldResult]
    aggregate_metrics: OOSMetrics
    stability: RegimeStability
    degradation_events: list[DegradationEvent]
    is_robust: bool

    # Statistiques inter-folds
    mean_oos_sharpe: float = 0.0
    std_oos_sharpe: float = 0.0
    n_profitable_folds: int = 0
    n_folds: int = 0

    def as_dict(self) -> dict:
        return {
            "n_folds": self.n_folds,
            "n_profitable_folds": self.n_profitable_folds,
            "profitable_fold_rate": (
                round(self.n_profitable_folds / self.n_folds, 4)
                if self.n_folds > 0
                else 0.0
            ),
            "mean_oos_sharpe": round(self.mean_oos_sharpe, 4),
            "std_oos_sharpe": round(self.std_oos_sharpe, 4),
            "aggregate": self.aggregate_metrics.as_dict(),
            "stability": self.stability.as_dict(),
            "n_degradation_warnings": sum(
                1 for e in self.degradation_events if e.severity == "warning"
            ),
            "n_degradation_criticals": sum(
                1 for e in self.degradation_events if e.severity == "critical"
            ),
            "is_robust": self.is_robust,
        }


class WalkForwardEngine:
    """
    Orchestrateur principal du walk-forward.

    Criteres de robustesse (is_robust = True si tous satisfaits) :
      - profitable_fold_rate >= min_profitable_fold_rate
      - aggregate Sharpe >= min_aggregate_sharpe
      - aggregate drawdown > max_drawdown_pct (ex : > -20%)
      - aucun evenement critique de degradation
      - stability_score >= min_stability_score
    """

    def __init__(
        self,
        splitter: WindowSplitter,
        loop: WalkForwardLoop,
        degradation_tracker: Optional[DegradationTracker] = None,
        min_profitable_fold_rate: float = 0.6,
        min_aggregate_sharpe: float = 0.5,
        max_drawdown_pct: float = -20.0,
        min_stability_score: float = 0.5,
        min_trades_per_regime: int = 3,
    ) -> None:
        self._splitter = splitter
        self._loop = loop
        self._tracker = degradation_tracker or DegradationTracker()
        self.min_profitable_fold_rate = min_profitable_fold_rate
        self.min_aggregate_sharpe = min_aggregate_sharpe
        self.max_drawdown_pct = max_drawdown_pct
        self.min_stability_score = min_stability_score
        self.min_trades_per_regime = min_trades_per_regime

    def run(self, data: list) -> WalkForwardResult:
        """
        Execute le walk-forward complet sur `data`.

        data : sequence indexable (list de candles, returns, ou tout autre objet
               que optimizer/validator savent traiter).
        """
        self._tracker.reset()
        folds: list[FoldResult] = []

        for window in self._splitter.split():
            fold_result = self._loop.run_fold(data, window)
            folds.append(fold_result)

            if fold_result.is_valid:
                self._tracker.record(window.fold_index, fold_result.oos_metrics)

        if not folds:
            empty = compute_oos_metrics([])
            empty_stability = compute_stability_score({})
            return WalkForwardResult(
                folds=[],
                aggregate_metrics=empty,
                stability=empty_stability,
                degradation_events=[],
                is_robust=False,
                n_folds=0,
            )

        # Agregat OOS : concatener tous les trades OOS valides
        all_oos_trades: list[TradeResult] = []
        for f in folds:
            if f.is_valid:
                all_oos_trades.extend(f.trades)
        aggregate = compute_oos_metrics(
            all_oos_trades, self._loop._annualization_factor
        )

        # Metriques inter-folds
        valid_sharpes = [f.oos_metrics.sharpe_ratio for f in folds if f.is_valid]
        mean_sharpe = statistics.mean(valid_sharpes) if valid_sharpes else 0.0
        std_sharpe = statistics.stdev(valid_sharpes) if len(valid_sharpes) > 1 else 0.0
        n_profitable = sum(
            1 for f in folds if f.is_valid and f.oos_metrics.is_profitable
        )

        # Stabilite inter-regimes : regrouper les trades par regime
        regime_trades: dict[str, list[TradeResult]] = {}
        for t in all_oos_trades:
            regime_trades.setdefault(t.regime, []).append(t)
        regime_metrics = {
            r: compute_oos_metrics(trades, self._loop._annualization_factor)
            for r, trades in regime_trades.items()
        }
        stability = compute_stability_score(regime_metrics, self.min_trades_per_regime)

        # Criteres de robustesse
        n_valid = sum(1 for f in folds if f.is_valid)
        profitable_rate = n_profitable / n_valid if n_valid > 0 else 0.0
        is_robust = (
            profitable_rate >= self.min_profitable_fold_rate
            and aggregate.sharpe_ratio >= self.min_aggregate_sharpe
            and aggregate.max_drawdown_pct > self.max_drawdown_pct
            and not self._tracker.is_degrading
            and stability.stability_score >= self.min_stability_score
        )

        return WalkForwardResult(
            folds=folds,
            aggregate_metrics=aggregate,
            stability=stability,
            degradation_events=self._tracker.all_events,
            is_robust=is_robust,
            mean_oos_sharpe=mean_sharpe,
            std_oos_sharpe=std_sharpe,
            n_profitable_folds=n_profitable,
            n_folds=len(folds),
        )
