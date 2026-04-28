import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import pandas as pd

from run_strategy_factory import Genome


class TestDataFrameTracking(unittest.TestCase):
    def test_dataframe_contains_tracking_columns(self):
        g = Genome()
        g.fitness = 1.23
        g.genes["entry.type"] = "trend"
        g.parent_ids = ["parent1", "parent2"]
        row = {
            **g.genes,
            "fitness": g.fitness,
            "id": g.id,
            "environment": "trend",
            "species": g.genes["entry.type"],
            "world": "trend",
            "parent_ids": ",".join(g.parent_ids),
        }
        df = pd.DataFrame([row])
        for col in ["id", "species", "parent_ids"]:
            self.assertIn(col, df.columns)
        self.assertEqual(df.loc[0, "id"], g.id)
        self.assertEqual(df.loc[0, "species"], "trend")
        self.assertEqual(df.loc[0, "parent_ids"], "parent1,parent2")


if __name__ == "__main__":
    unittest.main()
