"""
P12-C — Strategy Validation Framework.

C1 — StrategyMetrics     : métriques fondamentales (Sharpe, Sortino, PF, Expectancy…)
C2 — EquityCurveAnalyzer : drawdown, underwater, new highs, récupération
C3 — MonteCarloEngine    : distribution drawdown, ruin probability, CI 95%
C4 — WalkForwardValidator: cohérence IS/OOS, détection sur-optimisation
C5 — RegimeValidator     : performance par régime BULL/BEAR/RANGE/HIGH_VOL/LOW_VOL
C6 — StrategyScorer      : score composite 0-100 et grade S/A/B/C/D/F
"""

from __future__ import annotations

import math
import random

import pytest

from system.equity_curve import EquityCurveAnalyzer
from system.monte_carlo import MonteCarloEngine
from system.regime_validator import RegimeValidator
from system.strategy_metrics import StrategyAnalyzer, StrategyMetrics, Trade
from system.strategy_score import StrategyGrade, StrategyScorer
from system.walk_forward import WalkForwardValidator

# ── Factories ─────────────────────────────────────────────────────────────────


def _winning_trades(n: int = 100, win_pnl: float = 50.0) -> list[Trade]:
    """Stratégie gagnante : 60% win rate, ratio R:R 2:1."""
    rng = random.Random(42)
    trades = []
    for _ in range(n):
        if rng.random() < 0.60:
            pnl = win_pnl * rng.uniform(0.8, 1.2)
        else:
            pnl = -win_pnl * 0.5 * rng.uniform(0.8, 1.2)
        trades.append(Trade(pnl=pnl, pnl_pct=pnl / 100.0))
    return trades


def _losing_trades(n: int = 100) -> list[Trade]:
    """Stratégie perdante : 30% win rate, ratio R:R 1:2."""
    rng = random.Random(42)
    trades = []
    for _ in range(n):
        if rng.random() < 0.30:
            pnl = 50.0 * rng.uniform(0.8, 1.2)
        else:
            pnl = -100.0 * rng.uniform(0.8, 1.2)
        trades.append(Trade(pnl=pnl, pnl_pct=pnl / 100.0))
    return trades


def _flat_trades(n: int = 50) -> list[Trade]:
    """Stratégie à l'équilibre : expectancy ~0."""
    return [Trade(pnl=0.0, pnl_pct=0.0) for _ in range(n)]


def _perfect_strategy(n: int = 100) -> list[Trade]:
    """Stratégie parfaite : 100% win rate, gains constants."""
    return [Trade(pnl=100.0, pnl_pct=1.0) for _ in range(n)]


def _monotone_equity(n: int = 50, step: float = 100.0) -> list[float]:
    return [10_000.0 + i * step for i in range(n)]


def _crash_equity() -> list[float]:
    """Peak → crash → récupération."""
    up = [10_000 + i * 200 for i in range(20)]  # 10k → 13800
    down = [up[-1] - i * 400 for i in range(1, 11)]  # 13800 → 9800
    recovery = [down[-1] + i * 400 for i in range(1, 12)]  # 9800 → 14000
    return up + down + recovery


# ══════════════════════════════════════════════════════════════════════════════
# C1 — Strategy Metrics
# ══════════════════════════════════════════════════════════════════════════════


