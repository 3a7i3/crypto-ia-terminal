from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    try:
        from run_strategy_factory import create_population, crossover, evaluate_fitness, mutate
    except ModuleNotFoundError as exc:
        print(f"Dépendance manquante pour le benchmark: {exc}")
        return 1

    pop_size = 500
    population = create_population(pop_size)

    start = time.time()
    mutated = [mutate(genome) for genome in population]
    mutation_elapsed = time.time() - start
    print(f"Mutation de {pop_size} individus: {mutation_elapsed:.3f}s")

    start = time.time()
    for genome in mutated:
        evaluate_fitness(genome)
    scoring_elapsed = time.time() - start
    print(f"Scoring de {pop_size} individus: {scoring_elapsed:.3f}s")

    start = time.time()
    workflow_population = [mutate(genome) for genome in population]
    for genome in workflow_population:
        evaluate_fitness(genome)
    workflow_population = sorted(workflow_population, key=lambda item: item.fitness, reverse=True)
    survivors = workflow_population[: max(1, int(len(workflow_population) * 0.2))]
    new_population = []
    while len(new_population) < len(workflow_population):
        parent_one = random.choice(survivors)
        parent_two = random.choice(survivors)
        child = crossover(parent_one, parent_two)
        child = mutate(child)
        evaluate_fitness(child)
        new_population.append(child)
    workflow_elapsed = time.time() - start
    print(f"Workflow complet (mutation+scoring+génération): {workflow_elapsed:.3f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())