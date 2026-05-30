"""
walk_forward.py — Validation Walk-Forward (P12-C4).

Découpe une série de trades en fenêtres train/test glissantes et mesure
la cohérence des métriques hors-échantillon.

Exemple (train=70%, n_splits=5) :
  Split 1 : trades[0:56]  train, trades[56:80]  test
  Split 2 : trades[16:72] train, trades[72:96]  test
  ...

Usage :
    validator = WalkForwardValidator(train_pct=0.70, n_splits=5)
    report = validator.validate(trades, initial_capital=10000.0)
    print(report.oos_sharpe_mean, report.is_oos_consistency)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from system.strategy_metrics import StrategyAnalyzer, StrategyMetrics, Trade


@dataclass
class WalkForwardSplit:
    split_idx: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    train_metrics: StrategyMetrics
    test_metrics: StrategyMetrics

    @property
    def degradation_sharpe(self) -> float:
        """Dégradation Sharpe IS→OOS (positif = amélioration, négatif = overfitting)."""
        return self.test_metrics.sharpe_ratio - self.train_metrics.sharpe_ratio

    @property
    def degradation_pf(self) -> float:
        return self.test_metrics.profit_factor - self.train_metrics.profit_factor


@dataclass
class WalkForwardReport:
    n_splits: int = 0
    n_trades: int = 0
    train_pct: float = 0.70

    # Métriques OOS (out-of-sample) agrégées
    oos_win_rate_mean: float = 0.0
    oos_sharpe_mean: float = 0.0
    oos_sortino_mean: float = 0.0
    oos_profit_factor_mean: float = 0.0
    oos_expectancy_mean: float = 0.0
    oos_max_drawdown_mean: float = 0.0

    # Stabilité (écart-type des métriques OOS)
    oos_sharpe_std: float = 0.0
    oos_profit_factor_std: float = 0.0

    # Cohérence IS vs OOS (corrélation des métriques)
    is_oos_sharpe_ratio: float = 0.0  # OOS Sharpe / IS Sharpe (idéal ≈ 1)

    # Survie : nb de splits OOS avec expectancy > 0
    n_profitable_splits: int = 0
    pct_profitable_splits: float = 0.0

    # Sur-optimisation détectée ?
    overfit_suspected: bool = False

    # Détail par split
    splits: list[WalkForwardSplit] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"splits={self.n_splits} "
            f"oos_sharpe={self.oos_sharpe_mean:.2f}±{self.oos_sharpe_std:.2f} "
            f"oos_pf={self.oos_profit_factor_mean:.2f} "
            f"profitable={self.pct_profitable_splits:.0%} "
            f"overfit={'YES' if self.overfit_suspected else 'NO'}"
        )


class WalkForwardValidator:
    """
    Validation Walk-Forward avec fenêtres glissantes.

    train_pct : fraction des trades pour le train dans chaque split (ex: 0.70)
    n_splits  : nombre de fenêtres glissantes
    """

    def __init__(
        self,
        train_pct: float = 0.70,
        n_splits: int = 5,
        initial_capital: float = 10_000.0,
    ) -> None:
        if not 0 < train_pct < 1:
            raise ValueError("train_pct doit être entre 0 et 1")
        if n_splits < 2:
            raise ValueError("n_splits doit être >= 2")
        self._train_pct = train_pct
        self._n_splits = n_splits
        self._analyzer = StrategyAnalyzer(initial_capital=initial_capital)

    def validate(self, trades: list[Trade]) -> WalkForwardReport:
        report = WalkForwardReport(
            n_splits=self._n_splits,
            n_trades=len(trades),
            train_pct=self._train_pct,
        )

        n = len(trades)
        window_size = int(n / (self._n_splits * (1 - self._train_pct) + 1))
        if window_size < 5:
            report.n_splits = 0
            return report

        train_size = int(window_size * self._train_pct)
        test_size = window_size - train_size
        if test_size < 1:
            return report

        splits: list[WalkForwardSplit] = []
        is_sharpes: list[float] = []
        oos_sharpes: list[float] = []

        for i in range(self._n_splits):
            start = i * test_size
            train_end = start + train_size
            test_end = train_end + test_size

            if test_end > n:
                break

            train_trades = trades[start:train_end]
            test_trades = trades[train_end:test_end]

            if not train_trades or not test_trades:
                continue

            train_m = self._analyzer.compute(train_trades)
            test_m = self._analyzer.compute(test_trades)

            splits.append(
                WalkForwardSplit(
                    split_idx=i,
                    train_start=start,
                    train_end=train_end,
                    test_start=train_end,
                    test_end=test_end,
                    train_metrics=train_m,
                    test_metrics=test_m,
                )
            )
            is_sharpes.append(train_m.sharpe_ratio)
            oos_sharpes.append(test_m.sharpe_ratio)

        report.splits = splits
        report.n_splits = len(splits)

        if not splits:
            return report

        def _finite(values: list) -> list:
            return [v for v in values if v != float("inf") and v == v]

        oos_win_rates = [s.test_metrics.win_rate for s in splits]
        oos_pfs = _finite([s.test_metrics.profit_factor for s in splits])
        oos_exps = [s.test_metrics.expectancy for s in splits]
        oos_mdd = [s.test_metrics.max_drawdown_pct for s in splits]
        oos_sortinos = _finite([s.test_metrics.sortino_ratio for s in splits])

        report.oos_win_rate_mean = (
            statistics.mean(oos_win_rates) if oos_win_rates else 0.0
        )
        report.oos_sharpe_mean = statistics.mean(oos_sharpes) if oos_sharpes else 0.0
        report.oos_sortino_mean = statistics.mean(oos_sortinos) if oos_sortinos else 0.0
        report.oos_profit_factor_mean = statistics.mean(oos_pfs) if oos_pfs else 0.0
        report.oos_expectancy_mean = statistics.mean(oos_exps) if oos_exps else 0.0
        report.oos_max_drawdown_mean = statistics.mean(oos_mdd) if oos_mdd else 0.0

        if len(oos_sharpes) >= 2:
            report.oos_sharpe_std = statistics.stdev(oos_sharpes)
        if len(oos_pfs) >= 2:
            report.oos_profit_factor_std = statistics.stdev(oos_pfs)

        # Ratio IS→OOS Sharpe (sur-optimisation si < 0.5)
        is_mean = statistics.mean(is_sharpes) if is_sharpes else 0.0
        if is_mean != 0:
            report.is_oos_sharpe_ratio = report.oos_sharpe_mean / is_mean

        # Profitable splits
        profitable = [s for s in splits if s.test_metrics.expectancy > 0]
        report.n_profitable_splits = len(profitable)
        report.pct_profitable_splits = len(profitable) / len(splits)

        # Sur-optimisation : IS >> OOS ou < 50% splits profitables
        report.overfit_suspected = (
            report.is_oos_sharpe_ratio < 0.5 or report.pct_profitable_splits < 0.5
        )

        return report
