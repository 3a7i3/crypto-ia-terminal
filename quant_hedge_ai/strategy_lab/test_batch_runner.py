"""
Test du module BatchRunner.
"""

import unittest

from quant_hedge_ai.strategy_lab.batch_runner import BatchRunner


class TestBatchRunner(unittest.TestCase):
    def test_run_batches(self):
        runner = BatchRunner(batch_size=2)
        items = [1, 2, 3, 4, 5]

        def square(x):
            return x * x

        results = runner.run_batches(items, square)
        self.assertEqual(results, [1, 4, 9, 16, 25])


if __name__ == "__main__":
    unittest.main()