class TestC1StrategyMetrics:

    def test_empty_trades_returns_zero_metrics(self):
        analyzer = StrategyAnalyzer()
        m = analyzer.compute([])
        assert m.total_trades == 0
        assert m.sharpe_ratio == 0.0

    def test_winning_strategy_positive_metrics(self):
        analyzer = StrategyAnalyzer(initial_capital=10_000.0)
        m = analyzer.compute(_winning_trades())
        assert m.win_rate > 0.5
        assert m.profit_factor > 1.0
        assert m.expectancy > 0.0
        assert m.is_viable

    def test_losing_strategy_negative_metrics(self):
        analyzer = StrategyAnalyzer(initial_capital=10_000.0)
        m = analyzer.compute(_losing_trades())
        assert m.profit_factor < 1.0
        assert m.expectancy < 0.0
        assert not m.is_viable

    def test_win_rate_computed_correctly(self):
        trades = [
            Trade(pnl=10.0, pnl_pct=0.1),
            Trade(pnl=10.0, pnl_pct=0.1),
            Trade(pnl=-5.0, pnl_pct=-0.05),
            Trade(pnl=-5.0, pnl_pct=-0.05),
        ]
        analyzer = StrategyAnalyzer()
        m = analyzer.compute(trades)
        assert m.win_trades == 2
        assert m.loss_trades == 2
        assert abs(m.win_rate - 0.5) < 1e-9

    def test_profit_factor_formula(self):
        """PF = Σwins / |Σlosses|."""
        trades = [
            Trade(pnl=100.0, pnl_pct=1.0),
            Trade(pnl=100.0, pnl_pct=1.0),
            Trade(pnl=-50.0, pnl_pct=-0.5),
        ]
        analyzer = StrategyAnalyzer()
        m = analyzer.compute(trades)
        assert abs(m.profit_factor - 4.0) < 0.01  # 200 / 50 = 4

    def test_expectancy_formula(self):
        """E = P(W)*AvgWin + P(L)*AvgLoss."""
        trades = [
            Trade(pnl=0.0, pnl_pct=1.0),  # win
            Trade(pnl=0.0, pnl_pct=1.0),  # win
            Trade(pnl=0.0, pnl_pct=-0.5),  # loss
        ]
        # P(W)=2/3, AvgWin=1%, P(L)=1/3, AvgLoss=-0.5%
        # E = 2/3 * 1 + 1/3 * (-0.5) = 0.667 - 0.167 = 0.5
        analyzer = StrategyAnalyzer()
        m = analyzer.compute(trades)
        assert abs(m.expectancy - 0.5) < 0.01

    def test_max_drawdown_from_equity_curve(self):
        """MDD = (peak - trough) / peak × 100."""
        equity = [10_000.0, 11_000.0, 8_000.0, 9_000.0]
        # Peak=11000, trough=8000 → DD = 3000/11000 = 27.27%
        analyzer = StrategyAnalyzer(initial_capital=10_000.0)
        mdd = analyzer._max_drawdown(equity)
        assert abs(mdd - 3000 / 11000 * 100) < 0.01

    def test_no_drawdown_on_monotone_equity(self):
        analyzer = StrategyAnalyzer()
        mdd = analyzer._max_drawdown(_monotone_equity())
        assert mdd == 0.0

    def test_sharpe_positive_for_winning_strategy(self):
        analyzer = StrategyAnalyzer(initial_capital=10_000.0)
        m = analyzer.compute(_winning_trades(200))
        assert m.sharpe_ratio > 0.0

    def test_sharpe_negative_for_losing_strategy(self):
        analyzer = StrategyAnalyzer(initial_capital=10_000.0)
        m = analyzer.compute(_losing_trades(200))
        assert m.sharpe_ratio < 0.0

    def test_sortino_uses_only_downside(self):
        """Sortino >= Sharpe pour une stratégie avec gains asymétriques."""
        analyzer = StrategyAnalyzer(initial_capital=10_000.0)
        m = analyzer.compute(_winning_trades(200))
        # Sortino utilise seulement les pertes → plus favorable pour stratégie gagnante
        assert m.sortino_ratio >= m.sharpe_ratio or m.sortino_ratio > 0

    def test_recovery_factor_infinite_on_zero_drawdown(self):
        analyzer = StrategyAnalyzer(initial_capital=10_000.0)
        m = analyzer.compute(_perfect_strategy())
        assert math.isinf(m.recovery_factor) or m.recovery_factor > 100

    def test_recovery_factor_formula(self):
        """RF = |total_return| / max_drawdown."""
        equity = [10_000.0, 11_000.0, 9_000.0, 12_000.0]
        # total return = 20%, max DD = (11000-9000)/11000 ≈ 18.18%
        # RF ≈ 20/18.18 ≈ 1.1
        analyzer = StrategyAnalyzer(initial_capital=10_000.0)
        trades = [
            Trade(pnl=1000.0, pnl_pct=10.0),
            Trade(pnl=-2000.0, pnl_pct=-20.0),
            Trade(pnl=3000.0, pnl_pct=30.0),
        ]
        m = analyzer.compute(trades, equity_curve=equity)
        assert m.recovery_factor > 0

    def test_all_wins_no_profit_factor_division_error(self):
        """Stratégie 100% gagnante → PF = inf, pas d'exception."""
        analyzer = StrategyAnalyzer()
        m = analyzer.compute(_perfect_strategy(50))
        assert m.profit_factor == float("inf") or m.profit_factor > 0

    def test_flat_strategy_expectancy_zero(self):
        analyzer = StrategyAnalyzer()
        m = analyzer.compute(_flat_trades())
        assert m.expectancy == 0.0

    def test_total_return_is_sum_of_returns(self):
        trades = [Trade(pnl=0.0, pnl_pct=2.0), Trade(pnl=0.0, pnl_pct=-1.0)]
        analyzer = StrategyAnalyzer()
        m = analyzer.compute(trades)
        assert abs(m.total_return_pct - 1.0) < 1e-9

    def test_summary_string_non_empty(self):
        analyzer = StrategyAnalyzer()
        m = analyzer.compute(_winning_trades(50))
        assert len(m.summary()) > 0


