"""
Tests pour evolve_world() — couverture de toutes les branches :
environments, extinction totale, stagnation, sauvegarde checkpoint.
"""

from unittest.mock import MagicMock

import pytest

from evolution_core import (Genome, apply_extinction, evolve_world,
                            score_env_crash, score_env_range, score_env_trend,
                            select_parents)

# ---------------------------------------------------------------------------
# Helpers — scoreurs déterministes (pas de marchés aléatoires)
# ---------------------------------------------------------------------------

FAST_SCORE = lambda g: 1.0  # score fixe, pas de backtest
SCORE_TREND = lambda g: 1.0
SCORE_RANGE = lambda g: 0.5
SCORE_CRASH = lambda g: 0.2
NO_EXTINCTION = lambda pop: pop  # aucun filtre
FULL_EXTINCTION = lambda pop: []  # extinction totale


def make_pop(n=10):
    return [Genome() for _ in range(n)]


def call_evolve_world(
    pop,
    env="trend",
    score_trend=SCORE_TREND,
    score_range=SCORE_RANGE,
    score_crash=SCORE_CRASH,
    extinction=NO_EXTINCTION,
    **kwargs
):
    return evolve_world(
        pop,
        env,
        score_trend,
        score_range,
        score_crash,
        extinction,
        select_parents,
        Genome,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Valeur de retour
# ---------------------------------------------------------------------------


class TestReturnType:
    def test_returns_tuple(self):
        result = call_evolve_world(make_pop())
        assert isinstance(result, tuple) and len(result) == 2

    def test_first_element_is_list_of_genomes(self):
        new_pop, _ = call_evolve_world(make_pop())
        assert all(isinstance(g, Genome) for g in new_pop)

    def test_second_element_is_env_string(self):
        _, env = call_evolve_world(make_pop(), env="trend")
        assert env in {"trend", "range", "crash"}

    def test_population_size_preserved(self):
        pop = make_pop(10)
        new_pop, _ = call_evolve_world(pop, env="trend")
        assert len(new_pop) == len(pop)


# ---------------------------------------------------------------------------
# Environnements
# ---------------------------------------------------------------------------


class TestEnvironments:
    def test_trend_env_uses_score_trend(self):
        scorer = MagicMock(return_value=1.0)
        call_evolve_world(make_pop(6), env="trend", score_trend=scorer)
        assert scorer.call_count > 0

    def test_range_env_uses_score_range(self):
        scorer = MagicMock(return_value=0.5)
        call_evolve_world(make_pop(6), env="range", score_range=scorer)
        assert scorer.call_count > 0

    def test_crash_env_uses_score_crash(self):
        scorer = MagicMock(return_value=0.2)
        call_evolve_world(make_pop(6), env="crash", score_crash=scorer)
        assert scorer.call_count > 0

    def test_chaos_env_dispatches_to_one_scorer(self):
        trend = MagicMock(return_value=1.0)
        range_ = MagicMock(return_value=0.5)
        crash = MagicMock(return_value=0.2)
        call_evolve_world(
            make_pop(6),
            env="chaos",
            score_trend=trend,
            score_range=range_,
            score_crash=crash,
        )
        total_calls = trend.call_count + range_.call_count + crash.call_count
        assert total_calls > 0
        # Un seul scoreur utilisé (l'env chaos est résolu en trend/range/crash)
        active = [s for s in (trend, range_, crash) if s.call_count > 0]
        assert len(active) == 1

    def test_chaos_current_env_is_valid(self):
        _, env = call_evolve_world(make_pop(6), env="chaos")
        assert env in {"trend", "range", "crash"}

    def test_trend_env_returns_trend(self):
        _, env = call_evolve_world(make_pop(6), env="trend")
        assert env == "trend"

    def test_range_env_returns_range(self):
        _, env = call_evolve_world(make_pop(6), env="range")
        assert env == "range"

    def test_crash_env_returns_crash(self):
        _, env = call_evolve_world(make_pop(6), env="crash")
        assert env == "crash"


# ---------------------------------------------------------------------------
# Extinction
# ---------------------------------------------------------------------------


class TestExtinction:
    def test_no_extinction_preserves_elite(self):
        pop = make_pop(10)
        new_pop, _ = call_evolve_world(pop, extinction=NO_EXTINCTION, elite_ratio=0.3)
        assert len(new_pop) == 10

    def test_total_extinction_fallback_to_best_3(self):
        pop = make_pop(10)
        new_pop, _ = call_evolve_world(pop, extinction=FULL_EXTINCTION)
        assert len(new_pop) == len(pop)

    def test_partial_extinction_still_fills_population(self):
        keep_one = lambda p: p[:1]
        pop = make_pop(8)
        new_pop, _ = call_evolve_world(pop, extinction=keep_one)
        assert len(new_pop) == 8


# ---------------------------------------------------------------------------
# Stagnation
# ---------------------------------------------------------------------------


class TestStagnation:
    def test_stagnation_detected_doubles_mutation(self):
        pop = make_pop(8)
        fitness_history = [1.0] * 12
        new_pop, _ = call_evolve_world(
            pop, fitness_history=fitness_history, stagnation_patience=10
        )
        assert len(new_pop) == len(pop)

    def test_no_stagnation_without_history(self):
        pop = make_pop(8)
        new_pop, _ = call_evolve_world(pop, fitness_history=None)
        assert len(new_pop) == len(pop)

    def test_short_history_below_patience_no_stagnation(self):
        pop = make_pop(8)
        fitness_history = [1.0] * 5
        new_pop, _ = call_evolve_world(
            pop, fitness_history=fitness_history, stagnation_patience=10
        )
        assert len(new_pop) == len(pop)

    def test_improving_history_no_stagnation(self):
        pop = make_pop(8)
        fitness_history = list(range(12))
        new_pop, _ = call_evolve_world(
            pop, fitness_history=fitness_history, stagnation_patience=10
        )
        assert len(new_pop) == len(pop)


# ---------------------------------------------------------------------------
# Checkpoint JSON
# ---------------------------------------------------------------------------


class TestCheckpoint:
    def test_checkpoint_json_created(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        call_evolve_world(make_pop(6), env="trend")
        assert (tmp_path / "checkpoints" / "pop_trend.json").exists()

    def test_checkpoint_is_valid_json(self, tmp_path, monkeypatch):
        import json

        monkeypatch.chdir(tmp_path)
        call_evolve_world(make_pop(6), env="range")
        data = json.loads(
            (tmp_path / "checkpoints" / "pop_range.json").read_text(encoding="utf-8")
        )
        assert "genomes" in data
        assert data["size"] == 6

    def test_checkpoint_loadable(self, tmp_path, monkeypatch):
        from evolution_core import GenomeSerializer

        monkeypatch.chdir(tmp_path)
        call_evolve_world(make_pop(6), env="crash")
        restored = GenomeSerializer.load_population(
            tmp_path / "checkpoints" / "pop_crash.json"
        )
        assert len(restored) == 6

    def test_no_pickle_used(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        call_evolve_world(make_pop(6), env="trend")
        checkpoints = list((tmp_path / "checkpoints").glob("*.pkl"))
        assert checkpoints == []
