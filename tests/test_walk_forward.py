"""
tests/test_walk_forward.py — P3 : Tests walk-forward, OOS metrics, stabilite, degradation.

Couvre :
  - WindowSplitter (no-leakage garanti, rolling, anchored, gap, edge cases)
  - OOSMetrics (Sharpe, Sortino, drawdown, win rate, profit factor, Calmar)
  - StabilityScore (CV, penalite regime negatif, cas limites)
  - DegradationTracker (z-score, Mann-Kendall, win rate floor)
  - WalkForwardLoop (isolation train/test, overfitting ratio, erreurs)
  - WalkForwardEngine (end-to-end, criteres de robustesse)
"""

from __future__ import annotations

import math
import random

import pytest

from metrics.oos_metrics import OOSMetrics, TradeResult, compute_oos_metrics
from metrics.stability_score import compute_stability_score
from monitor.degradation_tracker import DegradationTracker, _mann_kendall
from walk_forward.engine import WalkForwardEngine
from walk_forward.walk_forward_loop import FoldResult, WalkForwardLoop
from walk_forward.window_splitter import WalkForwardWindow, WindowSplitter

SEED = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trades(pnl_list: list[float], regime: str = "bull") -> list[TradeResult]:
    return [
        TradeResult(timestamp_ms=i * 1000, pnl_pct=p, regime=regime)
        for i, p in enumerate(pnl_list)
    ]


def _make_metrics(
    sharpe: float = 1.0,
    win_rate: float = 0.6,
    max_dd: float = -5.0,
    n_trades: int = 20,
    total_return: float = 10.0,
    profit_factor: float = 1.5,
) -> OOSMetrics:
    return OOSMetrics(
        n_trades=n_trades,
        total_return_pct=total_return,
        sharpe_ratio=sharpe,
        sortino_ratio=sharpe * 1.2,
        max_drawdown_pct=max_dd,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win_pct=2.0,
        avg_loss_pct=-1.0,
        expectancy_pct=0.8,
        calmar_ratio=abs(total_return / max_dd) if max_dd < 0 else float("inf"),
    )


# ---------------------------------------------------------------------------
# TestWindowSplitter
# ---------------------------------------------------------------------------


