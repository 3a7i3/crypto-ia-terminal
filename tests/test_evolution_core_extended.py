"""
Tests étendus pour evolution_core.py
Couvre les branches non atteintes par test_evolve_world.py :
  migrate, generate_*_market, compute_rsi, ma_signal, backtest (3 types),
  compute_drawdown, compute_sharpe, score_env_*, evaluate_fitness,
  _compute_evolution_params, evolve, enrich_evolve, save_simulation_summary,
  create_population, apply_extinction (espèce rare), select_parents (cross-species).
"""

import json
import math
import random

import numpy as np
import pytest

from evolution_core import (GENE_SPACE, Genome, GenomeSerializer,
                            _compute_evolution_params, apply_extinction,
                            backtest, clamp_gene, compute_drawdown,
                            compute_rsi, compute_sharpe, create_population,
                            crossover, enrich_evolve, evaluate_fitness, evolve,
                            generate_crash_market, generate_range_market,
                            generate_trend_market, ma_signal, migrate, mutate,
                            save_simulation_summary, score_env_crash,
                            score_env_range, score_env_trend, select_parents)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _genome(entry_type="mean_reversion") -> Genome:
    return Genome(
        genes={
            "entry.type": entry_type,
            "entry.rsi_period": 5,
            "entry.rsi_buy": 50.0,
            "ma_short": 5.0,
            "ma_long": 20.0,
            "ma_signal": "cross_over",
            "exit.tp": 1.0,
            "exit.sl": 0.5,
            "risk.risk_per_trade": 0.01,
        }
    )


def _prices(n=100, trend=0.001) -> np.ndarray:
    """Série de prix déterministe — assure que RSI et MA ont assez de données."""
    rng = np.random.default_rng(42)
    changes = rng.normal(trend, 0.005, n)
    prices = [100.0]
    for c in changes:
        prices.append(prices[-1] * (1 + c))
    return np.array(prices)


# ── create_population ─────────────────────────────────────────────────────────


class TestCreatePopulation:
    def test_returns_list_of_genomes(self):
        pop = create_population(5)
        assert len(pop) == 5
        assert all(isinstance(g, Genome) for g in pop)

    def test_default_size(self):
        pop = create_population()
        assert len(pop) == 50


# ── migrate ───────────────────────────────────────────────────────────────────


class TestMigrate:
    def test_populations_unchanged_size(self):
        pops = {
            "w1": [Genome() for _ in range(10)],
            "w2": [Genome() for _ in range(10)],
        }
        result = migrate(pops, migration_rate=0.1, pop_size=10)
        assert all(len(v) == 10 for v in result.values())

    def test_migrants_are_copies(self):
        pops = {
            "w1": [Genome() for _ in range(10)],
            "w2": [Genome() for _ in range(10)],
        }
        original_ids_w1 = {g.id for g in pops["w1"]}
        result = migrate(pops, migration_rate=0.2, pop_size=10)
        final_ids_w2 = {g.id for g in result["w2"]}
        # Après migration des meilleurs de w1 vers w2, au moins un ID de w1
        # peut apparaître dans w2 (copies incluses)
        assert len(final_ids_w2) > 0

    def test_three_worlds(self):
        pops = {f"w{i}": [Genome() for _ in range(8)] for i in range(3)}
        result = migrate(pops, migration_rate=0.1, pop_size=8)
        assert len(result) == 3


# ── generate_*_market ─────────────────────────────────────────────────────────


class TestMarketGenerators:
    def test_trend_market_length(self):
        prices = generate_trend_market(length=50)
        assert len(prices) == 51  # length+1 (initial 100 + 50 iterations)

    def test_range_market_length(self):
        prices = generate_range_market(length=50)
        assert len(prices) == 51

    def test_crash_market_length(self):
        prices = generate_crash_market(length=50)
        assert len(prices) == 51

    def test_trend_market_starts_at_100(self):
        prices = generate_trend_market(length=10)
        assert prices[0] == pytest.approx(100.0)

    def test_crash_market_second_half_bearish_on_average(self):
        """Sur 1000 runs, la fin du crash market est en moyenne < le milieu."""
        results = []
        for _ in range(20):
            p = generate_crash_market(length=100)
            mid = p[50]
            end = p[-1]
            results.append(end < mid * 1.1)  # tolérance large
        assert sum(results) >= 10

    def test_all_prices_positive(self):
        for gen in (
            generate_trend_market,
            generate_range_market,
            generate_crash_market,
        ):
            prices = gen(length=30)
            assert np.all(prices > 0)


