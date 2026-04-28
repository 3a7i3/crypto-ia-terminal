"""
Tests unitaires pour le module strategy_lab.
"""

import unittest

from quant_hedge_ai.strategy_lab.backtest_launcher import BacktestLauncher
from quant_hedge_ai.strategy_lab.generator import StrategyGenerator
from quant_hedge_ai.strategy_lab.parameter_space import ParameterSpace
from quant_hedge_ai.strategy_lab.ranker import StrategyRanker
from quant_hedge_ai.strategy_lab.signal_builder import SignalBuilder
from quant_hedge_ai.strategy_lab.strategy_db import StrategyDatabase
from quant_hedge_ai.strategy_lab.templates import StrategyTemplate


class TestStrategyLab(unittest.TestCase):
    def test_backward_compatibility(self):
        # Ancien template sans nouveau paramètre
        logic = "IF momentum_14 > {threshold}: BUY ELSE: HOLD"
        template = StrategyTemplate("momentum", logic)
        params = {"threshold": 0.03, "unused_param": 123}
        # inject_params doit ignorer les paramètres inutilisés
        result = template.inject_params(params)
        self.assertIn("0.03", result)

    def test_complex_strategy(self):
        logic = "IF momentum_14 > {threshold} AND rsi_7 < {rsi_level}: BUY ELSE: HOLD"
        template = StrategyTemplate("complex", logic)
        params = {"threshold": 0.03, "rsi_level": 30}
        result = template.inject_params(params)
        self.assertIn("0.03", result)
        self.assertIn("30", result)
        sb = SignalBuilder(template, params)
        data = {"momentum_14": [0.04, 0.02], "rsi_7": [25, 35]}
        signals = sb.build(data)
        # Premier point: momentum > threshold et rsi < rsi_level => BUY
        # Deuxième point: rsi > rsi_level => HOLD
        self.assertEqual(signals, ["BUY", "HOLD"])

    def test_strategy_generator(self):
        features = ["momentum_14", "rsi_7"]
        templates = ["momentum", "breakout"]
        generator = StrategyGenerator(features, templates)
        combos = generator.generate()
        expected = [
            ("momentum_14", "momentum"),
            ("momentum_14", "breakout"),
            ("rsi_7", "momentum"),
            ("rsi_7", "breakout"),
        ]
        self.assertEqual(set(combos), set(expected))

    def test_parameter_space(self):
        ps = ParameterSpace("momentum")
        grid = ps.get_grid()
        self.assertIn({"threshold": 0.01}, grid)
        self.assertIn({"threshold": 0.03}, grid)
        ps2 = ParameterSpace("breakout")
        grid2 = ps2.get_grid()
        self.assertIn({"window": 10}, grid2)
        self.assertIn({"window": 20}, grid2)

    def test_strategy_template(self):
        logic = "IF momentum_14 > {threshold}: BUY ELSE: HOLD"
        template = StrategyTemplate("momentum", logic)
        result = template.inject_params({"threshold": 0.03})
        self.assertEqual(result, "IF momentum_14 > 0.03: BUY ELSE: HOLD")

    def test_signal_builder(self):
        logic = "IF momentum_14 > {threshold}: BUY ELSE: HOLD"
        template = StrategyTemplate("momentum", logic)
        sb = SignalBuilder(template, {"threshold": 0.03})
        data = {"momentum_14": [0.01, 0.04, 0.03, 0.05]}
        signals = sb.build(data)
        self.assertEqual(signals, ["HOLD", "BUY", "HOLD", "BUY"])

    def test_backtest_launcher(self):
        logic = "IF momentum_14 > {threshold}: BUY ELSE: HOLD"
        template = StrategyTemplate("momentum", logic)
        sb = SignalBuilder(template, {"threshold": 0.03})
        bl = BacktestLauncher(None)
        data = {"momentum_14": [0.01, 0.04, 0.03, 0.05]}
        metrics = bl.run(sb, data)
        self.assertEqual(metrics["n_buy"], 2)
        self.assertEqual(metrics["n_hold"], 2)
        self.assertEqual(metrics["total"], 4)

    def test_ranker(self):
        ranker = StrategyRanker({"sharpe": 0.7, "drawdown": -0.3})
        metrics = [
            {"sharpe": 1.0, "drawdown": 0.2},
            {"sharpe": 0.5, "drawdown": 0.1},
        ]
        scores = ranker.rank(metrics)
        # score = sharpe*0.7 + drawdown*(-0.3)
        self.assertAlmostEqual(scores[0][1], 1.0 * 0.7 + 0.2 * (-0.3))
        self.assertAlmostEqual(scores[1][1], 0.5 * 0.7 + 0.1 * (-0.3))

    def test_strategy_db(self):
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            db_path = tmp.name
        db = StrategyDatabase(db_path)
        db.save("id1", {"a": 1}, {"score": 10}, 2)
        db.save("id2", {"b": 2}, {"score": 20}, 1)
        db.save("id3", {"c": 3}, {"score": 5}, 3)
        top = db.top_strategies(2)
        db.conn.close()
        os.remove(db_path)
        self.assertEqual(top[0]["id"], "id2")
        self.assertEqual(top[1]["id"], "id1")


if __name__ == "__main__":
    unittest.main()
