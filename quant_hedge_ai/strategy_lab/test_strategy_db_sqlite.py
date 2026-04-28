"""
Test de la persistance sqlite dans StrategyDatabase.
"""

import os
import unittest

from quant_hedge_ai.strategy_lab.strategy_db import StrategyDatabase


def cleanup_db(path):
    if os.path.exists(path):
        os.remove(path)


class TestStrategyDatabaseSqlite(unittest.TestCase):
    DB_PATH = "test_strategy_lab.sqlite"

    def setUp(self):
        cleanup_db(self.DB_PATH)
        self.db = StrategyDatabase(self.DB_PATH)

    def tearDown(self):
        self.db.conn.close()
        cleanup_db(self.DB_PATH)

    def test_save_and_top(self):
        self.db.save("id1", {"a": 1}, {"score": 10}, 2)
        self.db.save("id2", {"b": 2}, {"score": 20}, 1)
        self.db.save("id3", {"c": 3}, {"score": 5}, 3)
        top = self.db.top_strategies(2)
        self.assertEqual(top[0]["id"], "id2")
        self.assertEqual(top[1]["id"], "id1")
        # Persistance réelle : on relit avec une nouvelle instance
        db2 = StrategyDatabase(self.DB_PATH)
        top2 = db2.top_strategies(2)
        self.assertEqual(top2[0]["id"], "id2")
        self.assertEqual(top2[1]["id"], "id1")
        db2.conn.close()


if __name__ == "__main__":
    unittest.main()
