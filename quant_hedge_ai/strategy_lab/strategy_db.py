# strategy_db.py

import sqlite3


class StrategyDatabase:
    def __init__(self, db_path="strategy_lab.sqlite"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS strategies (
            id TEXT PRIMARY KEY,
            params TEXT,
            metrics TEXT,
            rank REAL
        )"""
        )
        self.conn.commit()

    def save(self, strategy_id, params, metrics, rank):
        """
        Sauvegarde la stratégie et ses résultats en base sqlite.
        """
        import json

        self.conn.execute(
            "REPLACE INTO strategies (id, params, metrics, rank) VALUES (?, ?, ?, ?)",
            (strategy_id, json.dumps(params), json.dumps(metrics), rank),
        )
        self.conn.commit()

    def top_strategies(self, n=50):
        """
        Retourne les n meilleures stratégies selon le rang (plus petit = meilleur).
        """
        import json

        cur = self.conn.execute(
            "SELECT id, params, metrics, rank FROM strategies ORDER BY rank ASC LIMIT ?",
            (n,),
        )
        results = []
        for row in cur:
            results.append(
                {
                    "id": row[0],
                    "params": json.loads(row[1]),
                    "metrics": json.loads(row[2]),
                    "rank": row[3],
                }
            )
        return results
