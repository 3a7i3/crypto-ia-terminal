import unittest

missing = []
try:
    import pandas
except ImportError:
    missing.append("pandas")
try:
    import pytest
except ImportError:
    missing.append("pytest")
if missing:

    @unittest.skip(f"Modules manquants : {', '.join(missing)}")
    class TestFullsuite(unittest.TestCase):
        def test_neutralise(self):
            pass

else:
    # ...existing code...
    import os
    import sys

    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    import random
    import time
    import unittest

    import pandas as pd

    from run_strategy_factory import (Genome,
                                      create_population,
                                      mutate, plot_dominance, plot_god_mode)


class TestFullSuite(unittest.TestCase):
    def test_performance_large_population(self):
        # Teste la génération et mutation sur une grande population
        pop_size = 200
        pop = create_population(pop_size)
        start = time.time()
        [mutate(g, mutation_rate=1, intensity=1) for g in pop]
        duration = time.time() - start
        self.assertLess(
            duration,
            10,
            f"Mutation trop lente: {duration:.2f}s pour {pop_size} individus",
        )

    def test_visualization_outputs(self):
        # Teste la génération de fichiers PNG par plot_god_mode et plot_dominance
        df = pd.DataFrame(
            {
                "exit.tp": [1.0, 2.0, 3.0],
                "exit.sl": [0.5, 1.0, 1.5],
                "fitness": [0.8, 1.2, 0.9],
                "species": ["trend", "mean_reversion", "hybrid"],
                "id": ["a", "b", "c"],
                "generation": [0, 0, 0],
            }
        )
        import run_strategy_factory

        run_strategy_factory.SHOW_PLOTS = False
        plot_god_mode(df)
        self.assertTrue(os.path.exists("results/god_mode_3d.png"))
        df2 = pd.DataFrame(
            {"generation": [0, 0, 1, 1], "species": ["A", "B", "A", "B"]}
        )
        plot_dominance(df2)
        self.assertTrue(os.path.exists("results/dominance_by_species.png"))

    def test_integration_full_cycle(self):
        # Génère, évolue, sauvegarde, relit et vérifie la cohérence
        pop = create_population(5)
        for g in pop:
            g.fitness = random.random()
        df = pd.DataFrame(
            [
                {
                    **g.genes,
                    "fitness": g.fitness,
                    "id": g.id,
                    "species": g.genes["entry.type"],
                }
                for g in pop
            ]
        )
        path = "results/test_cycle.csv"
        df.to_csv(path, index=False)
        df2 = pd.read_csv(path)
        self.assertEqual(len(df2), 5)
        self.assertIn("fitness", df2.columns)
        self.assertIn("id", df2.columns)

    def test_reproducibility(self):
        # Fixe le seed et vérifie la reproductibilité
        random.seed(42)
        pop1 = create_population(3)
        genes1 = [g.genes for g in pop1]
        random.seed(42)
        pop2 = create_population(3)
        genes2 = [g.genes for g in pop2]
        self.assertEqual(genes1, genes2)

    def test_error_handling_in_mutate(self):
        # Simule une erreur dans mutate et vérifie la gestion
        class BadGenome(Genome):
            def __init__(self):
                super().__init__()
                self.genes = None  # Provoque une erreur

        with self.assertRaises(Exception):
            mutate(BadGenome())


if __name__ == "__main__":
    unittest.main()
