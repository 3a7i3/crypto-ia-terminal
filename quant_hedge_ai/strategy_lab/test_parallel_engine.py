"""
Test du module ParallelEngine.
"""

import unittest

from quant_hedge_ai.strategy_lab.parallel_engine import ParallelEngine


def square(x):
    return x * x


class TestParallelEngine(unittest.TestCase):
    def test_run_multiprocessing(self):
        engine = ParallelEngine(n_jobs=2)
        items = [1, 2, 3, 4]
        results = engine.run_multiprocessing(items, square)
        self.assertEqual(sorted(results), [1, 4, 9, 16])

    def test_run_joblib(self):
        engine = ParallelEngine(n_jobs=2)
        items = [1, 2, 3, 4]
        results = engine.run_joblib(items, square)
        self.assertEqual(sorted(results), [1, 4, 9, 16])


if __name__ == "__main__":
    unittest.main()
