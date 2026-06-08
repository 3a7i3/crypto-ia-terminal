"""
Tests de contrat C2 — Bootstrap Stability.

Invariants vérifiés :
  C2-I1 : result.n == len(trades)
  C2-I2 : 0.0 ≤ p_value ≤ 1.0
  C2-I3 : ci_low ≤ ci_high
  C2-I4 : empty input → résultat safe (n=0, p_value=1.0)
  C2-I5 : résultat reproductible avec seed fixe
  C2-I6 : intégration C1→C2 — consomme ISOOSSplit.is_trades
  C2-I7 : alpha positif → ci_low tend vers positif
  C2-I8 : alpha négatif → p_value tend vers 1.0
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.analytics.bootstrap_stability import BootstrapResult, run_bootstrap_stability
from src.analytics.is_oos_splitter import split_is_oos
from src.domain.trade_event import MarketRegime, TradeEvent

_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_trade(i: int, net_pnl: float) -> TradeEvent:
    opened = _EPOCH + timedelta(hours=i)
    closed = opened + timedelta(minutes=30)
    fees = 0.5
    return TradeEvent(
        trade_id=f"T{i:04d}",
        run_id="run-c2",
        strategy_id="sma",
        symbol="BTC/USDT",
        side="buy",
        entry_price=100.0,
        exit_price=110.0,
        quantity=1.0,
        execution_mode="backtest",
        gross_pnl_usd=net_pnl + fees,
        fees_usd=fees,
        slippage_usd=0.0,
        opened_at=opened,
        closed_at=closed,
    )


def _winning_trades(n: int, pnl: float = 10.0) -> list[TradeEvent]:
    return [_make_trade(i, pnl) for i in range(n)]


def _losing_trades(n: int, pnl: float = -10.0) -> list[TradeEvent]:
    return [_make_trade(i, pnl) for i in range(n)]


def _mixed_trades(n_win: int, n_lose: int) -> list[TradeEvent]:
    wins = _winning_trades(n_win, 10.0)
    loses = [_make_trade(n_win + i, -5.0) for i in range(n_lose)]
    return wins + loses


# ── C2-I1 : result.n == len(trades) ────────────────────────────────────────


class TestCountInvariant:
    @pytest.mark.parametrize("n", [1, 5, 10, 18, 30])
    def test_n_equals_input_length(self, n):
        r = run_bootstrap_stability(_winning_trades(n), seed=42)
        assert r.n == n

    def test_n_zero_for_empty(self):
        r = run_bootstrap_stability([], seed=42)
        assert r.n == 0


# ── C2-I2 : 0.0 ≤ p_value ≤ 1.0 ────────────────────────────────────────────


class TestPValueBounds:
    @pytest.mark.parametrize("n", [1, 5, 10, 30])
    def test_p_value_in_unit_interval_winning(self, n):
        r = run_bootstrap_stability(_winning_trades(n), seed=42)
        assert 0.0 <= r.p_value <= 1.0

    @pytest.mark.parametrize("n", [1, 5, 10, 30])
    def test_p_value_in_unit_interval_losing(self, n):
        r = run_bootstrap_stability(_losing_trades(n), seed=42)
        assert 0.0 <= r.p_value <= 1.0

    def test_p_value_one_for_empty(self):
        r = run_bootstrap_stability([])
        assert r.p_value == pytest.approx(1.0)


# ── C2-I3 : ci_low ≤ ci_high ────────────────────────────────────────────────


class TestCIOrdering:
    @pytest.mark.parametrize("n", [2, 5, 10, 30])
    def test_ci_low_lte_ci_high_winning(self, n):
        r = run_bootstrap_stability(_winning_trades(n), seed=42)
        assert r.ci_low <= r.ci_high

    @pytest.mark.parametrize("n", [2, 5, 10, 30])
    def test_ci_low_lte_ci_high_losing(self, n):
        r = run_bootstrap_stability(_losing_trades(n), seed=42)
        assert r.ci_low <= r.ci_high

    @pytest.mark.parametrize("n", [2, 5, 10, 30])
    def test_ci_low_lte_ci_high_mixed(self, n):
        r = run_bootstrap_stability(_mixed_trades(n, n), seed=42)
        assert r.ci_low <= r.ci_high


# ── C2-I4 : empty input → résultat safe ─────────────────────────────────────


class TestEmptySafety:
    def test_empty_returns_bootstrap_result(self):
        r = run_bootstrap_stability([])
        assert isinstance(r, BootstrapResult)

    def test_empty_mean_expectancy_zero(self):
        assert run_bootstrap_stability([]).mean_expectancy == pytest.approx(0.0)

    def test_empty_p_value_one(self):
        assert run_bootstrap_stability([]).p_value == pytest.approx(1.0)

    def test_empty_ci_zero(self):
        r = run_bootstrap_stability([])
        assert r.ci_low == pytest.approx(0.0)
        assert r.ci_high == pytest.approx(0.0)


# ── C2-I5 : reproductibilité avec seed fixe ─────────────────────────────────


class TestReproducibility:
    def test_same_seed_same_result(self):
        trades = _winning_trades(20)
        r1 = run_bootstrap_stability(trades, seed=0)
        r2 = run_bootstrap_stability(trades, seed=0)
        assert r1 == r2

    def test_different_seeds_may_differ(self):
        trades = _mixed_trades(10, 10)
        r1 = run_bootstrap_stability(trades, seed=1)
        r2 = run_bootstrap_stability(trades, seed=99)
        # les CI diffèrent presque certainement (pas une garantie stricte mais haute probabilité)
        assert not (r1.ci_low == r2.ci_low and r1.ci_high == r2.ci_high)

    def test_no_seed_still_returns_valid_result(self):
        r = run_bootstrap_stability(_winning_trades(10))
        assert isinstance(r, BootstrapResult)
        assert 0.0 <= r.p_value <= 1.0


# ── C2-I6 : intégration C1→C2 ───────────────────────────────────────────────


class TestC1C2Integration:
    def test_consumes_is_trades_from_split(self):
        trades = _winning_trades(30)
        split = split_is_oos(trades)
        r = run_bootstrap_stability(split.is_trades, seed=42)
        assert r.n == split.metadata.n_is

    def test_is_only_never_uses_oos(self):
        winning = _winning_trades(20)
        losing = _losing_trades(10)
        all_trades = winning + losing

        split = split_is_oos(all_trades)
        r_is = run_bootstrap_stability(split.is_trades, seed=42)
        r_all = run_bootstrap_stability(all_trades, seed=42)

        # IS subset → résultat différent de l'ensemble complet
        assert r_is.n != r_all.n

    def test_oos_not_contaminated(self):
        trades = _winning_trades(20)
        split = split_is_oos(trades)
        r = run_bootstrap_stability(split.is_trades, seed=42)
        # OOS n'intervient pas dans le calcul
        assert r.n == split.metadata.n_is
        assert r.n < len(trades)


# ── C2-I7 : alpha positif → ci_low tend vers positif ───────────────────────


class TestAlphaSignal:
    def test_pure_winning_ci_low_positive(self):
        # tous les trades gagnants → bootstrap entièrement positif
        r = run_bootstrap_stability(
            _winning_trades(30, pnl=50.0), n_resamples=200, seed=42
        )
        assert r.ci_low > 0.0

    def test_pure_winning_p_value_near_zero(self):
        r = run_bootstrap_stability(
            _winning_trades(30, pnl=50.0), n_resamples=200, seed=42
        )
        assert r.p_value == pytest.approx(0.0)

    def test_pure_winning_mean_expectancy_positive(self):
        r = run_bootstrap_stability(_winning_trades(20, pnl=10.0), seed=42)
        assert r.mean_expectancy == pytest.approx(10.0)


# ── C2-I8 : alpha négatif → p_value tend vers 1.0 ───────────────────────────


class TestNegativeAlpha:
    def test_pure_losing_p_value_one(self):
        r = run_bootstrap_stability(
            _losing_trades(30, pnl=-50.0), n_resamples=200, seed=42
        )
        assert r.p_value == pytest.approx(1.0)

    def test_pure_losing_ci_high_negative(self):
        r = run_bootstrap_stability(
            _losing_trades(30, pnl=-50.0), n_resamples=200, seed=42
        )
        assert r.ci_high < 0.0

    def test_pure_losing_mean_expectancy_negative(self):
        r = run_bootstrap_stability(_losing_trades(20, pnl=-10.0), seed=42)
        assert r.mean_expectancy == pytest.approx(-10.0)


# ── Paramètres ──────────────────────────────────────────────────────────────


class TestParameters:
    @pytest.mark.parametrize("n_resamples", [10, 30, 100, 500])
    def test_n_resamples_respected(self, n_resamples):
        # Le résultat est valide quelle que soit la valeur
        r = run_bootstrap_stability(
            _winning_trades(15), n_resamples=n_resamples, seed=42
        )
        assert isinstance(r, BootstrapResult)
        assert 0.0 <= r.p_value <= 1.0

    def test_single_trade(self):
        r = run_bootstrap_stability(_winning_trades(1), seed=42)
        assert r.n == 1
        assert r.mean_expectancy == pytest.approx(10.0)
        assert r.p_value == pytest.approx(0.0)
