"""
Tests de contrat C5 — Significance Gate.

Règles vérifiées individuellement et en combinaison :
  G1 : len(trades) < 30  → False
  G2 : p_value >= 0.05   → False
  G3 : ci_low <= 0       → False
  G1∧G2∧G3 satisfaites  → True

Intégration C1→C2→C5 vérifiée.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.analytics.bootstrap_stability import BootstrapResult, run_bootstrap_stability
from src.analytics.is_oos_splitter import split_is_oos
from src.analytics.significance_gate import MIN_TRADES, is_alpha_significant
from src.domain.trade_event import TradeEvent

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ── Builders ────────────────────────────────────────────────────────────────


def _result(
    *, mean=10.0, ci_low=1.0, ci_high=15.0, p_value=0.0, n=30
) -> BootstrapResult:
    return BootstrapResult(
        mean_expectancy=mean,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value=p_value,
        n=n,
    )


def _make_trade(i: int, net_pnl: float = 10.0) -> TradeEvent:
    opened = _EPOCH + timedelta(hours=i)
    closed = opened + timedelta(minutes=30)
    return TradeEvent(
        trade_id=f"T{i:04d}",
        run_id="run-c5",
        strategy_id="sma",
        symbol="BTC/USDT",
        side="buy",
        entry_price=100.0,
        exit_price=110.0,
        quantity=1.0,
        execution_mode="backtest",
        gross_pnl_usd=net_pnl + 0.5,
        fees_usd=0.5,
        slippage_usd=0.0,
        opened_at=opened,
        closed_at=closed,
    )


def _trades(n: int, net_pnl: float = 10.0) -> list[TradeEvent]:
    return [_make_trade(i, net_pnl) for i in range(n)]


# ── G1 : volume minimum ──────────────────────────────────────────────────────


class TestG1Volume:
    def test_n_29_rejected(self):
        assert is_alpha_significant(_result(), _trades(29)) is False

    def test_n_0_rejected(self):
        assert is_alpha_significant(_result(), []) is False

    def test_n_1_rejected(self):
        assert is_alpha_significant(_result(), _trades(1)) is False

    def test_n_30_passes_g1(self):
        # G1 passe — G2 et G3 encore satisfaites par _result()
        assert is_alpha_significant(_result(), _trades(MIN_TRADES)) is True

    def test_n_100_passes_g1(self):
        assert is_alpha_significant(_result(), _trades(100)) is True

    @pytest.mark.parametrize("n", range(0, MIN_TRADES))
    def test_all_below_threshold_rejected(self, n):
        assert is_alpha_significant(_result(), _trades(n)) is False


# ── G2 : p_value < 0.05 ─────────────────────────────────────────────────────


class TestG2PValue:
    def test_p_value_0_05_rejected(self):
        assert is_alpha_significant(_result(p_value=0.05), _trades(30)) is False

    def test_p_value_0_10_rejected(self):
        assert is_alpha_significant(_result(p_value=0.10), _trades(30)) is False

    def test_p_value_1_0_rejected(self):
        assert is_alpha_significant(_result(p_value=1.0), _trades(30)) is False

    def test_p_value_0_04_passes(self):
        assert is_alpha_significant(_result(p_value=0.04), _trades(30)) is True

    def test_p_value_0_0_passes(self):
        assert is_alpha_significant(_result(p_value=0.0), _trades(30)) is True

    @pytest.mark.parametrize("p", [0.05, 0.06, 0.10, 0.50, 0.99, 1.0])
    def test_p_gte_threshold_always_rejected(self, p):
        assert is_alpha_significant(_result(p_value=p), _trades(30)) is False


# ── G3 : ci_low > 0 ─────────────────────────────────────────────────────────


class TestG3CILow:
    def test_ci_low_zero_rejected(self):
        assert is_alpha_significant(_result(ci_low=0.0), _trades(30)) is False

    def test_ci_low_negative_rejected(self):
        assert is_alpha_significant(_result(ci_low=-1.0), _trades(30)) is False

    def test_ci_low_very_negative_rejected(self):
        assert is_alpha_significant(_result(ci_low=-100.0), _trades(30)) is False

    def test_ci_low_0_001_passes(self):
        assert is_alpha_significant(_result(ci_low=0.001), _trades(30)) is True

    def test_ci_low_positive_passes(self):
        assert is_alpha_significant(_result(ci_low=5.0), _trades(30)) is True

    @pytest.mark.parametrize("ci_low", [0.0, -0.01, -1.0, -100.0])
    def test_ci_low_lte_zero_always_rejected(self, ci_low):
        assert is_alpha_significant(_result(ci_low=ci_low), _trades(30)) is False


# ── Conditions combinées ─────────────────────────────────────────────────────


class TestCombinations:
    def test_all_three_satisfied_returns_true(self):
        r = _result(p_value=0.0, ci_low=5.0)
        assert is_alpha_significant(r, _trades(30)) is True

    def test_g1_fail_overrides(self):
        r = _result(p_value=0.0, ci_low=5.0)
        assert is_alpha_significant(r, _trades(29)) is False

    def test_g2_fail_overrides(self):
        r = _result(p_value=0.10, ci_low=5.0)
        assert is_alpha_significant(r, _trades(30)) is False

    def test_g3_fail_overrides(self):
        r = _result(p_value=0.0, ci_low=-1.0)
        assert is_alpha_significant(r, _trades(30)) is False

    def test_g1_g2_fail(self):
        r = _result(p_value=0.10, ci_low=5.0)
        assert is_alpha_significant(r, _trades(10)) is False

    def test_g1_g3_fail(self):
        r = _result(p_value=0.0, ci_low=-1.0)
        assert is_alpha_significant(r, _trades(10)) is False

    def test_g2_g3_fail(self):
        r = _result(p_value=0.10, ci_low=-1.0)
        assert is_alpha_significant(r, _trades(30)) is False

    def test_all_three_fail(self):
        r = _result(p_value=1.0, ci_low=-10.0)
        assert is_alpha_significant(r, _trades(5)) is False

    def test_returns_bool_not_truthy(self):
        r = _result()
        result = is_alpha_significant(r, _trades(30))
        assert result is True or result is False
        assert type(result) is bool


# ── Intégration C1→C2→C5 ────────────────────────────────────────────────────


class TestC1C2C5Integration:
    def test_pure_winning_chain_significant(self):
        trades = _trades(50, net_pnl=50.0)
        split = split_is_oos(trades)
        bootstrap = run_bootstrap_stability(split.is_trades, n_resamples=200, seed=42)
        result = is_alpha_significant(bootstrap, split.is_trades)
        assert result is True

    def test_pure_losing_chain_not_significant(self):
        trades = _trades(50, net_pnl=-50.0)
        split = split_is_oos(trades)
        bootstrap = run_bootstrap_stability(split.is_trades, n_resamples=200, seed=42)
        result = is_alpha_significant(bootstrap, split.is_trades)
        assert result is False

    def test_insufficient_is_trades_not_significant(self):
        # IS avec N=18 (60% de 30) → insuffisant pour G1
        trades = _trades(30, net_pnl=50.0)  # IS = 18 trades
        split = split_is_oos(trades)
        bootstrap = run_bootstrap_stability(split.is_trades, n_resamples=200, seed=42)
        result = is_alpha_significant(bootstrap, split.is_trades)
        # 18 IS trades < 30 → G1 rejette
        assert result is False

    def test_chain_output_is_bool(self):
        trades = _trades(60, net_pnl=10.0)
        split = split_is_oos(trades)
        bootstrap = run_bootstrap_stability(split.is_trades, seed=42)
        result = is_alpha_significant(bootstrap, split.is_trades)
        assert type(result) is bool