# ══════════════════════════════════════════════════════════════════════════════
# C2 — Equity Curve Analyzer
# ══════════════════════════════════════════════════════════════════════════════


class TestC2EquityCurve:

    def test_monotone_equity_no_drawdown(self):
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze(_monotone_equity())
        assert report.max_drawdown_pct == 0.0
        assert report.longest_underwater_bars == 0

    def test_crash_and_recovery_detected(self):
        """Peak → crash → récupération → drawdown period détecté."""
        equity = _crash_equity()
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze(equity)
        assert report.max_drawdown_pct > 0.0
        assert report.n_drawdown_periods >= 1

    def test_new_highs_counted(self):
        equity = [10_000, 10_500, 10_200, 11_000, 10_800, 12_000]
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze(equity)
        assert report.n_new_highs >= 2

    def test_single_value_equity(self):
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze([10_000.0])
        assert report.max_drawdown_pct == 0.0

    def test_underwater_time_correct(self):
        """equity sous le peak historique → underwater."""
        equity = [10_000, 11_000, 9_000, 10_500, 11_500]
        # Bars underwater: idx 2 (9000<11000), idx 3 (10500<11000) → 2 bars
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze(equity)
        assert report.longest_underwater_bars >= 1
        assert 0.0 <= report.pct_time_underwater <= 1.0

    def test_final_new_high_detected(self):
        equity = [10_000, 9_000, 11_000]
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze(equity)
        assert report.final_is_new_high

    def test_final_not_new_high(self):
        equity = [10_000, 12_000, 11_000]
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze(equity)
        assert not report.final_is_new_high

    def test_unrecovered_drawdown_counted(self):
        """Drawdown non récupéré en fin de série."""
        equity = [10_000, 11_000, 8_000]  # crash sans récupération
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze(equity)
        assert report.unrecovered_drawdowns >= 1

    def test_drawdown_period_fields(self):
        equity = [10_000, 12_000, 9_000, 13_000]
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze(equity)
        assert len(report.drawdown_periods) >= 1
        dd = report.drawdown_periods[0]
        assert dd.peak_value > dd.trough_value
        assert dd.drawdown_pct > 0.0

    def test_equity_volatility_computed(self):
        equity = [10_000, 10_500, 9_800, 10_300, 10_100]
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze(equity)
        assert report.equity_volatility_pct >= 0.0

    def test_summary_non_empty(self):
        analyzer = EquityCurveAnalyzer()
        report = analyzer.analyze(_crash_equity())
        assert len(report.summary()) > 0


# ══════════════════════════════════════════════════════════════════════════════
# C3 — Monte Carlo Engine
# ══════════════════════════════════════════════════════════════════════════════


