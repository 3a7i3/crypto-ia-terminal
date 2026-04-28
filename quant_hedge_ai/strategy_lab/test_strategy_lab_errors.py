"""
Tests d'erreurs et cas limites pour strategy_lab.
"""

import unittest

from quant_hedge_ai.strategy_lab.backtest_launcher import BacktestLauncher
from quant_hedge_ai.strategy_lab.generator import StrategyGenerator
from quant_hedge_ai.strategy_lab.parameter_space import ParameterSpace
from quant_hedge_ai.strategy_lab.ranker import StrategyRanker
from quant_hedge_ai.strategy_lab.signal_builder import SignalBuilder
from quant_hedge_ai.strategy_lab.strategy_db import StrategyDatabase
from quant_hedge_ai.strategy_lab.templates import StrategyTemplate


class TestStrategyLabErrors(unittest.TestCase):
    def test_signal_builder_unexpected_input(self):
        logic = "IF momentum_14 > {threshold}: BUY ELSE: HOLD"
        template = StrategyTemplate("momentum", logic)
        sb = SignalBuilder(template, {"threshold": 0.03})
        # Données manquantes
        with self.assertRaises(KeyError):
            sb.build({"rsi_7": [0.1, 0.2]})
        # Types inattendus
        with self.assertRaises(TypeError):
            sb.build({"momentum_14": "not_a_list"})

    def test_generator_empty(self):
        generator = StrategyGenerator([], [])
        self.assertEqual(generator.generate(), [])

    def test_parameter_space_unknown(self):
        ps = ParameterSpace("unknown")
        self.assertEqual(ps.get_grid(), [{}])

    def test_template_missing_param(self):
        template = StrategyTemplate(
            "momentum", "IF momentum_14 > {threshold}: BUY ELSE: HOLD"
        )
        with self.assertRaises(KeyError):
            template.inject_params({})

    def test_signal_builder_bad_logic(self):
        template = StrategyTemplate("momentum", "BAD LOGIC")
        sb = SignalBuilder(template, {"threshold": 0.03})
        with self.assertRaises(ValueError):
            sb.build({"momentum_14": [0.01, 0.04]})

    def test_backtest_launcher_empty(self):
        logic = "IF momentum_14 > {threshold}: BUY ELSE: HOLD"
        template = StrategyTemplate("momentum", logic)
        sb = SignalBuilder(template, {"threshold": 0.03})
        bl = BacktestLauncher(None)
        metrics = bl.run(sb, {"momentum_14": []})
        self.assertEqual(metrics["n_buy"], 0)
        self.assertEqual(metrics["n_hold"], 0)
        self.assertEqual(metrics["total"], 0)

    def test_ranker_missing_metric(self):
        ranker = StrategyRanker({"sharpe": 1.0, "drawdown": -0.5})
        metrics = [{"sharpe": 1.0}]  # manque drawdown
        scores = ranker.rank(metrics)
        self.assertEqual(len(scores), 1)
        self.assertAlmostEqual(scores[0][1], 1.0 * 1.0 + 0 * (-0.5))

    def test_strategy_db_empty(self):
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            db_path = tmp.name
        db = StrategyDatabase(db_path)
        result = db.top_strategies(1)
        db.conn.close()
        os.remove(db_path)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
