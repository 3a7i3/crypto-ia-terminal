"""
Test de performance du pipeline strategy_lab.
"""

import time
import unittest

from quant_hedge_ai.strategy_lab.backtest_launcher import BacktestLauncher
from quant_hedge_ai.strategy_lab.generator import StrategyGenerator
from quant_hedge_ai.strategy_lab.parameter_space import ParameterSpace
from quant_hedge_ai.strategy_lab.signal_builder import SignalBuilder
from quant_hedge_ai.strategy_lab.strategy_db import StrategyDatabase
from quant_hedge_ai.strategy_lab.templates import StrategyTemplate


class TestStrategyLabPerformance(unittest.TestCase):
    def test_pipeline_speed(self):
        features = [f"momentum_{i}" for i in range(30)]
        templates = ["momentum"]
        generator = StrategyGenerator(features, templates)
        combos = generator.generate()
        param_space = ParameterSpace("momentum")
        grid = param_space.get_grid()
        logic = "IF momentum_0 > {threshold}: BUY ELSE: HOLD"
        template = StrategyTemplate("momentum", logic)
        db = StrategyDatabase(":memory:")
        data = {"momentum_0": [0.01, 0.04, 0.03, 0.05] * 1000}
        start = time.time()
        for params in grid:
            sb = SignalBuilder(template, params)
            bl = BacktestLauncher(None)
            metrics = bl.run(sb, data)
            score = metrics["n_buy"] - metrics["n_hold"]
            db.save(f"strat_{params['threshold']}", params, metrics, -score)
        elapsed = time.time() - start
        # Le pipeline doit s'exécuter en moins de 2 secondes (ajuster selon la machine)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
