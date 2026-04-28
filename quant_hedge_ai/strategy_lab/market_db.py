"""MarketDatabase — persistance SQLite des bougies OHLCV et snapshots marché."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = "databases/market_data.sqlite"


class MarketDatabase:
    """
    Persiste les bougies OHLCV dans SQLite.

    Chaque cycle appelle save_snapshot(market) où market = scanner.scan().
    Les bougies dupliquées (même symbol + timestamp) sont ignorées (INSERT OR IGNORE).
    Les données > max_age_days sont purgées automatiquement lors des saves.
    """

    def __init__(
        self,
        db_path: str = _DEFAULT_PATH,
        max_age_days: int = 30,
    ) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_age_days = max_age_days
        self._lock = threading.Lock()
        self._latest: dict = {}
        self._save_count = 0
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ohlcv (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT    NOT NULL,
                    timestamp   TEXT    NOT NULL,
                    open        REAL,
                    high        REAL,
                    low         REAL,
                    close       REAL,
                    volume      REAL,
                    source      TEXT    DEFAULT 'unknown',
                    fetched_at  REAL    NOT NULL,
                    UNIQUE(symbol, timestamp)
                )
            """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_ts"
                " ON ohlcv(symbol, timestamp DESC)"
            )
            conn.commit()
        logger.debug("[MarketDatabase] Base initialisée : %s", self._path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._path), timeout=10)

    def save_snapshot(self, market: dict) -> int:
        """Persiste toutes les bougies du snapshot. Retourne nb de nouvelles lignes."""
        self._latest = market
        history: dict[str, list[dict]] = market.get("history", {})
        if not history:
            return 0

        fetched_at = time.time()
        rows = []
        for symbol, candles in history.items():
            for c in candles:
                rows.append(
                    (
                        symbol,
                        c.get("timestamp", ""),
                        c.get("open"),
                        c.get("high"),
                        c.get("low"),
                        c.get("close"),
                        c.get("volume"),
                        c.get("source", "unknown"),
                        fetched_at,
                    )
                )

        if not rows:
            return 0

        inserted = 0
        with self._lock:
            with self._connect() as conn:
                cur = conn.executemany(
                    "INSERT OR IGNORE INTO ohlcv"
                    " (symbol, timestamp, open, high, low, close,"
                    " volume, source, fetched_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
                inserted = cur.rowcount
                conn.commit()

        self._save_count += 1
        if self._save_count % 10 == 0:
            self._purge_old()

        if inserted:
            logger.debug("[MarketDatabase] +%d nouvelles bougies persistées", inserted)
        return inserted

    def get_latest_snapshot(self) -> dict:
        """Retourne le dernier snapshot en mémoire (non persisté)."""
        return self._latest

    def get_history(self, symbol: str, limit: int = 200) -> list[dict]:
        """Récupère les N dernières bougies pour un symbole depuis SQLite."""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT symbol, timestamp, open, high, low, close, volume, source
                    FROM ohlcv
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (symbol, limit),
                ).fetchall()

        return [
            {
                "symbol": r[0],
                "timestamp": r[1],
                "open": r[2],
                "high": r[3],
                "low": r[4],
                "close": r[5],
                "volume": r[6],
                "source": r[7],
            }
            for r in reversed(rows)
        ]

    def get_stats(self) -> dict:
        """Statistiques sur les données stockées."""
        with self._lock:
            with self._connect() as conn:
                total = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
                symbols = conn.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM ohlcv"
                ).fetchone()[0]
                sources = dict(
                    conn.execute(
                        "SELECT source, COUNT(*) FROM ohlcv GROUP BY source"
                    ).fetchall()
                )
                oldest = conn.execute("SELECT MIN(timestamp) FROM ohlcv").fetchone()[0]
                newest = conn.execute("SELECT MAX(timestamp) FROM ohlcv").fetchone()[0]

        real = sources.get("ccxt_live", 0)
        synth = sources.get("synthetic", 0)
        return {
            "total_candles": total,
            "symbols": symbols,
            "sources": sources,
            "real_ratio": round(real / total, 4) if total else 0.0,
            "synthetic_ratio": round(synth / total, 4) if total else 0.0,
            "oldest": oldest,
            "newest": newest,
        }

    def _purge_old(self) -> None:
        """Supprime les bougies plus vieilles que max_age_days."""
        if self._max_age_days <= 0:
            return
        cutoff_ts = time.time() - self._max_age_days * 86400
        with self._lock:
            with self._connect() as conn:
                deleted = conn.execute(
                    "DELETE FROM ohlcv WHERE fetched_at < ?", (cutoff_ts,)
                ).rowcount
                conn.commit()
        if deleted:
            logger.info(
                "[MarketDatabase] Purge : %d bougies > %dd supprimées",
                deleted,
                self._max_age_days,
            )
