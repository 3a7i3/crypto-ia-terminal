"""
db.py — Persistance SQLite pour orderbook snapshots et trades.

Base dédiée : databases/orderbook_flow.sqlite (ADR-0018, invariant 2).
Jamais market_data.sqlite. Lecture seule pour le dashboard.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from observability.json_logger import get_logger

_log = get_logger("orderbook_observer.db")
_DEFAULT_PATH = "databases/orderbook_flow.sqlite"


class OrderbookDatabase:
    """
    Persiste les trades et snapshots orderbook dans SQLite.

    Thread-safe via lock interne. Rotation automatique des données
    au-delà de retention_days.
    """

    def __init__(
        self,
        db_path: str = _DEFAULT_PATH,
        retention_days: int = 7,
    ) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._retention_days = retention_days
        self._lock = threading.Lock()
        self._save_count = 0
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts          TEXT    NOT NULL,
                    symbol      TEXT    NOT NULL,
                    exchange    TEXT    NOT NULL DEFAULT 'mexc',
                    price       REAL    NOT NULL,
                    qty         REAL    NOT NULL,
                    side        TEXT    NOT NULL,
                    trade_id    TEXT,
                    inserted_at REAL    NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orderbook_snapshots (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts          TEXT    NOT NULL,
                    symbol      TEXT    NOT NULL,
                    exchange    TEXT    NOT NULL DEFAULT 'mexc',
                    depth       INTEGER NOT NULL,
                    bids_json   TEXT    NOT NULL,
                    asks_json   TEXT    NOT NULL,
                    spread      REAL,
                    mid_price   REAL,
                    imbalance   REAL,
                    inserted_at REAL    NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS liquidity_levels (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts          TEXT    NOT NULL,
                    symbol      TEXT    NOT NULL,
                    exchange    TEXT    NOT NULL DEFAULT 'mexc',
                    price_level REAL    NOT NULL,
                    side        TEXT    NOT NULL,
                    total_qty   REAL    NOT NULL,
                    is_wall     INTEGER NOT NULL DEFAULT 0,
                    inserted_at REAL    NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts "
                "ON trades(symbol, ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ob_snap_symbol_ts "
                "ON orderbook_snapshots(symbol, ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_liq_symbol_ts "
                "ON liquidity_levels(symbol, ts)"
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def save_trades(self, trades: list[dict[str, Any]]) -> int:
        """Insère un batch de trades. Retourne le nombre inséré."""
        if not trades:
            return 0
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO trades (ts, symbol, exchange, price, qty, side, trade_id, inserted_at)
                    VALUES (:ts, :symbol, :exchange, :price, :qty, :side, :trade_id, :inserted_at)
                    """,
                    [{**t, "inserted_at": now} for t in trades],
                )
                conn.commit()
                count = len(trades)
        self._save_count += count
        return count

    def save_orderbook_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Insère un snapshot orderbook."""
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO orderbook_snapshots
                        (ts, symbol, exchange, depth, bids_json, asks_json,
                         spread, mid_price, imbalance, inserted_at)
                    VALUES (:ts, :symbol, :exchange, :depth, :bids_json, :asks_json,
                            :spread, :mid_price, :imbalance, :inserted_at)
                    """,
                    {**snapshot, "inserted_at": now},
                )
                conn.commit()

    def query_trades(
        self,
        symbol: str,
        since: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Lit les trades récents pour un symbole (lecture seule dashboard)."""
        with self._lock:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            if since:
                rows = conn.execute(
                    "SELECT * FROM trades WHERE symbol = ? AND ts >= ? "
                    "ORDER BY ts DESC LIMIT ?",
                    (symbol, since, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trades WHERE symbol = ? "
                    "ORDER BY ts DESC LIMIT ?",
                    (symbol, limit),
                ).fetchall()
            conn.close()
        return [dict(r) for r in rows]

    def query_latest_orderbook(
        self, symbol: str, exchange: str = "mexc"
    ) -> dict[str, Any] | None:
        """Retourne le dernier snapshot orderbook pour un symbole."""
        with self._lock:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM orderbook_snapshots "
                "WHERE symbol = ? AND exchange = ? ORDER BY ts DESC LIMIT 1",
                (symbol, exchange),
            ).fetchone()
            conn.close()
        return dict(row) if row else None

    def query_liquidity_levels(
        self, symbol: str, exchange: str = "mexc"
    ) -> list[dict[str, Any]]:
        """Retourne les niveaux de liquidité actuels pour un symbole."""
        with self._lock:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM liquidity_levels "
                "WHERE symbol = ? AND exchange = ? ORDER BY ts DESC LIMIT 40",
                (symbol, exchange),
            ).fetchall()
            conn.close()
        return [dict(r) for r in rows]

    def purge_old_data(self) -> int:
        """Supprime les données plus anciennes que retention_days."""
        cutoff = time.time() - self._retention_days * 86400
        total = 0
        with self._lock:
            with self._connect() as conn:
                for table in ("trades", "orderbook_snapshots", "liquidity_levels"):
                    cur = conn.execute(
                        f"DELETE FROM {table} WHERE inserted_at < ?",  # noqa: S608
                        (cutoff,),
                    )
                    total += cur.rowcount
                conn.commit()
        if total:
            _log.info("[OrderbookDB] purge: %d lignes supprimees (> %dj)", total, self._retention_days)
        return total

    @property
    def stats(self) -> dict[str, Any]:
        """Statistiques résumées de la base."""
        with self._lock:
            conn = self._connect()
            counts = {}
            for table in ("trades", "orderbook_snapshots", "liquidity_levels"):
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
                counts[table] = row[0] if row else 0
            conn.close()
        return {
            "db_path": str(self._path),
            "retention_days": self._retention_days,
            "total_saves": self._save_count,
            **counts,
        }
