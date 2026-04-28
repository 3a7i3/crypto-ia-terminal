import pytest

from evolution_core import (Genome, apply_extinction, create_population,
                            crossover, evaluate_fitness, mutate)


def test_mutate_changes_genome():
    g = Genome()
    g2 = mutate(g, mutation_rate=1.0, intensity=0.5)
    # Au moins un gène doit changer
    assert any(g.genes[k] != g2.genes[k] for k in g.genes)


def test_crossover_combines_genes():
    g1 = Genome()
    g2 = Genome()
    child = crossover(g1, g2)
    # Les gènes du child doivent venir de g1 ou g2
    for k in g1.genes:
        assert child.genes[k] == g1.genes[k] or child.genes[k] == g2.genes[k]


def test_apply_extinction_removes_rare_species():
    pop = [Genome({"entry.type": "trend"}) for _ in range(10)]
    pop += [Genome({"entry.type": "rare"}) for _ in range(2)]
    filtered = apply_extinction(pop, min_species_size=3)
    assert all(g.genes["entry.type"] != "rare" for g in filtered)


def test_evaluate_fitness_sets_values():
    g = Genome()
    evaluate_fitness(g)
    assert isinstance(g.fitness, float)
    assert isinstance(g.fitness_trend, float)
    assert isinstance(g.fitness_range, float)
    assert isinstance(g.fitness_crash, float)


def test_create_population_size():
    pop = create_population(7)
    assert len(pop) == 7