class TestWindowSplitter:

    def test_basic_rolling_no_overlap(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100)
        folds = list(sp.split())
        for w in folds:
            # Garantie centrale : aucun chevauchement
            assert w.train_end <= w.test_start

    def test_basic_rolling_fold_count(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        folds = list(sp.split())
        assert len(folds) == 4  # fold 0..3

    def test_rolling_consecutive_folds_advance(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        folds = list(sp.split())
        for i in range(len(folds) - 1):
            assert folds[i + 1].train_start == folds[i].train_start + 100

    def test_rolling_train_size_constant(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=50)
        for w in sp.split():
            assert w.train_size == 600

    def test_anchored_train_start_always_zero(self):
        sp = WindowSplitter(
            n_samples=1000, train_size=600, test_size=100, anchored=True
        )
        for w in sp.split():
            assert w.train_start == 0

    def test_anchored_train_grows(self):
        sp = WindowSplitter(
            n_samples=1000, train_size=600, test_size=100, step=100, anchored=True
        )
        folds = list(sp.split())
        for i in range(1, len(folds)):
            assert folds[i].train_size > folds[i - 1].train_size

    def test_gap_respected(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, gap=20)
        for w in sp.split():
            assert w.test_start == w.train_end + 20
            assert w.gap_size == 20

    def test_gap_zero_test_adjacent_to_train(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, gap=0)
        for w in sp.split():
            assert w.test_start == w.train_end

    def test_test_end_within_bounds(self):
        sp = WindowSplitter(n_samples=500, train_size=300, test_size=50, step=50)
        for w in sp.split():
            assert w.test_end <= 500

    def test_no_folds_when_too_small(self):
        # train+test=1001 > n_samples=1000
        with pytest.raises(ValueError, match="trop petit"):
            WindowSplitter(n_samples=100, train_size=80, test_size=30)

    def test_negative_gap_raises(self):
        with pytest.raises(ValueError, match="gap"):
            WindowSplitter(n_samples=1000, train_size=600, test_size=100, gap=-1)

    def test_zero_train_raises(self):
        with pytest.raises(ValueError):
            WindowSplitter(n_samples=1000, train_size=0, test_size=100)

    def test_zero_test_raises(self):
        with pytest.raises(ValueError):
            WindowSplitter(n_samples=1000, train_size=600, test_size=0)

    def test_fold_indices_sequential(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100)
        folds = list(sp.split())
        for i, w in enumerate(folds):
            assert w.fold_index == i

    def test_n_folds_property(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        assert sp.n_folds == 4

    def test_window_leakage_raises_on_construction(self):
        with pytest.raises(ValueError, match="leakage"):
            WalkForwardWindow(
                fold_index=0, train_start=0, train_end=100, test_start=50, test_end=150
            )

    def test_window_valid_construction(self):
        w = WalkForwardWindow(
            fold_index=0, train_start=0, train_end=600, test_start=600, test_end=700
        )
        assert w.train_size == 600
        assert w.test_size == 100
        assert w.gap_size == 0

    def test_step_defaults_to_test_size(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100)
        assert sp.step == 100

    def test_all_data_indices_within_bounds(self):
        sp = WindowSplitter(n_samples=300, train_size=200, test_size=50, step=25)
        for w in sp.split():
            assert w.train_start >= 0
            assert w.test_end <= 300

    def test_gap_prevents_feature_leakage(self):
        """Gap=20 simule une MA-20 : le dernier sample train ne contamine pas test."""
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, gap=20)
        for w in sp.split():
            assert w.test_start - w.train_end == 20


# ---------------------------------------------------------------------------
# TestOOSMetrics
# ---------------------------------------------------------------------------


class TestOOSMetrics:

    def test_empty_trades(self):
        m = compute_oos_metrics([])
        assert m.n_trades == 0
        assert m.total_return_pct == 0.0
        assert m.sharpe_ratio == 0.0

    def test_single_trade_win(self):
        m = compute_oos_metrics(_trades([5.0]))
        assert m.n_trades == 1
        assert m.total_return_pct == pytest.approx(5.0, rel=1e-4)
        assert m.win_rate == pytest.approx(1.0)
        assert m.sharpe_ratio == 0.0  # std=0 avec 1 trade

    def test_single_trade_loss(self):
        m = compute_oos_metrics(_trades([-3.0]))
        assert m.total_return_pct == pytest.approx(-3.0, rel=1e-4)
        assert m.win_rate == 0.0
        assert m.max_drawdown_pct == pytest.approx(-3.0, rel=1e-4)

    def test_all_wins_no_drawdown(self):
        m = compute_oos_metrics(_trades([1.0] * 10))
        assert m.win_rate == pytest.approx(1.0)
        assert m.max_drawdown_pct == pytest.approx(0.0)
        assert math.isinf(m.profit_factor)

    def test_all_losses(self):
        m = compute_oos_metrics(_trades([-1.0] * 10))
        assert m.win_rate == pytest.approx(0.0)
        assert m.profit_factor == pytest.approx(0.0)
        assert m.max_drawdown_pct < 0

    def test_sharpe_positive_for_winning_strategy(self):
        rng = random.Random(SEED)
        returns = [rng.gauss(0.5, 1.0) for _ in range(50)]
        m = compute_oos_metrics(_trades(returns))
        assert m.sharpe_ratio > 0

    def test_sharpe_negative_for_losing_strategy(self):
        rng = random.Random(SEED)
        returns = [rng.gauss(-0.5, 1.0) for _ in range(50)]
        m = compute_oos_metrics(_trades(returns))
        assert m.sharpe_ratio < 0

    def test_sortino_geq_sharpe_for_positive_returns(self):
        rng = random.Random(SEED)
        returns = [abs(rng.gauss(0.5, 1.0)) for _ in range(50)]  # tous positifs
        m = compute_oos_metrics(_trades(returns))
        assert math.isinf(m.sortino_ratio) or m.sortino_ratio > 0

    def test_max_drawdown_negative(self):
        returns = [2.0, -5.0, 1.0, -3.0, 4.0]
        m = compute_oos_metrics(_trades(returns))
        assert m.max_drawdown_pct < 0

    def test_max_drawdown_zero_all_positive(self):
        m = compute_oos_metrics(_trades([1.0, 2.0, 0.5]))
        assert m.max_drawdown_pct == pytest.approx(0.0)

    def test_profit_factor_formula(self):
        # wins=[3, 3] losses=[-1, -1] → PF = 6 / 2 = 3.0
        returns = [3.0, -1.0, 3.0, -1.0]
        m = compute_oos_metrics(_trades(returns))
        assert m.profit_factor == pytest.approx(3.0, rel=1e-4)

    def test_win_rate(self):
        returns = [1.0, 1.0, -1.0, -1.0, 1.0]  # 3 wins / 5
        m = compute_oos_metrics(_trades(returns))
        assert m.win_rate == pytest.approx(0.6)

    def test_expectancy_positive(self):
        # WR=0.6, avg_win=3, avg_loss=-1 → 0.6*3 + 0.4*(-1) = 1.4
        returns = [3.0, 3.0, 3.0, -1.0, -1.0]
        m = compute_oos_metrics(_trades(returns))
        assert m.expectancy_pct > 0

    def test_total_return_compounded(self):
        # 10% then -10% ≠ 0 (compound: 100*1.1*0.9 = 99)
        m = compute_oos_metrics(_trades([10.0, -10.0]))
        assert m.total_return_pct == pytest.approx(-1.0, rel=1e-4)

    def test_calmar_positive_return_positive_dd(self):
        returns = [2.0, -1.0, 2.0, -0.5, 3.0]
        m = compute_oos_metrics(_trades(returns))
        if m.max_drawdown_pct < 0:
            assert m.calmar_ratio > 0

    def test_calmar_inf_when_no_drawdown(self):
        m = compute_oos_metrics(_trades([1.0, 2.0, 3.0]))
        assert math.isinf(m.calmar_ratio)

    def test_is_profitable_true(self):
        rng = random.Random(SEED)
        returns = [abs(rng.gauss(1.0, 0.5)) for _ in range(30)]
        m = compute_oos_metrics(_trades(returns))
        assert m.is_profitable is True

    def test_is_profitable_false(self):
        m = compute_oos_metrics(_trades([-1.0] * 10))
        assert m.is_profitable is False

    def test_as_dict_keys(self):
        m = compute_oos_metrics(_trades([1.0, -0.5, 2.0]))
        d = m.as_dict()
        assert "n_trades" in d
        assert "sharpe_ratio" in d
        assert "max_drawdown_pct" in d
        assert "is_profitable" in d
        assert "risk_adjusted_score" in d

    def test_annualization_affects_sharpe(self):
        returns = [0.5, -0.2, 0.8, -0.1, 0.3] * 10
        m252 = compute_oos_metrics(_trades(returns), annualization_factor=252.0)
        m1 = compute_oos_metrics(_trades(returns), annualization_factor=1.0)
        assert abs(m252.sharpe_ratio) > abs(m1.sharpe_ratio)


# ---------------------------------------------------------------------------
# TestStabilityScore
# ---------------------------------------------------------------------------


class TestStabilityScore:

    def test_single_regime_score_one(self):
        m = {"bull": _make_metrics(sharpe=1.5)}
        r = compute_stability_score(m)
        assert r.stability_score == pytest.approx(1.0)
        assert r.regime_count == 1

    def test_two_equal_regimes_high_score(self):
        m = {
            "bull": _make_metrics(sharpe=1.5),
            "bear": _make_metrics(sharpe=1.5),
        }
        r = compute_stability_score(m)
        assert r.stability_score > 0.9  # CV=0 → score=1.0

    def test_very_different_regimes_low_score(self):
        m = {
            "bull": _make_metrics(sharpe=3.0),
            "bear": _make_metrics(sharpe=0.1),
        }
        r = compute_stability_score(m)
        assert r.stability_score < 0.7

    def test_negative_regime_penalizes(self):
        m_no_neg = {
            "bull": _make_metrics(sharpe=1.5),
            "stable": _make_metrics(sharpe=1.0),
        }
        m_with_neg = {
            "bull": _make_metrics(sharpe=1.5),
            "bear": _make_metrics(sharpe=-0.5),
        }
        s_no_neg = compute_stability_score(m_no_neg).stability_score
        s_with_neg = compute_stability_score(m_with_neg).stability_score
        assert s_with_neg < s_no_neg

    def test_worst_regime_correct(self):
        m = {
            "bull": _make_metrics(sharpe=2.0),
            "bear": _make_metrics(sharpe=0.5),
            "stable": _make_metrics(sharpe=1.2),
        }
        r = compute_stability_score(m)
        assert r.worst_regime == "bear"
        assert r.best_regime == "bull"

    def test_is_regime_stable_true(self):
        m = {
            "bull": _make_metrics(sharpe=1.5),
            "bear": _make_metrics(sharpe=1.2),
        }
        r = compute_stability_score(m)
        assert r.is_regime_stable is True

    def test_is_regime_stable_false_negative_sharpe(self):
        m = {
            "bull": _make_metrics(sharpe=2.0),
            "bear": _make_metrics(sharpe=-1.0),
        }
        r = compute_stability_score(m)
        assert r.is_regime_stable is False

    def test_min_trades_filter(self):
        """Regime avec n_trades < min_trades_per_regime ignore."""
        m = {
            "bull": _make_metrics(sharpe=2.0, n_trades=10),
            "noise": _make_metrics(sharpe=-5.0, n_trades=1),  # filtre
        }
        r = compute_stability_score(m, min_trades_per_regime=3)
        # "noise" filtre → 1 seul regime valide → score=1.0
        assert r.stability_score == pytest.approx(1.0)

    def test_empty_regime_dict(self):
        r = compute_stability_score({})
        assert r.stability_score == pytest.approx(1.0)

    def test_as_dict_keys(self):
        m = {"bull": _make_metrics(), "bear": _make_metrics(sharpe=0.8)}
        r = compute_stability_score(m)
        d = r.as_dict()
        assert "stability_score" in d
        assert "sharpe_cv" in d
        assert "is_regime_stable" in d


# ---------------------------------------------------------------------------
# TestMannKendall
# ---------------------------------------------------------------------------


class TestMannKendall:

    def test_increasing_series_positive_tau(self):
        tau, p = _mann_kendall([1.0, 2.0, 3.0, 4.0, 5.0])
        assert tau == pytest.approx(1.0)
        assert p < 0.05

    def test_decreasing_series_negative_tau(self):
        tau, p = _mann_kendall([5.0, 4.0, 3.0, 2.0, 1.0])
        assert tau == pytest.approx(-1.0)
        assert p < 0.05

    def test_constant_series_tau_zero(self):
        tau, p = _mann_kendall([3.0, 3.0, 3.0, 3.0])
        assert tau == pytest.approx(0.0)

    def test_too_few_points(self):
        tau, p = _mann_kendall([1.0, 2.0])
        assert tau == 0.0
        assert p == 1.0

    def test_single_point(self):
        tau, p = _mann_kendall([5.0])
        assert p == 1.0

    def test_noisy_uptrend_positive_p(self):
        rng = random.Random(SEED)
        data = [i * 0.5 + rng.gauss(0, 0.1) for i in range(20)]
        tau, p = _mann_kendall(data)
        assert tau > 0

    def test_noisy_downtrend_negative_tau(self):
        rng = random.Random(SEED)
        data = [-i * 0.5 + rng.gauss(0, 0.1) for i in range(20)]
        tau, p = _mann_kendall(data)
        assert tau < 0


# ---------------------------------------------------------------------------
# TestDegradationTracker
# ---------------------------------------------------------------------------


class TestDegradationTracker:

    def test_no_alert_on_first_two_folds(self):
        tracker = DegradationTracker()
        e1 = tracker.record(0, _make_metrics(sharpe=1.0))
        e2 = tracker.record(1, _make_metrics(sharpe=0.9))
        assert e1 == []
        assert e2 == []

    def test_no_alert_stable_performance(self):
        tracker = DegradationTracker(window=5)
        for i in range(10):
            events = tracker.record(i, _make_metrics(sharpe=1.5, win_rate=0.65))
        assert not tracker.is_degrading

    def test_warning_on_sharp_drop(self):
        tracker = DegradationTracker(sharpe_z_warning=-1.5, sharpe_z_critical=-3.0)
        for i in range(5):
            tracker.record(i, _make_metrics(sharpe=1.5))
        # chute soudaine
        events = tracker.record(5, _make_metrics(sharpe=-2.0))
        warnings = [e for e in events if e.severity == "warning"]
        criticals = [e for e in events if e.severity == "critical"]
        assert len(warnings) + len(criticals) > 0

    def test_critical_on_extreme_drop(self):
        tracker = DegradationTracker(sharpe_z_critical=-2.0)
        for i in range(5):
            tracker.record(i, _make_metrics(sharpe=2.0, win_rate=0.7))
        events = tracker.record(5, _make_metrics(sharpe=-5.0, win_rate=0.1))
        assert any(e.severity == "critical" for e in events)

    def test_is_degrading_after_critical(self):
        tracker = DegradationTracker(sharpe_z_critical=-2.0)
        for i in range(5):
            tracker.record(i, _make_metrics(sharpe=2.0))
        tracker.record(5, _make_metrics(sharpe=-5.0))
        assert tracker.is_degrading is True

    def test_no_critical_stable(self):
        tracker = DegradationTracker()
        for i in range(10):
            tracker.record(i, _make_metrics(sharpe=1.0 + i * 0.1))  # ameliore
        assert tracker.is_degrading is False

    def test_win_rate_warning(self):
        tracker = DegradationTracker(winrate_floor=0.40, winrate_floor_crit=0.25)
        for i in range(5):
            tracker.record(i, _make_metrics(win_rate=0.65))
        events = tracker.record(5, _make_metrics(win_rate=0.30))  # entre floor et crit
        wr_events = [e for e in events if e.metric == "win_rate"]
        assert any(e.severity == "warning" for e in wr_events)

    def test_win_rate_critical(self):
        tracker = DegradationTracker(winrate_floor=0.40, winrate_floor_crit=0.25)
        for i in range(5):
            tracker.record(i, _make_metrics(win_rate=0.65))
        events = tracker.record(5, _make_metrics(win_rate=0.15))
        wr_events = [e for e in events if e.metric == "win_rate"]
        assert any(e.severity == "critical" for e in wr_events)

    def test_mann_kendall_declining_trend_detected(self):
        tracker = DegradationTracker(mk_alpha_critical=0.05)
        for i in range(8):
            tracker.record(i, _make_metrics(sharpe=2.0 - i * 0.3))
        # Tendance fortement declinante
        assert any(e.metric == "sharpe_trend" for e in tracker.all_events)

    def test_reset_clears_history(self):
        tracker = DegradationTracker()
        for i in range(5):
            tracker.record(i, _make_metrics(sharpe=-3.0, win_rate=0.1))
        tracker.reset()
        assert tracker.is_degrading is False
        assert tracker.all_events == []

    def test_summary_keys(self):
        tracker = DegradationTracker()
        for i in range(4):
            tracker.record(i, _make_metrics(sharpe=float(i)))
        s = tracker.summary()
        assert "n_folds_recorded" in s
        assert "is_degrading" in s
        assert "mk_tau" in s

    def test_event_as_dict(self):
        tracker = DegradationTracker(sharpe_z_critical=-1.5)
        for i in range(5):
            tracker.record(i, _make_metrics(sharpe=2.0))
        events = tracker.record(5, _make_metrics(sharpe=-4.0))
        if events:
            d = events[0].as_dict()
            assert "severity" in d
            assert "z_score" in d
            assert "trend_tau" in d


# ---------------------------------------------------------------------------
# TestWalkForwardLoop
# ---------------------------------------------------------------------------


class TestWalkForwardLoop:

    def _make_data(self, n: int = 1000) -> list[float]:
        rng = random.Random(SEED)
        return [rng.gauss(0.1, 1.0) for _ in range(n)]

    def _optimizer(self, train: list) -> dict:
        """Optimiseur minimal : retourne la moyenne du train comme seuil."""
        mu = sum(train) / len(train) if train else 0.0
        return {"threshold": mu}

    def _validator(self, test: list, params: dict) -> list[TradeResult]:
        """Validateur : trade si valeur > seuil."""
        threshold = params["threshold"]
        trades = []
        for i, val in enumerate(test):
            if abs(val) > abs(threshold):
                pnl = val * 0.1
                trades.append(TradeResult(timestamp_ms=i * 1000, pnl_pct=pnl))
        return trades

    def test_optimizer_receives_only_train(self):
        """Le validateur ne doit jamais voir les donnees d'entrainement."""
        seen_in_optimizer = []

        def opt(train):
            seen_in_optimizer.extend(train)
            return {}

        def val(test, params):
            for t in test:
                assert t not in seen_in_optimizer, "Data leakage!"
            return []

        data = list(range(1000))
        loop = WalkForwardLoop(optimizer=opt, validator=val)
        w = WalkForwardWindow(
            fold_index=0, train_start=0, train_end=600, test_start=600, test_end=700
        )
        loop.run_fold(data, w)

    def test_fold_result_valid(self):
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        data = self._make_data()
        w = WalkForwardWindow(
            fold_index=0, train_start=0, train_end=600, test_start=600, test_end=700
        )
        result = loop.run_fold(data, w)
        assert result.is_valid
        assert result.error is None

    def test_fold_result_oos_metrics_populated(self):
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        data = self._make_data()
        w = WalkForwardWindow(
            fold_index=0, train_start=0, train_end=600, test_start=600, test_end=700
        )
        result = loop.run_fold(data, w)
        assert result.oos_metrics.n_trades >= 0

    def test_train_metrics_populated_with_train_validator(self):
        loop = WalkForwardLoop(
            optimizer=self._optimizer,
            validator=self._validator,
            train_validator=self._validator,
        )
        data = self._make_data()
        w = WalkForwardWindow(
            fold_index=0, train_start=0, train_end=600, test_start=600, test_end=700
        )
        result = loop.run_fold(data, w)
        assert result.train_metrics.n_trades >= 0

    def test_overfitting_ratio_computed(self):
        loop = WalkForwardLoop(
            optimizer=self._optimizer,
            validator=self._validator,
            train_validator=self._validator,
        )
        data = self._make_data()
        w = WalkForwardWindow(
            fold_index=0, train_start=0, train_end=600, test_start=600, test_end=700
        )
        result = loop.run_fold(data, w)
        # overfitting_ratio peut etre None si train Sharpe = 0
        if result.overfitting_ratio is not None:
            assert isinstance(result.overfitting_ratio, float)

    def test_exception_captured_in_error(self):
        def bad_opt(train):
            raise RuntimeError("optimizer crashed")

        loop = WalkForwardLoop(optimizer=bad_opt, validator=self._validator)
        data = self._make_data()
        w = WalkForwardWindow(
            fold_index=0, train_start=0, train_end=600, test_start=600, test_end=700
        )
        result = loop.run_fold(data, w)
        assert not result.is_valid
        assert "crashed" in result.error

    def test_as_dict_keys(self):
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        data = self._make_data()
        w = WalkForwardWindow(
            fold_index=0, train_start=0, train_end=600, test_start=600, test_end=700
        )
        result = loop.run_fold(data, w)
        d = result.as_dict()
        assert "fold_index" in d
        assert "oos" in d
        assert "train" in d
        assert "overfitting_ratio" in d


# ---------------------------------------------------------------------------
# TestWalkForwardEngine
# ---------------------------------------------------------------------------


class TestWalkForwardEngine:

    def _make_data_with_regime(self, n: int = 1000) -> list[dict]:
        """Data synthetique : chaque sample est un dict avec un regime."""
        rng = random.Random(SEED)
        regimes = ["bull", "bear", "stable"]
        return [
            {"value": rng.gauss(0.2, 1.0), "regime": regimes[i % 3]} for i in range(n)
        ]

    def _optimizer(self, train: list) -> dict:
        values = [d["value"] for d in train]
        return {"threshold": sum(values) / len(values)}

    def _validator(self, test: list, params: dict) -> list[TradeResult]:
        thr = params["threshold"]
        return [
            TradeResult(
                timestamp_ms=i * 1000,
                pnl_pct=d["value"] * 0.05,
                regime=d["regime"],
            )
            for i, d in enumerate(test)
            if abs(d["value"]) > abs(thr)
        ]

    def test_run_returns_walk_forward_result(self):
        from walk_forward.engine import WalkForwardResult

        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        engine = WalkForwardEngine(splitter=sp, loop=loop)
        data = self._make_data_with_regime()
        result = engine.run(data)
        assert isinstance(result, WalkForwardResult)

    def test_correct_n_folds(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        engine = WalkForwardEngine(splitter=sp, loop=loop)
        data = self._make_data_with_regime()
        result = engine.run(data)
        assert result.n_folds == sp.n_folds

    def test_aggregate_covers_all_oos_trades(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        engine = WalkForwardEngine(splitter=sp, loop=loop)
        data = self._make_data_with_regime()
        result = engine.run(data)
        total = sum(f.oos_metrics.n_trades for f in result.folds if f.is_valid)
        assert result.aggregate_metrics.n_trades == total

    def test_no_leakage_in_folds(self):
        """Verifier qu'aucun fold n'a train_end > test_start."""
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        engine = WalkForwardEngine(splitter=sp, loop=loop)
        data = self._make_data_with_regime()
        result = engine.run(data)
        for f in result.folds:
            assert f.fold.train_end <= f.fold.test_start

    def test_stability_computed(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        engine = WalkForwardEngine(splitter=sp, loop=loop)
        data = self._make_data_with_regime()
        result = engine.run(data)
        assert 0.0 <= result.stability.stability_score <= 1.0

    def test_is_robust_field_present(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        engine = WalkForwardEngine(splitter=sp, loop=loop)
        data = self._make_data_with_regime()
        result = engine.run(data)
        assert isinstance(result.is_robust, bool)

    def test_empty_data_raises_or_returns_empty(self):
        # n_samples=0 leve une ValueError dans WindowSplitter
        with pytest.raises(ValueError):
            WindowSplitter(n_samples=0, train_size=600, test_size=100)

    def test_as_dict_keys(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        engine = WalkForwardEngine(splitter=sp, loop=loop)
        data = self._make_data_with_regime()
        result = engine.run(data)
        d = result.as_dict()
        assert "n_folds" in d
        assert "aggregate" in d
        assert "stability" in d
        assert "is_robust" in d

    def test_degradation_events_collected(self):
        sp = WindowSplitter(n_samples=1000, train_size=600, test_size=100, step=100)
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        engine = WalkForwardEngine(splitter=sp, loop=loop)
        data = self._make_data_with_regime()
        result = engine.run(data)
        # peut etre vide si aucun probleme — juste verifier que c'est une liste
        assert isinstance(result.degradation_events, list)

    def test_anchored_engine_run(self):
        sp = WindowSplitter(
            n_samples=1000, train_size=400, test_size=100, step=100, anchored=True
        )
        loop = WalkForwardLoop(optimizer=self._optimizer, validator=self._validator)
        engine = WalkForwardEngine(splitter=sp, loop=loop)
        data = self._make_data_with_regime()
        result = engine.run(data)
        assert result.n_folds >= 1
        # Premier fold toujours anchored a 0
        assert result.folds[0].fold.train_start == 0
