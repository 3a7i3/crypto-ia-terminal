"""
Test du module StrategyEvolutionEngine.
"""

import unittest

from quant_hedge_ai.strategy_lab.evolution_engine import \
    StrategyEvolutionEngine


class TestStrategyEvolutionEngine(unittest.TestCase):
    def test_mutate_threshold(self):
        engine = StrategyEvolutionEngine(mutation_rate=1.0)  # mutation forcée
        strat = {"threshold": 0.05, "window": 10}
        mutated = engine.mutate(strat)
        self.assertNotEqual(mutated["threshold"], 0.05)
        self.assertIn(mutated["window"], [9, 11])
        # Ne modifie pas l'original
        self.assertEqual(strat["threshold"], 0.05)
        self.assertEqual(strat["window"], 10)

    def test_no_mutation(self):
        engine = StrategyEvolutionEngine(mutation_rate=0.0)
        strat = {"threshold": 0.05, "window": 10}
        mutated = engine.mutate(strat)
        self.assertEqual(mutated, strat)


if __name__ == "__main__":
    unittest.main()