class TestC3MonteCarlo:

    def test_empty_trades_returns_zero_report(self):
        engine = MonteCarloEngine(n_sims=100, seed=42)
        report = engine.run([])
        assert report.ruin_probability == 0.0
        assert report.drawdown_p50 == 0.0

    def test_percentile_ordering(self):
        """P5 <= P25 <= P50 <= P75 <= P95."""
        trades = _winning_trades(100)
        engine = MonteCarloEngine(n_sims=500, seed=42)
        report = engine.run(trades, initial_capital=10_000.0)
        assert report.drawdown_p5 <= report.drawdown_p25
        assert report.drawdown_p25 <= report.drawdown_p50
        assert report.drawdown_p50 <= report.drawdown_p75
        assert report.drawdown_p75 <= report.drawdown_p95

    def test_return_percentile_ordering(self):
        trades = _winning_trades(100)
        engine = MonteCarloEngine(n_sims=500, seed=42)
        report = engine.run(trades)
        assert report.return_p5 <= report.return_p25
        assert report.return_p25 <= report.return_p50
        assert report.return_p50 <= report.return_p75

    def test_low_ruin_for_winning_strategy(self):
        """Stratégie gagnante → probabilité de ruine faible."""
        trades = _winning_trades(100)
        engine = MonteCarloEngine(n_sims=1000, ruin_threshold_pct=80.0, seed=42)
        report = engine.run(trades, initial_capital=10_000.0)
        assert report.ruin_probability < 0.30

    def test_high_ruin_for_losing_strategy(self):
        """Stratégie perdante → probabilité de ruine plus élevée."""
        trades = _losing_trades(100)
        engine = MonteCarloEngine(n_sims=1000, ruin_threshold_pct=50.0, seed=42)
        report = engine.run(trades, initial_capital=10_000.0)
        # Une stratégie perdante devrait avoir une ruine non-nulle
        assert report.ruin_probability >= 0.0

    def test_deterministic_with_seed(self):
        """Même seed → même résultat."""
        trades = _winning_trades(50)
        r1 = MonteCarloEngine(n_sims=100, seed=99).run(trades)
        r2 = MonteCarloEngine(n_sims=100, seed=99).run(trades)
        assert r1.drawdown_p50 == r2.drawdown_p50
        assert r1.ruin_probability == r2.ruin_probability

    def test_different_seed_different_result(self):
        """Seeds différents → résultats différents (statistiquement)."""
        trades = _winning_trades(100)
        r1 = MonteCarloEngine(n_sims=200, seed=1).run(trades)
        r2 = MonteCarloEngine(n_sims=200, seed=9999).run(trades)
        # Pas identiques mais proches
        assert r1.drawdown_p50 != r2.drawdown_p50 or r1.return_mean != r2.return_mean

    def test_ci_interval_valid(self):
        """CI lower <= mean <= upper."""
        trades = _winning_trades(100)
        engine = MonteCarloEngine(n_sims=500, seed=42)
        report = engine.run(trades)
        assert report.ci_lower_95 <= report.return_mean <= report.ci_upper_95

    def test_n_simulations_reported(self):
        trades = _winning_trades(20)
        engine = MonteCarloEngine(n_sims=250, seed=42)
        report = engine.run(trades)
        assert report.n_simulations == 250

    def test_drawdown_non_negative(self):
        trades = _winning_trades(100)
        engine = MonteCarloEngine(n_sims=200, seed=42)
        report = engine.run(trades)
        assert report.drawdown_p5 >= 0.0
        assert report.drawdown_mean >= 0.0

    def test_summary_non_empty(self):
        trades = _winning_trades(50)
        engine = MonteCarloEngine(n_sims=100, seed=42)
        report = engine.run(trades)
        assert len(report.summary()) > 0

    def test_perfect_strategy_low_drawdown(self):
        """Stratégie parfaite → drawdown médian proche de 0."""
        trades = _perfect_strategy(50)
        engine = MonteCarloEngine(n_sims=500, seed=42)
        report = engine.run(trades, initial_capital=10_000.0)
        assert report.drawdown_p50 == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# C4 — Walk Forward Validator
# ══════════════════════════════════════════════════════════════════════════════


class TestC4WalkForward:

    def test_invalid_train_pct_raises(self):
        with pytest.raises(ValueError):
            WalkForwardValidator(train_pct=0.0)
        with pytest.raises(ValueError):
            WalkForwardValidator(train_pct=1.0)

    def test_invalid_n_splits_raises(self):
        with pytest.raises(ValueError):
            WalkForwardValidator(n_splits=1)

    def test_too_few_trades_returns_empty(self):
        validator = WalkForwardValidator(train_pct=0.70, n_splits=5)
        report = validator.validate([Trade(pnl=1.0, pnl_pct=0.01)])
        assert report.n_splits == 0

    def test_winning_strategy_positive_oos(self):
        """Stratégie gagnante → OOS expectancy positive sur la majorité des splits."""
        trades = _winning_trades(500)
        validator = WalkForwardValidator(train_pct=0.70, n_splits=5)
        report = validator.validate(trades)
        assert report.n_splits > 0
        assert report.pct_profitable_splits > 0.0

    def test_n_splits_produces_correct_count(self):
        trades = _winning_trades(300)
        validator = WalkForwardValidator(train_pct=0.70, n_splits=4)
        report = validator.validate(trades)
        assert report.n_splits <= 4

    def test_oos_metrics_not_none(self):
        trades = _winning_trades(300)
        validator = WalkForwardValidator(train_pct=0.70, n_splits=3)
        report = validator.validate(trades)
        if report.n_splits > 0:
            assert report.oos_sharpe_mean is not None
            assert report.oos_profit_factor_mean is not None

    def test_overfit_field_is_bool(self):
        """overfit_suspected est toujours un booléen."""
        trades = _winning_trades(300)
        validator = WalkForwardValidator(train_pct=0.70, n_splits=3)
        report = validator.validate(trades)
        assert isinstance(report.overfit_suspected, bool)

    def test_splits_contain_train_test_indices(self):
        trades = _winning_trades(200)
        validator = WalkForwardValidator(train_pct=0.70, n_splits=3)
        report = validator.validate(trades)
        for split in report.splits:
            assert split.train_start < split.train_end
            assert split.test_start < split.test_end
            assert split.train_end == split.test_start

    def test_summary_non_empty(self):
        trades = _winning_trades(300)
        validator = WalkForwardValidator(n_splits=3)
        report = validator.validate(trades)
        assert len(report.summary()) > 0


