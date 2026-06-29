"""tests/scripts/test_advanced_stats — bootstrap CI, Monte-Carlo, rolling PF, drift."""

from __future__ import annotations

import math

import pytest

from analysis.base import (
    bootstrap_confidence_interval,
    concept_drift_detected,
    monte_carlo_max_drawdown,
    profit_factor,
    rolling_profit_factor,
)

# ── bootstrap_confidence_interval ─────────────────────────────────────────────


def test_bootstrap_requires_min_10() -> None:
    assert bootstrap_confidence_interval([1.0, -1.0]) is None


def test_bootstrap_returns_tuple() -> None:
    pnls = [1.0, -0.5, 2.0, -1.0, 0.5] * 5  # 25 trades
    result = bootstrap_confidence_interval(pnls, n_bootstrap=200)
    assert result is not None
    lo, hi = result
    assert lo <= hi


def test_bootstrap_ci_contains_mean() -> None:
    import random

    random.seed(42)
    pnls = [1.0] * 20  # expectancy = 1.0 exactement
    lo, hi = bootstrap_confidence_interval(pnls, n_bootstrap=500)
    assert lo <= 1.0 <= hi


def test_bootstrap_ci_bounds_valid() -> None:
    pnls = [2.0, -1.0, 3.0, -0.5, 1.5, -2.0] * 5
    result = bootstrap_confidence_interval(pnls, n_bootstrap=300)
    assert result is not None
    lo, hi = result
    assert math.isfinite(lo) and math.isfinite(hi)


def test_bootstrap_custom_metric() -> None:
    pnls = [5.0, -2.0] * 15
    result = bootstrap_confidence_interval(
        pnls, metric_fn=profit_factor, n_bootstrap=300
    )
    assert result is not None
    lo, hi = result
    assert lo > 0  # PF doit être positif


# ── monte_carlo_max_drawdown ──────────────────────────────────────────────────


def test_mc_requires_min_10() -> None:
    assert monte_carlo_max_drawdown([1.0, -1.0]) is None


def test_mc_returns_dict() -> None:
    pnls = [2.0, -1.0, 3.0, -2.0, 1.0] * 5
    result = monte_carlo_max_drawdown(pnls, n_sim=100)
    assert result is not None
    assert "mean_dd" in result
    assert "p95_dd" in result
    assert "p99_dd" in result
    assert "observed_dd" in result


def test_mc_p99_gte_p95() -> None:
    pnls = [1.0, -3.0, 2.0, -1.0, 4.0] * 5
    result = monte_carlo_max_drawdown(pnls, n_sim=200)
    assert result["p99_dd"] >= result["p95_dd"]


def test_mc_all_positive_no_drawdown() -> None:
    pnls = [1.0] * 20
    result = monte_carlo_max_drawdown(pnls, n_sim=100)
    assert result is not None
    assert result["observed_dd"] == 0.0
    assert result["mean_dd"] == 0.0


def test_mc_n_sim_respected() -> None:
    pnls = [1.0, -0.5] * 10
    result = monte_carlo_max_drawdown(pnls, n_sim=42)
    assert result["n_sim"] == 42


# ── rolling_profit_factor ─────────────────────────────────────────────────────


def test_rolling_pf_length() -> None:
    pnls = [1.0, -0.5, 2.0, -1.0, 3.0]
    result = rolling_profit_factor(pnls, window=3)
    assert len(result) == 5


def test_rolling_pf_first_nones() -> None:
    pnls = [1.0, -1.0, 2.0, -0.5, 1.5]
    result = rolling_profit_factor(pnls, window=3)
    assert result[0] is None
    assert result[1] is None
    assert result[2] is not None


def test_rolling_pf_values() -> None:
    # window=2: [1, -1], [-1, 2], [2, -0.5]
    pnls = [1.0, -1.0, 2.0, -0.5]
    result = rolling_profit_factor(pnls, window=2)
    assert result[0] is None
    assert result[1] == pytest.approx(1.0)  # 1/1
    assert result[2] == pytest.approx(2.0)  # 2/1
    assert result[3] == pytest.approx(2.0 / 0.5)  # 2/0.5


def test_rolling_pf_full_window_equals_pf() -> None:
    pnls = [5.0, -2.0, 3.0, -1.0, 4.0]
    result = rolling_profit_factor(pnls, window=len(pnls))
    expected = profit_factor(pnls)
    assert result[-1] == pytest.approx(expected)


# ── concept_drift_detected ────────────────────────────────────────────────────


def test_drift_requires_min_n() -> None:
    result = concept_drift_detected([1.0, -1.0], min_n=40)
    assert result["drift"] is None
    assert "N=" in result["reason"]


def test_drift_not_detected_stable() -> None:
    # Même PF en récent et historique
    pnls = [2.0, -1.0] * 30  # stable : PF = 2.0 partout
    result = concept_drift_detected(pnls, window=10, min_n=40)
    assert result["drift"] is False


def test_drift_detected_degradation() -> None:
    # Bons résultats historiques, puis pertes récentes
    pnls = [5.0, -1.0] * 25 + [-3.0] * 15  # dérive vers les pertes
    result = concept_drift_detected(pnls, window=15, min_n=40, threshold_ratio=0.7)
    assert result["drift"] is True


def test_drift_ratio_valid() -> None:
    pnls = [3.0, -1.0] * 30
    result = concept_drift_detected(pnls, window=10, min_n=40)
    assert "ratio" in result
    assert isinstance(result["ratio"], float)


def test_drift_reason_present() -> None:
    pnls = [2.0, -1.0] * 30
    result = concept_drift_detected(pnls, window=10, min_n=40)
    assert isinstance(result["reason"], str)
    assert len(result["reason"]) > 0


def test_drift_pf_values_returned() -> None:
    pnls = [2.0, -1.0] * 30
    result = concept_drift_detected(pnls, window=10, min_n=40)
    assert result["pf_historical"] is not None
    assert result["pf_recent"] is not None
