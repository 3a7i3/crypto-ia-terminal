"""
Test d'intégration complet du pipeline strategy_lab.
"""

import unittest

from quant_hedge_ai.strategy_lab.backtest_launcher import BacktestLauncher
from quant_hedge_ai.strategy_lab.generator import StrategyGenerator
from quant_hedge_ai.strategy_lab.parameter_space import ParameterSpace
from quant_hedge_ai.strategy_lab.signal_builder import SignalBuilder
from quant_hedge_ai.strategy_lab.strategy_db import StrategyDatabase
from quant_hedge_ai.strategy_lab.templates import StrategyTemplate


class TestStrategyLabIntegration(unittest.TestCase):
    def test_database_persistence(self):
        import os
        import tempfile

        # Utilise une base sqlite temporaire
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            db_path = tmp.name
        db = StrategyDatabase(db_path)
        params = {"threshold": 0.05}
        metrics = {"n_buy": 3, "n_hold": 1, "total": 4}
        db.save("strat_test", params, metrics, -2)
        # Recharge la base et vérifie la persistance
        db2 = StrategyDatabase(db_path)
        top = db2.top_strategies(1)
        db.conn.close()
        db2.conn.close()
        os.remove(db_path)
        self.assertEqual(top[0]["id"], "strat_test")
        self.assertEqual(top[0]["params"], params)
        self.assertEqual(top[0]["metrics"], metrics)

    def test_pipeline_performance(self):
        import time

        features = [f"momentum_{i}" for i in range(20)]
        templates = ["momentum"]
        generator = StrategyGenerator(features, templates)
        generator.generate()
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

    def test_full_pipeline(self):
        # Génération
        features = ["momentum_14"]
        templates = ["momentum"]
        generator = StrategyGenerator(features, templates)
        combos = generator.generate()
        self.assertEqual(combos, [("momentum_14", "momentum")])

        # Paramètres
        param_space = ParameterSpace("momentum")
        grid = param_space.get_grid()
        self.assertTrue(len(grid) > 0)

        # Template
        logic = "IF momentum_14 > {threshold}: BUY ELSE: HOLD"
        template = StrategyTemplate("momentum", logic)

        # Signal + Backtest + DB
        db = StrategyDatabase()
        for params in grid:
            sb = SignalBuilder(template, params)
            data = {"momentum_14": [0.01, 0.04, 0.03, 0.05]}
            bl = BacktestLauncher(None)
            metrics = bl.run(sb, data)
            # Score = n_buy - n_hold (exemple)
            score = metrics["n_buy"] - metrics["n_hold"]
            db.save(
                f"strat_{params['threshold']}", params, metrics, -score
            )  # rang = -score (plus grand score = meilleur)

        # Ranking
        top = db.top_strategies(1)
        self.assertEqual(top[0]["metrics"]["n_buy"], 3)
        self.assertEqual(top[0]["params"]["threshold"], 0.01)


if __name__ == "__main__":
    unittest.main()
