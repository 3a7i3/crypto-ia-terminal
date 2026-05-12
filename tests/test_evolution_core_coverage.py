"""
Tests de couverture pour les fonctions d'evolution_core.py non atteintes :
score_env_*, migrate(), enrich_evolve(), save_simulation_summary().
"""

import csv
import pickle

import pytest

from evolution_core import (GENE_SPACE, Genome, clamp_gene, enrich_evolve,
                            migrate, save_simulation_summary, score_env_crash,
                            score_env_range, score_env_trend, select_parents)

# ---------------------------------------------------------------------------
# score_env_* — scoreurs par environnement
# ---------------------------------------------------------------------------


class TestScoreEnv:
    def test_score_env_trend_returns_float(self):
        g = Genome()
        score = score_env_trend(g)
        assert isinstance(score, float)

    def test_score_env_range_returns_float(self):
        g = Genome()
        score = score_env_range(g)
        assert isinstance(score, float)

    def test_score_env_crash_returns_float(self):
        g = Genome()
        score = score_env_crash(g)
        assert isinstance(score, float)

    def test_scores_differ_across_envs(self):
        import random

        import numpy as np

        random.seed(0)
        np.random.seed(0)
        g = Genome()
        t = score_env_trend(g)
        random.seed(0)
        np.random.seed(0)
        r = score_env_range(g)
        random.seed(0)
        np.random.seed(0)
        c = score_env_crash(g)
        # Les 3 scores ne sont pas tous identiques (marchés différents)
        assert not (t == r == c)


# ---------------------------------------------------------------------------
# migrate()
# ---------------------------------------------------------------------------


class TestMigrate:
    def _make_populations(self, n_worlds=2, pop_size=10):
        pops = {}
        for i in range(n_worlds):
            pop = [Genome() for _ in range(pop_size)]
            for g in pop:
                g.fitness = float(i + 1)
            pops[f"world_{i}"] = pop
        return pops

    def test_returns_same_worlds(self):
        pops = self._make_populations()
        result = migrate(pops, migration_rate=0.1, pop_size=10)
        assert set(result.keys()) == set(pops.keys())

    def test_population_size_preserved(self):
        pops = self._make_populations(pop_size=10)
        result = migrate(pops, migration_rate=0.2, pop_size=10)
        for world in result.values():
            assert len(world) == 10

    def test_migration_moves_individuals(self):
        pops = self._make_populations(n_worlds=2, pop_size=10)
        ids_before = {w: {g.id for g in pop} for w, pop in pops.items()}
        result = migrate(pops, migration_rate=0.3, pop_size=10)
        ids_after = {w: {g.id for g in pop} for w, pop in result.items()}
        # Au moins un monde doit avoir reçu de nouveaux individus
        changed = any(ids_after[w] != ids_before[w] for w in ids_before)
        assert changed

    def test_three_worlds(self):
        pops = self._make_populations(n_worlds=3, pop_size=8)
        result = migrate(pops, migration_rate=0.1, pop_size=8)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# enrich_evolve()
# ---------------------------------------------------------------------------


class TestEnrichEvolve:
    def test_returns_tuple(self):
        pop = [Genome() for _ in range(6)]
        result = enrich_evolve(pop)
        assert isinstance(result, tuple) and len(result) == 2

    def test_population_same_size(self):
        pop = [Genome() for _ in range(6)]
        new_pop, _ = enrich_evolve(pop)
        assert len(new_pop) == 6

    def test_stats_keys(self):
        pop = [Genome() for _ in range(6)]
        _, stats = enrich_evolve(pop)
        expected = {
            "best_fitness",
            "mean_fitness",
            "std_fitness",
            "n_elite",
            "mutation_rate",
            "alert_stagnation",
            "alert_extinction",
            "alert_surperformance",
        }
        assert set(stats.keys()) == expected

    def test_stats_types(self):
        pop = [Genome() for _ in range(6)]
        _, stats = enrich_evolve(pop)
        assert isinstance(stats["best_fitness"], float)
        assert isinstance(stats["mean_fitness"], (float, int))
        assert isinstance(stats["alert_stagnation"], bool)

    def test_stagnation_detected(self):
        pop = [Genome() for _ in range(6)]
        fitness_history = [1.0] * 12
        _, stats = enrich_evolve(
            pop, stagnation_patience=10, fitness_history=fitness_history
        )
        assert stats["alert_stagnation"] is True
        assert stats["alert_extinction"] is True


# ---------------------------------------------------------------------------
# save_simulation_summary()
# ---------------------------------------------------------------------------


class TestSaveSimulationSummary:
    def test_saves_csv(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        summary = {"best_fitness": 1.5, "generation": 10}
        save_simulation_summary(summary, "summary.csv")
        csv_path = tmp_path / "sim_summaries" / "summary.csv"
        assert csv_path.exists()
        rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
        assert len(rows) == 1
        assert float(rows[0]["best_fitness"]) == pytest.approx(1.5)

    def test_saves_pkl(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        summary = {"best_fitness": 2.0, "generation": 5}
        save_simulation_summary(summary, "summary.pkl")
        pkl_path = tmp_path / "sim_summaries" / "summary.pkl"
        assert pkl_path.exists()
        with open(pkl_path, "rb") as f:
            loaded = pickle.load(f)
        assert loaded["best_fitness"] == 2.0


# ---------------------------------------------------------------------------
# clamp_gene() — branches manquantes
# ---------------------------------------------------------------------------


class TestClampGene:
    def test_clamps_above_max(self):
        result = clamp_gene("exit.tp", 999.0)
        assert result == GENE_SPACE["exit.tp"][1]

    def test_clamps_below_min(self):
        result = clamp_gene("exit.tp", -999.0)
        assert result == GENE_SPACE["exit.tp"][0]

    def test_passthrough_for_list_gene(self):
        result = clamp_gene("entry.type", "trend")
        assert result == "trend"


# ---------------------------------------------------------------------------
# select_parents()
# ---------------------------------------------------------------------------


class TestSelectParents:
    def test_returns_two_genomes(self):
        survivors = [Genome() for _ in range(5)]
        p1, p2 = select_parents(survivors)
        assert isinstance(p1, Genome) and isinstance(p2, Genome)

    def test_same_species_preferred(self):
        survivors = [Genome({"entry.type": "trend"}) for _ in range(10)]
        survivors += [Genome({"entry.type": "hybrid"})]
        p1, p2 = select_parents(survivors)
        assert p1.genes["entry.type"] == p2.genes["entry.type"]

    def test_single_survivor_returns_same_parent_twice(self):
        survivors = [Genome()]
        p1, p2 = select_parents(survivors)
        assert p1.id == p2.id
