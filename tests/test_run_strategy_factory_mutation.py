from __future__ import annotations

import pytest

pytest.importorskip("matplotlib")

from run_strategy_factory import GENE_SPACE, Genome, mutate


def test_mutation_extreme_keeps_genes_within_gene_space_bounds() -> None:
    genome = Genome()
    for key, value in genome.genes.items():
        if isinstance(value, float):
            genome.genes[key] = -1e9

    mutated = mutate(genome, mutation_rate=1, intensity=1)

    for key, value in mutated.genes.items():
        if key in GENE_SPACE and isinstance(GENE_SPACE[key], tuple):
            lower_bound, upper_bound = GENE_SPACE[key]
            assert value >= lower_bound
            assert value <= upper_bound