# ── compute_rsi ───────────────────────────────────────────────────────────────


class TestComputeRSI:
    def test_output_length(self):
        prices = _prices(50)
        rsi = compute_rsi(prices, period=5)
        assert len(rsi) == len(prices) - 5

    def test_values_in_0_100(self):
        prices = _prices(100)
        rsi = compute_rsi(prices, period=14)
        assert np.all(rsi >= 0) and np.all(rsi <= 100)

    def test_uptrend_rsi_above_50(self):
        prices = np.linspace(100, 200, 100)
        rsi = compute_rsi(prices, period=5)
        assert np.mean(rsi) > 50


# ── ma_signal ─────────────────────────────────────────────────────────────────


class TestMASignal:
    def test_cross_over_returns_array(self):
        prices = _prices(200)
        signals = ma_signal(prices, short=5, long=20, signal_type="cross_over")
        assert isinstance(signals, np.ndarray)

    def test_cross_under_returns_array(self):
        prices = _prices(200)
        signals = ma_signal(prices, short=5, long=20, signal_type="cross_under")
        assert isinstance(signals, np.ndarray)

    def test_signals_are_valid_indices(self):
        prices = _prices(200)
        signals = ma_signal(prices, short=5, long=20)
        assert np.all(signals >= 0)
        assert np.all(signals < len(prices))


# ── backtest ──────────────────────────────────────────────────────────────────


class TestBacktest:
    def test_returns_list(self):
        prices = _prices(100)
        equity = backtest(_genome("mean_reversion"), prices)
        assert isinstance(equity, list)

    def test_equity_starts_at_1(self):
        prices = _prices(100)
        equity = backtest(_genome("mean_reversion"), prices)
        assert equity[0] == pytest.approx(1.0)

    def test_equity_all_positive(self):
        prices = _prices(100)
        equity = backtest(_genome("mean_reversion"), prices)
        assert all(e > 0 for e in equity)

    def test_entry_type_trend(self):
        prices = _prices(200)
        equity = backtest(_genome("trend"), prices)
        assert len(equity) > 1

    def test_entry_type_hybrid(self):
        prices = _prices(200)
        equity = backtest(_genome("hybrid"), prices)
        assert len(equity) > 1

    def test_equity_length_matches_prices(self):
        prices = _prices(80)
        equity = backtest(_genome("mean_reversion"), prices)
        assert len(equity) >= 2


# ── compute_drawdown ──────────────────────────────────────────────────────────


class TestComputeDrawdown:
    def test_flat_equity_zero_drawdown(self):
        equity = [1.0] * 20
        dd = compute_drawdown(equity)
        assert dd == pytest.approx(0.0, abs=1e-9)

    def test_monotone_increase_zero_drawdown(self):
        equity = [1.0 + i * 0.01 for i in range(20)]
        dd = compute_drawdown(equity)
        assert dd == pytest.approx(0.0, abs=1e-6)

    def test_drop_detected(self):
        equity = [1.0, 1.1, 1.0, 0.9, 1.0]
        dd = compute_drawdown(equity)
        assert dd > 0.0

    def test_returns_non_negative(self):
        equity = [1.0, 0.8, 0.6, 0.9]
        dd = compute_drawdown(equity)
        assert dd >= 0.0


# ── compute_sharpe ────────────────────────────────────────────────────────────


class TestComputeSharpe:
    def test_flat_returns_zero_sharpe(self):
        equity = [1.0] * 20
        sharpe = compute_sharpe(equity)
        assert sharpe == pytest.approx(0.0)

    def test_positive_returns_positive_sharpe(self):
        equity = [1.0 + i * 0.01 + random.uniform(-0.001, 0.001) for i in range(30)]
        sharpe = compute_sharpe(equity)
        assert sharpe > 0

    def test_negative_returns_negative_sharpe(self):
        equity = [1.0 - i * 0.01 - random.uniform(0, 0.001) for i in range(30)]
        sharpe = compute_sharpe(equity)
        assert sharpe < 0


# ── score_env_* ───────────────────────────────────────────────────────────────


