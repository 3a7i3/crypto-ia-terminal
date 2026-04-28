import time
import unittest

from run_strategy_factory import (create_population, evaluate_fitness, evolve,
                                  mutate)


class TestPerformanceBenchmarks(unittest.TestCase):
    def setUp(self):
        self.pop_size = 500
        self.population = create_population(self.pop_size)

    def test_mutation_speed(self):
        start = time.time()
        mutated = [mutate(g) for g in self.population]
        elapsed = time.time() - start
        print(f"Mutation de {self.pop_size} individus: {elapsed:.3f}s")
        self.assertLess(elapsed, 2.0, "Mutation trop lente")

    def test_scoring_speed(self):
        mutated = [mutate(g) for g in self.population]
        start = time.time()
        for g in mutated:
            evaluate_fitness(g)
        elapsed = time.time() - start
        print(f"Scoring de {self.pop_size} individus: {elapsed:.3f}s")
        self.assertLess(elapsed, 3.0, "Scoring trop lent")

    def test_end_to_end_workflow(self):
        start = time.time()
        pop = [mutate(g) for g in self.population]
        for g in pop:
            evaluate_fitness(g)
        pop = sorted(pop, key=lambda x: x.fitness, reverse=True)
        # Simule une sélection et une nouvelle génération
        survivors = pop[: max(1, int(len(pop) * 0.2))]
        new_pop = []
        import random

        from run_strategy_factory import crossover

        while len(new_pop) < len(pop):
            p1 = random.choice(survivors)
            p2 = random.choice(survivors)
            child = crossover(p1, p2)
            child = mutate(child)
            evaluate_fitness(child)
            new_pop.append(child)
        elapsed = time.time() - start
        print(f"Workflow complet (mutation+scoring+génération): {elapsed:.3f}s")
        self.assertLess(elapsed, 8.0, "Workflow complet trop lent")


if __name__ == "__main__":
    unittest.main()