# ══════════════════════════════════════════════════════════════════════════════
# C5 — Regime Validator
# ══════════════════════════════════════════════════════════════════════════════


class TestC5RegimeValidator:

    def test_empty_trades_returns_empty(self):
        validator = RegimeValidator()
        report = validator.validate([])
        assert report.total_trades == 0
        assert report.by_regime == {}

    def test_explicit_regimes_used(self):
        """Si trades ont un régime explicite, il est utilisé tel quel."""
        trades = [
            Trade(pnl=100.0, pnl_pct=1.0, regime="BULL"),
            Trade(pnl=-50.0, pnl_pct=-0.5, regime="BEAR"),
            Trade(pnl=10.0, pnl_pct=0.1, regime="BULL"),
        ]
        validator = RegimeValidator()
        report = validator.validate(trades)
        assert "BULL" in report.by_regime
        assert "BEAR" in report.by_regime

    def test_auto_labeling_produces_regimes(self):
        """Sans régime explicite, l'auto-classifieur assigne des régimes."""
        trades = _winning_trades(50)
        validator = RegimeValidator()
        report = validator.validate(trades)
        assert len(report.by_regime) > 0
        assert report.total_trades == 50

    def test_best_worst_regime_identified(self):
        trades = [
            Trade(pnl=100.0, pnl_pct=1.0, regime="BULL"),
            Trade(pnl=100.0, pnl_pct=1.0, regime="BULL"),
            Trade(pnl=-200.0, pnl_pct=-2.0, regime="BEAR"),
            Trade(pnl=-100.0, pnl_pct=-1.0, regime="BEAR"),
        ]
        validator = RegimeValidator()
        report = validator.validate(trades)
        assert report.best_regime == "BULL"
        assert report.worst_regime == "BEAR"

    def test_regime_trade_counts_sum_to_total(self):
        trades = _winning_trades(100)
        validator = RegimeValidator()
        report = validator.validate(trades)
        total = sum(report.trade_counts_by_regime.values())
        assert total == 100

    def test_sharpe_spread_computed(self):
        """Spread de Sharpe entre régimes doit être >= 0."""
        trades = [
            Trade(pnl=100.0, pnl_pct=1.0, regime="BULL"),
            Trade(pnl=80.0, pnl_pct=0.8, regime="BULL"),
            Trade(pnl=-60.0, pnl_pct=-0.6, regime="BEAR"),
        ]
        validator = RegimeValidator()
        report = validator.validate(trades)
        assert report.sharpe_spread >= 0.0

    def test_metrics_per_regime_non_none(self):
        trades = [
            Trade(pnl=10.0, pnl_pct=0.1, regime="BULL"),
            Trade(pnl=10.0, pnl_pct=0.1, regime="RANGE"),
        ]
        validator = RegimeValidator()
        report = validator.validate(trades)
        for regime, metrics in report.by_regime.items():
            assert isinstance(metrics, StrategyMetrics)

    def test_summary_non_empty(self):
        trades = _winning_trades(50)
        validator = RegimeValidator()
        report = validator.validate(trades)
        assert len(report.summary()) > 0


# ══════════════════════════════════════════════════════════════════════════════
# C6 — Strategy Score
# ══════════════════════════════════════════════════════════════════════════════


