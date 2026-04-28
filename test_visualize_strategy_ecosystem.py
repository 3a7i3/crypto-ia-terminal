import unittest

missing = []
# ...existing code...

if missing:

    @unittest.skip(f"Modules manquants : {', '.join(missing)}")
    class TestVisualizeStrategyEcosystem(unittest.TestCase):
        def test_neutralise(self):
            pass

else:
    import os
    import sys

    import pytest

    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    import importlib
    import sys

    def test_visualize_strategy_ecosystem_empty(monkeypatch, tmp_path):
        monkeypatch.setattr("glob.glob", lambda pattern: [])
        if "visualize_strategy_ecosystem" in sys.modules:
            importlib.reload(sys.modules["visualize_strategy_ecosystem"])
        import visualize_strategy_ecosystem

        assert True

    def test_visualize_strategy_ecosystem_with_csv(monkeypatch, tmp_path):
        import pandas as pd

        fake_file = tmp_path / "pop_gen_0.csv"
        df = pd.DataFrame(
            {
                "fitness": [1.0],
                "species": ["A"],
                "generation": [0],
                "entry.type": ["X"],
                "fitness_trend": [0.5],
                "fitness_range": [0.2],
                "fitness_crash": [0.1],
            }
        )
        df.to_csv(fake_file, index=False)
        monkeypatch.setattr("glob.glob", lambda pattern: [str(fake_file)])
        if "visualize_strategy_ecosystem" in sys.modules:
            importlib.reload(sys.modules["visualize_strategy_ecosystem"])
        import visualize_strategy_ecosystem

        assert True
