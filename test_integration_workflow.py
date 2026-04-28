import os
import unittest

import pandas as pd

from run_strategy_factory import (Genome, create_population, mutate,
                                  plot_god_mode, score_env_trend)
from terminal_core.quant.logging_alerts import logger


class TestIntegrationWorkflow(unittest.TestCase):
    def test_full_workflow(self):
        # 1. Génération de population
        pop = create_population(10)
        self.assertEqual(len(pop), 10)
        self.assertTrue(all(isinstance(g, Genome) for g in pop))

        # 2. Mutation
        mutated = [mutate(g, mutation_rate=0.5, intensity=0.5) for g in pop]
        self.assertEqual(len(mutated), 10)

        # 3. Scoring
        scores = [score_env_trend(g) for g in mutated]
        self.assertTrue(all(isinstance(s, float) for s in scores))

        # 4. Reporting (DataFrame + plot)
        df = pd.DataFrame(
            [
                {
                    "id": i,
                    "fitness": s,
                    "species": g.genes.get("entry.type", "?"),
                    "exit.tp": g.genes.get("exit.tp", 0),
                    "exit.sl": g.genes.get("exit.sl", 0),
                }
                for i, (g, s) in enumerate(zip(mutated, scores))
            ]
        )
        os.makedirs("results", exist_ok=True)
        plot_god_mode(df)
        self.assertTrue(os.path.exists("results/god_mode_3d.png"))
        logger.info("Test d'intégration complet exécuté avec succès.")


if __name__ == "__main__":
    unittest.main()