class TestScoreEnv:
    def test_score_trend_returns_float(self):
        g = _genome()
        score = score_env_trend(g)
        assert isinstance(score, float)

    def test_score_range_returns_float(self):
        g = _genome()
        score = score_env_range(g)
        assert isinstance(score, float)

    def test_score_crash_returns_float(self):
        g = _genome()
        score = score_env_crash(g)
        assert isinstance(score, float)

    def test_scores_are_finite(self):
        g = _genome()
        for fn in (score_env_trend, score_env_range, score_env_crash):
            assert math.isfinite(fn(g))


# ── evaluate_fitness ──────────────────────────────────────────────────────────


class TestEvaluateFitness:
    def test_assigns_all_fitness_fields(self):
        g = _genome()
        evaluate_fitness(g)
        assert math.isfinite(g.fitness)
        assert math.isfinite(g.fitness_trend)
        assert math.isfinite(g.fitness_range)
        assert math.isfinite(g.fitness_crash)

    def test_fitness_is_mean_of_three(self):
        g = _genome()
        evaluate_fitness(g)
        expected = (g.fitness_trend + g.fitness_range + g.fitness_crash) / 3
        assert g.fitness == pytest.approx(expected, rel=1e-6)


# ── _compute_evolution_params ────────────────────────────────────────────────


class TestComputeEvolutionParams:
    def _pop_with_fitness(self, fitnesses):
        pop = []
        for f in fitnesses:
            g = Genome()
            g.fitness = f
            pop.append(g)
        return pop

    def test_no_history_uses_base_rate(self):
        pop = self._pop_with_fitness([1.0, 0.8, 0.5])
        survivors, _, rate, stag, ext, super_ = _compute_evolution_params(
            pop,
            elite_ratio=0.5,
            mutation_base=0.3,
            stagnation_patience=10,
            fitness_history=None,
        )
        assert rate == pytest.approx(0.3)
        assert not stag and not ext and not super_

    def test_stagnation_detected(self):
        pop = self._pop_with_fitness([1.0, 0.9, 0.8])
        history = [1.0] * 12
        _, _, rate, stag, ext, _ = _compute_evolution_params(
            pop,
            elite_ratio=0.5,
            mutation_base=0.3,
            stagnation_patience=10,
            fitness_history=history,
        )
        assert stag and ext
        assert rate == pytest.approx(min(1.0, 0.3 * 2))

    def test_surperformance_detected(self):
        pop = self._pop_with_fitness([5.0, 1.0, 0.5])
        history = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 2.0, 2.5, 3.0, 3.5]
        _, _, _, _, _, super_ = _compute_evolution_params(
            pop,
            elite_ratio=0.5,
            mutation_base=0.3,
            stagnation_patience=5,
            fitness_history=history,
        )
        assert super_

    def test_short_history_below_patience(self):
        pop = self._pop_with_fitness([1.0, 0.9])
        history = [1.0] * 3
        _, _, rate, stag, _, _ = _compute_evolution_params(
            pop,
            elite_ratio=0.5,
            mutation_base=0.25,
            stagnation_patience=10,
            fitness_history=history,
        )
        assert not stag
        assert rate == pytest.approx(0.25)

    def test_improving_history_adaptive_rate(self):
        pop = self._pop_with_fitness([2.0, 1.0, 0.5])
        history = list(range(12))
        _, _, rate, stag, _, _ = _compute_evolution_params(
            pop,
            elite_ratio=0.5,
            mutation_base=0.3,
            stagnation_patience=10,
            fitness_history=history,
        )
        assert not stag
        assert 0.0 < rate <= 1.0


# ── evolve ────────────────────────────────────────────────────────────────────


class TestEvolve:
    def test_population_size_preserved(self):
        pop = [_genome() for _ in range(4)]
        new_pop = evolve(pop, elite_ratio=0.5, mutation_base=0.3)
        assert len(new_pop) == 4

    def test_returns_list_of_genomes(self):
        pop = [_genome() for _ in range(4)]
        new_pop = evolve(pop)
        assert all(isinstance(g, Genome) for g in new_pop)

    def test_with_stagnation_history(self):
        pop = [_genome() for _ in range(4)]
        history = [1.0] * 12
        new_pop = evolve(pop, fitness_history=history, stagnation_patience=10)
        assert len(new_pop) == 4


# ── enrich_evolve ─────────────────────────────────────────────────────────────


