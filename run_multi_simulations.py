"""
Module : run_multi_simulations.py
Automatise le lancement de plusieurs simulations évolutionnaires et sauvegarde un résumé pour chaque run.
"""

import os
import random

from evolution_core import create_population, evolve, save_simulation_summary


def run_multi_simulations(
    n_runs=5,
    pop_size=50,
    n_generations=30,
    elite_ratio=0.1,
    mutation_base=0.3,
    stagnation_patience=10,
    seed_start=42,
):
    """
    Lance n_runs simulations indépendantes, sauvegarde un résumé pour chaque run.
    """
    for i in range(n_runs):
        seed = seed_start + i
        random.seed(seed)
        pop = create_population(pop_size)
        fitness_history = []
        for gen in range(n_generations):
            pop = evolve(
                pop,
                elite_ratio=elite_ratio,
                mutation_base=mutation_base,
                stagnation_patience=stagnation_patience,
                fitness_history=fitness_history,
            )
            best = max(pop, key=lambda g: g.fitness)
            fitness_history.append(best.fitness)
        best = max(pop, key=lambda g: g.fitness)
        summary = {
            "run": i + 1,
            "seed": seed,
            "elite_ratio": elite_ratio,
            "mutation_base": mutation_base,
            "stagnation_patience": stagnation_patience,
            "pop_size": pop_size,
            "n_generations": n_generations,
            "best_fitness": best.fitness,
            "mean_fitness": sum(g.fitness for g in pop) / len(pop),
            "std_fitness": (
                sum(
                    (g.fitness - sum(g2.fitness for g2 in pop) / len(pop)) ** 2
                    for g in pop
                )
                / len(pop)
            )
            ** 0.5,
        }
        save_simulation_summary(summary, f"sim_run_{i+1}.csv")
        print(f"[multi-sim] Résumé sauvegardé pour run {i+1}")


if __name__ == "__main__":
    run_multi_simulations(n_runs=5, pop_size=50, n_generations=30)
