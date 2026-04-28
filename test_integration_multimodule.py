import os
import unittest

from run_strategy_factory import (create_population, evaluate_fitness, evolve,
                                  mutate)
from terminal_core.quant.logging_alerts import log_and_alert


class TestIntegrationMultiModule(unittest.TestCase):
    def test_full_workflow_with_alerts(self):
        # 1. Génération population
        pop = create_population(50)
        self.assertTrue(len(pop) == 50)
        # 2. Mutation
        mutated = [mutate(g) for g in pop]
        # 3. Scoring
        for g in mutated:
            evaluate_fitness(g)
        # 4. Evolution (nouvelle génération)
        new_pop = evolve(mutated)
        self.assertTrue(len(new_pop) == 50)
        # 5. Logging et alertes
        try:
            log_and_alert("info", "Test multi-module OK", alert=True)
        except Exception as e:
            self.fail(f"Erreur lors de l'appel log_and_alert: {e}")
        # 6. Vérifie qu'un fichier de log a été créé
        self.assertTrue(os.path.exists("quant_system.log"))


if __name__ == "__main__":
    unittest.main()
