"""
Test du MultiTimeframeBacktester — Validation robustesse MTF.
"""
from __future__ import annotations

import unittest

from quant_hedge_ai.strategy_factory.multi_timeframe_backtester import (
    SimpleMultiTimeframeBacktester,
)


class TestMultiTimeframeBacktester(unittest.TestCase):
    """Tests du backtester MTF."""

    def setUp(self) -> None:
        self.backtester = SimpleMultiTimeframeBacktester(
            timeframes=["5m", "15m", "1h"]
        )

    def test_consistency_score_all_positive(self) -> None:
        """Score = 1.0 si tous les PnL sont positifs."""
        pnls = [100.0, 150.0, 120.0]
        score = self.backtester._compute_consistency(pnls)
        self.assertEqual(score, 1.0)

    def test_consistency_score_partial(self) -> None:
        """Score = 0.67 si 2/3 positif."""
        pnls = [100.0, -50.0, 120.0]
        score = self.backtester._compute_consistency(pnls)
        self.assertAlmostEqual(score, 2/3, places=2)

    def test_consistency_score_all_negative(self) -> None:
        """Score = 0.0 si tous négatif."""
        pnls = [-50.0, -100.0, -75.0]
        score = self.backtester._compute_consistency(pnls)
        self.assertEqual(score, 0.0)

    def test_robust_strategy(self) -> None:
        """Stratégie robuste si consistency > 0.7."""
        strategy = {"threshold": 0.3, "name": "test_robust"}
        data_by_tf = {
            "5m": [{"close": 100 + i}  for i in range(10)],
            "15m": [{"close": 100 + i}  for i in range(10)],
            "1h": [{"close": 100 + i}  for i in range(10)],
        }

        result = self.backtester.run(strategy, data_by_tf)

        self.assertTrue(result["is_robust"], "Strategy doit être robuste (consistency > 0.7)")
        self.assertEqual(result["strategy"], strategy)
        self.assertIn("5m", result["results_by_tf"])

    def test_batch_backtest(self) -> None:
        """Backteste plusieurs stratégies."""
        strategies = [
            {"threshold": 0.2, "name": "s1"},
            {"threshold": 0.5, "name": "s2"},
            {"threshold": 0.8, "name": "s3"},
        ]
        data_by_tf = {
            "5m": [{"close": 100 + i} for i in range(10)],
            "15m": [{"close": 100 + i} for i in range(10)],
        }

        results = self.backtester.run_batch(strategies, data_by_tf)

        self.assertEqual(len(results), 3)
        for result in results:
            self.assertIn("avg_pnl", result)
            self.assertIn("consistency_score", result)
            self.assertIn("is_robust", result)


if __name__ == "__main__":
    unittest.main()
