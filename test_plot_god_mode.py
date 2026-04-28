import unittest

missing = []
import matplotlib

matplotlib.use("Agg")
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import pandas as pd

from run_strategy_factory import plot_god_mode


class TestPlotGodMode(unittest.TestCase):
    def test_plot_god_mode_runs(self):
        import run_strategy_factory

        run_strategy_factory.SHOW_PLOTS = False
        # DataFrame minimal simulant une population
        df = pd.DataFrame(
            {
                "exit.tp": [1.0, 2.0],
                "exit.sl": [0.5, 1.0],
                "fitness": [0.8, 1.2],
                "species": ["trend", "mean_reversion"],
                "id": ["abc12345", "def67890"],
                "generation": [0, 0],
                "environment": ["trend", "trend"],
            }
        )
        try:
            plot_god_mode(df)
        except Exception as e:
            self.fail(f"plot_god_mode a levé une exception: {e}")