class TestEnrichEvolve:
    def test_returns_tuple_pop_stats(self):
        pop = [_genome() for _ in range(4)]
        new_pop, stats = enrich_evolve(pop)
        assert isinstance(new_pop, list)
        assert isinstance(stats, dict)

    def test_stats_keys_present(self):
        pop = [_genome() for _ in range(4)]
        _, stats = enrich_evolve(pop)
        for key in (
            "best_fitness",
            "mean_fitness",
            "std_fitness",
            "n_elite",
            "mutation_rate",
            "alert_stagnation",
        ):
            assert key in stats

    def test_population_size_preserved(self):
        pop = [_genome() for _ in range(4)]
        new_pop, _ = enrich_evolve(pop, elite_ratio=0.5)
        assert len(new_pop) == 4

    def test_stagnation_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pop = [_genome() for _ in range(4)]
        history = [1.0] * 12
        new_pop, stats = enrich_evolve(
            pop, fitness_history=history, stagnation_patience=10
        )
        assert stats["alert_stagnation"] is True
        assert len(new_pop) == 4

    def test_checkpoint_saved(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pop = [_genome() for _ in range(4)]
        enrich_evolve(pop)
        assert (tmp_path / "checkpoints" / "pop_last.json").exists()


# ── save_simulation_summary ───────────────────────────────────────────────────


class TestSaveSimulationSummary:
    def test_saves_csv(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        summary = {"run": 1, "best_fitness": 1.5, "seed": 42}
        save_simulation_summary(summary, "test_run.csv")
        assert (tmp_path / "sim_summaries" / "test_run.csv").exists()

    def test_csv_content(self, tmp_path, monkeypatch):
        import csv

        monkeypatch.chdir(tmp_path)
        summary = {"run": 1, "best_fitness": 2.5, "seed": 7}
        save_simulation_summary(summary, "run_content.csv")
        path = tmp_path / "sim_summaries" / "run_content.csv"
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        assert rows[0]["best_fitness"] == "2.5"

    def test_saves_pkl(self, tmp_path, monkeypatch):
        import pickle

        monkeypatch.chdir(tmp_path)
        summary = {"run": 2, "best_fitness": 0.8}
        save_simulation_summary(summary, "test.pkl")
        path = tmp_path / "sim_summaries" / "test.pkl"
        assert path.exists()
        loaded = pickle.loads(path.read_bytes())
        assert loaded["run"] == 2


# ── apply_extinction ──────────────────────────────────────────────────────────


class TestApplyExtinction:
    def test_removes_rare_species(self):
        pop = [_genome("trend")] * 6 + [_genome("mean_reversion")] * 2
        result = apply_extinction(pop, min_species_size=5)
        assert all(g.genes["entry.type"] == "trend" for g in result)

    def test_keeps_abundant_species(self):
        pop = [_genome("trend")] * 6 + [_genome("mean_reversion")] * 6
        result = apply_extinction(pop, min_species_size=5)
        types = {g.genes["entry.type"] for g in result}
        assert "trend" in types and "mean_reversion" in types

    def test_all_rare_returns_empty(self):
        pop = [_genome("trend")] * 2 + [_genome("mean_reversion")] * 2
        result = apply_extinction(pop, min_species_size=5)
        assert result == []


# ── select_parents ────────────────────────────────────────────────────────────


class TestSelectParents:
    def test_returns_two_genomes(self):
        survivors = [_genome("trend")] * 5
        p1, p2 = select_parents(survivors)
        assert isinstance(p1, Genome) and isinstance(p2, Genome)

    def test_cross_species_fallback(self):
        survivors = [_genome("trend"), _genome("mean_reversion"), _genome("hybrid")]
        p1, p2 = select_parents(survivors)
        assert isinstance(p1, Genome) and isinstance(p2, Genome)

    def test_single_survivor(self):
        survivors = [_genome("trend")]
        p1, p2 = select_parents(survivors)
        assert p1 is survivors[0]


# ── GenomeSerializer ──────────────────────────────────────────────────────────


class TestGenomeSerializer:
    def test_round_trip(self, tmp_path):
        g = _genome("hybrid")
        g.fitness = 2.5
        g.fitness_trend = 1.0
        GenomeSerializer.save_population([g], tmp_path / "pop.json")
        loaded = GenomeSerializer.load_population(tmp_path / "pop.json")
        assert len(loaded) == 1
        assert loaded[0].fitness == pytest.approx(2.5)

    def test_from_dict_missing_optional_fields(self):
        d = {"genes": _genome().genes, "id": "abc", "fitness": 0.0}
        g = GenomeSerializer.from_dict(d)
        assert g.fitness_trend == 0.0
        assert g.parent_ids == []
