from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("matplotlib")

from run_strategy_factory import Genome, apply_extinction, crossover


def test_genome_id_is_unique() -> None:
    first = Genome()
    second = Genome()
    assert first.id != second.id


def test_genome_id_has_expected_length() -> None:
    genome = Genome()
    assert len(genome.id) == 8


def test_crossover_keeps_parent_ids() -> None:
    parent_one = Genome()
    parent_two = Genome()
    child = crossover(parent_one, parent_two)
    assert child.parent_ids == [parent_one.id, parent_two.id]


def test_genome_dataframe_row_keeps_tracking_columns() -> None:
    genome = Genome()
    genome.fitness = 1.23
    genome.genes["entry.type"] = "trend"
    genome.parent_ids = ["parent1", "parent2"]

    row = {
        **genome.genes,
        "fitness": genome.fitness,
        "id": genome.id,
        "environment": "trend",
        "species": genome.genes["entry.type"],
        "world": "trend",
        "parent_ids": ",".join(genome.parent_ids),
    }
    dataframe = pd.DataFrame([row])

    assert {"id", "species", "parent_ids"}.issubset(dataframe.columns)
    assert dataframe.loc[0, "id"] == genome.id
    assert dataframe.loc[0, "species"] == "trend"
    assert dataframe.loc[0, "parent_ids"] == "parent1,parent2"


def test_apply_extinction_drops_population_when_species_too_rare() -> None:
    population = [Genome({"entry.type": "rare"}) for _ in range(3)]

    survivors = apply_extinction(population, min_species_size=5)

    assert survivors == []


def test_apply_extinction_keeps_empty_population_empty() -> None:
    assert apply_extinction([], min_species_size=5) == []