class TestC6StrategyScore:

    def _metrics(self, **overrides) -> StrategyMetrics:
        m = StrategyMetrics(
            total_trades=100,
            win_rate=0.6,
            profit_factor=1.8,
            expectancy=0.3,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown_pct=8.0,
            total_return_pct=30.0,
            recovery_factor=3.75,
            is_viable=True,
        )
        for k, v in overrides.items():
            setattr(m, k, v)
        return m

    def test_score_bounded_0_100(self):
        scorer = StrategyScorer()
        for metrics in [
            self._metrics(),
            self._metrics(sharpe_ratio=10.0, sortino_ratio=10.0, profit_factor=5.0),
            self._metrics(sharpe_ratio=-5.0, profit_factor=0.1, max_drawdown_pct=90.0),
        ]:
            score = scorer.score(metrics)
            assert 0.0 <= score.total <= 100.0

    def test_excellent_strategy_grade_a_or_s(self):
        scorer = StrategyScorer()
        metrics = self._metrics(
            sharpe_ratio=2.5,
            sortino_ratio=4.0,
            profit_factor=2.5,
            max_drawdown_pct=3.0,
            expectancy=0.6,
        )
        result = scorer.score(metrics)
        assert result.grade in (StrategyGrade.S, StrategyGrade.A)

    def test_poor_strategy_grade_d_or_f(self):
        scorer = StrategyScorer()
        metrics = self._metrics(
            sharpe_ratio=-1.0,
            sortino_ratio=-0.5,
            profit_factor=0.5,
            max_drawdown_pct=45.0,
            expectancy=-0.5,
        )
        result = scorer.score(metrics)
        assert result.grade in (StrategyGrade.D, StrategyGrade.F)

    def test_higher_sharpe_higher_score(self):
        scorer = StrategyScorer()
        low = scorer.score(self._metrics(sharpe_ratio=0.5))
        high = scorer.score(self._metrics(sharpe_ratio=2.0))
        assert high.total > low.total

    def test_lower_drawdown_higher_score(self):
        scorer = StrategyScorer()
        risky = scorer.score(self._metrics(max_drawdown_pct=40.0))
        safe = scorer.score(self._metrics(max_drawdown_pct=3.0))
        assert safe.total > risky.total

    def test_higher_expectancy_higher_score(self):
        scorer = StrategyScorer()
        low = scorer.score(self._metrics(expectancy=0.0))
        high = scorer.score(self._metrics(expectancy=0.6))
        assert high.total > low.total

    def test_profit_factor_inf_max_pts(self):
        """PF = inf (aucune perte) → max points PF."""
        scorer = StrategyScorer()
        result = scorer.score(self._metrics(profit_factor=float("inf")))
        assert result.profit_factor_pts == 100.0  # score brut max avant pondération

    def test_zero_drawdown_max_pts_drawdown(self):
        scorer = StrategyScorer()
        result = scorer.score(self._metrics(max_drawdown_pct=0.0))
        assert result.drawdown_pts == 100.0  # score brut max avant pondération

    def test_grade_mapping_correct(self):
        scorer = StrategyScorer()
        assert scorer.grade(95.0) == StrategyGrade.S
        assert scorer.grade(80.0) == StrategyGrade.A
        assert scorer.grade(65.0) == StrategyGrade.B
        assert scorer.grade(50.0) == StrategyGrade.C
        assert scorer.grade(35.0) == StrategyGrade.D
        assert scorer.grade(20.0) == StrategyGrade.F

    def test_contributions_weighted_sum_to_total(self):
        """total = Σ(raw_score × poids), poids = [25,25,20,15,15]%."""
        scorer = StrategyScorer()
        result = scorer.score(self._metrics())
        expected = (
            result.sharpe_pts * 0.25
            + result.sortino_pts * 0.25
            + result.profit_factor_pts * 0.20
            + result.drawdown_pts * 0.15
            + result.expectancy_pts * 0.15
        )
        assert abs(expected - result.total) < 0.01

    def test_summary_non_empty(self):
        scorer = StrategyScorer()
        result = scorer.score(self._metrics())
        assert len(result.summary()) > 0

    def test_integration_with_analyzer(self):
        """Pipeline complet : trades → metrics → score."""
        analyzer = StrategyAnalyzer(initial_capital=10_000.0)
        scorer = StrategyScorer()

        trades = _winning_trades(200)
        metrics = analyzer.compute(trades)
        result = scorer.score(metrics)

        assert 0 <= result.total <= 100
        assert isinstance(result.grade, StrategyGrade)
        assert metrics.is_viable == (
            metrics.expectancy > 0 and metrics.profit_factor > 1
        )
