import unittest

missing = []
try:
    import pandas
except ImportError:
    missing.append("pandas")
try:
    import pytest
except ImportError:
    missing.append("pytest")

if missing:

    @unittest.skip(f"Modules manquants : {', '.join(missing)}")
    class TestVisualizeStrategyEcosystemAllGens(unittest.TestCase):
        def test_neutralise(self):
            pass

else:
    import os
    import sys

    import pytest

    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    import importlib
    import sys

    def test_visualize_strategy_ecosystem_all_gens_empty(monkeypatch, tmp_path):
        monkeypatch.setattr("glob.glob", lambda pattern: [])
        if "visualize_strategy_ecosystem_all_gens" in sys.modules:
            importlib.reload(sys.modules["visualize_strategy_ecosystem_all_gens"])
        import visualize_strategy_ecosystem_all_gens

        # Vérifie que l'import ne plante pas sans fichiers
        assert True

    def test_visualize_strategy_ecosystem_all_gens_with_csv(monkeypatch, tmp_path):
        import pandas as pd

        fake_file = tmp_path / "pop_gen_0.csv"
        df = pd.DataFrame({"fitness": [1.0], "species": ["A"], "generation": [0]})
        df.to_csv(fake_file, index=False)
        monkeypatch.setattr("glob.glob", lambda pattern: [str(fake_file)])
        if "visualize_strategy_ecosystem_all_gens" in sys.modules:
            importlib.reload(sys.modules["visualize_strategy_ecosystem_all_gens"])
        import visualize_strategy_ecosystem_all_gens

        assert True
