"""
Tests quantitatifs pour evolution_core.py et feature_cache.py.
Couvre les fonctions non testées : evolve, backtest, compute_rsi,
compute_drawdown, compute_sharpe, register_feature.
"""

import numpy as np
import pytest

from evolution_core import (Genome, backtest, compute_drawdown, compute_rsi,
                            compute_sharpe, evaluate_fitness, evolve,
                            generate_crash_market, generate_range_market,
                            generate_trend_market)
from quant_hedge_ai.strategy_lab.feature_cache import (clear_cache,
                                                       compute_feature,
                                                       list_features,
                                                       register_feature)

# ---------------------------------------------------------------------------
# evolve()
# ---------------------------------------------------------------------------


class TestEvolve:
    def test_returns_same_size_population(self):
        pop = [Genome() for _ in range(10)]
        new_pop = evolve(pop)
        assert len(new_pop) == 10

    def test_returns_list_of_genomes(self):
        pop = [Genome() for _ in range(6)]
        new_pop = evolve(pop)
        assert all(isinstance(g, Genome) for g in new_pop)

    def test_fitness_assigned(self):
        pop = [Genome() for _ in range(6)]
        new_pop = evolve(pop)
        assert all(isinstance(g.fitness, float) for g in new_pop)

    def test_new_individuals_added(self):
        pop = [Genome() for _ in range(8)]
        original_ids = {g.id for g in pop}
        new_pop = evolve(pop, elite_ratio=0.25)
        new_ids = {g.id for g in new_pop}
        # Des enfants (nouveaux IDs) doivent avoir été créés
        assert len(new_ids - original_ids) > 0

    def test_stagnation_doubles_mutation(self):
        pop = [Genome() for _ in range(8)]
        # Simule un historique stagnant
        fitness_history = [1.0] * 12
        new_pop = evolve(pop, stagnation_patience=10, fitness_history=fitness_history)
        assert len(new_pop) == 8


# ---------------------------------------------------------------------------
# backtest()
# ---------------------------------------------------------------------------


class TestBacktest:
    def test_returns_list(self):
        g = Genome()
        prices = generate_trend_market(200)
        result = backtest(g, prices)
        assert isinstance(result, list)

    def test_starts_at_one(self):
        g = Genome()
        prices = generate_trend_market(200)
        result = backtest(g, prices)
        assert result[0] == pytest.approx(1.0)

    def test_capital_positive(self):
        g = Genome()
        prices = generate_range_market(300)
        result = backtest(g, prices)
        assert all(v > 0 for v in result)

    def test_crash_reduces_equity(self):
        g = Genome(
            {
                "entry.type": "trend",
                "entry.rsi_period": 14,
                "entry.rsi_buy": 50,
                "ma_short": 5,
                "ma_long": 20,
                "ma_signal": "cross_over",
                "exit.tp": 2.0,
                "exit.sl": 1.0,
                "risk.risk_per_trade": 0.01,
            }
        )
        prices = generate_crash_market(500)
        result = backtest(g, prices)
        assert result[-1] < result[0] * 5


# ---------------------------------------------------------------------------
# compute_rsi()
# ---------------------------------------------------------------------------


class TestComputeRSI:
    def test_output_range(self):
        prices = generate_trend_market(200)
        rsi = compute_rsi(prices, period=14)
        assert np.all(rsi >= 0) and np.all(rsi <= 100)

    def test_length(self):
        prices = generate_range_market(200)
        rsi = compute_rsi(prices, period=14)
        assert len(rsi) == len(prices) - 14

    def test_uptrend_high_rsi(self):
        prices = np.linspace(100, 200, 100)
        rsi = compute_rsi(prices, period=14)
        assert np.mean(rsi) > 60


# ---------------------------------------------------------------------------
# compute_drawdown() / compute_sharpe()
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_drawdown_zero_for_monotone_equity(self):
        equity = [1.0, 1.1, 1.2, 1.3, 1.4]
        dd = compute_drawdown(equity)
        assert dd == pytest.approx(0.0, abs=1e-9)

    def test_drawdown_positive(self):
        equity = [1.0, 1.2, 0.8, 0.9]
        dd = compute_drawdown(equity)
        assert dd > 0

    def test_drawdown_bounded(self):
        equity = [1.0, 0.5, 0.3]
        dd = compute_drawdown(equity)
        assert 0 <= dd <= 1

    def test_sharpe_flat_returns_zero(self):
        equity = [1.0, 1.0, 1.0, 1.0]
        sharpe = compute_sharpe(equity)
        assert sharpe == 0.0

    def test_sharpe_positive_for_growth(self):
        equity = np.linspace(1.0, 2.0, 50).tolist()
        sharpe = compute_sharpe(equity)
        assert sharpe > 0


# ---------------------------------------------------------------------------
# register_feature() + list_features()
# ---------------------------------------------------------------------------


class TestFeatureCacheExtensions:
    def teardown_method(self):
        clear_cache()

    def test_register_and_call_custom_feature(self):
        register_feature("custom_sum", lambda values: sum(values))
        result = compute_feature("custom_sum", (1.0, 2.0, 3.0))
        assert result == pytest.approx(6.0)

    def test_register_non_callable_raises(self):
        with pytest.raises(TypeError):
            register_feature("bad", 42)

    def test_list_features_contains_builtins(self):
        features = list_features()
        assert "mean" in features
        assert "rolling_volatility" in features
        assert "correlation" in features

    def test_register_overrides_existing(self):
        original = compute_feature("mean", (2.0, 4.0))
        register_feature("mean", lambda values: -1.0)
        overridden = compute_feature("mean", (2.0, 4.0))
        assert overridden == pytest.approx(-1.0)
        # Restaure mean original
        from quant_hedge_ai.strategy_lab.feature_cache import _mean

        register_feature("mean", _mean)

    def test_register_clears_cache(self):
        compute_feature("mean", (10.0, 20.0))
        info_before = compute_feature.cache_info()
        register_feature("mean_v2", lambda values: 0.0)
        info_after = compute_feature.cache_info()
        assert info_after.currsize < info_before.currsize or info_after.currsize == 0
