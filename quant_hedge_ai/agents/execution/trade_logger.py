"""
TradeLogger — SQLite audit log for all orders.

Logs every order that passes through ExecutionEngine, including:
  - paper orders
  - live orders (successful and failed)
  - orders rejected by safety guards

Provides session PnL query and recent-trades retrieval.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
import time
from pathlib import Path

from observability.json_logger import get_logger

_log = get_logger("trade_logger")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL    NOT NULL,
    symbol    TEXT    NOT NULL,
    action    TEXT    NOT NULL,
    size      REAL    NOT NULL,
    price     REAL,
    notional  REAL,
    pnl       REAL,
    mode      TEXT    NOT NULL,
    status    TEXT    NOT NULL,
    order_id  TEXT,
    error     TEXT,
    raw_json  TEXT
)
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades (ts)
"""


class TradeLogger:
    """Thread-safe SQLite trade audit log."""

    def __init__(self, db_path: str = "databases/trade_log.sqlite") -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(path)
        self._lock = threading.Lock()
        self._init_db()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)
            conn.execute(_CREATE_INDEX)

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path, timeout=10)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Write ──────────────────────────────────────────────────────────────────

    def log(self, order_result: dict, status: str = "ok") -> None:
        """
        Persist one order result.

        `order_result` should contain at minimum: symbol, action, size, mode.
        Additional fields (price, notional, pnl, id, error) are extracted if present.
        """
        ts = time.time()
        row = (
            ts,
            order_result.get("symbol", ""),
            order_result.get("action", "").upper(),
            float(order_result.get("size", 0.0)),
            order_result.get("price") or order_result.get("average"),
            order_result.get("notional") or order_result.get("cost"),
            order_result.get("pnl"),
            order_result.get("mode", "unknown"),
            status,
            str(order_result.get("id", "") or ""),
            order_result.get("error"),
            json.dumps(order_result, default=str),
        )
        try:
            with self._lock:
                with self._connect() as conn:
                    conn.execute(
                        """INSERT INTO trades
                           (ts, symbol, action, size, price, notional, pnl,
                            mode, status, order_id, error, raw_json)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        row,
                    )
        except Exception as exc:
            _log.error("TRADE_LOG_FAILED", error=str(exc))

    def log_rejected(self, symbol: str, action: str, size: float, reason: str) -> None:
        """Log an order that was rejected before reaching the exchange."""
        self.log(
            {
                "symbol": symbol,
                "action": action,
                "size": size,
                "mode": "rejected",
                "error": reason,
            },
            status="rejected",
        )

    # ── Read ───────────────────────────────────────────────────────────────────

    def recent_trades(self, n: int = 50) -> list[dict]:
        """Return the N most recent trades as dicts (newest first)."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT ts, symbol, action, size, price, notional, pnl,
                              mode, status, order_id, error
                       FROM trades
                       ORDER BY ts DESC
                       LIMIT ?""",
                    (n,),
                ).fetchall()
            cols = [
                "ts",
                "symbol",
                "action",
                "size",
                "price",
                "notional",
                "pnl",
                "mode",
                "status",
                "order_id",
                "error",
            ]
            return [dict(zip(cols, r)) for r in rows]
        except Exception as exc:
            _log.error("TRADE_READ_FAILED", error=str(exc))
            return []

    def session_pnl(self, since_ts: float | None = None) -> float:
        """Sum of PnL for all trades since `since_ts` (epoch seconds). Defaults to last 24h."""
        if since_ts is None:
            since_ts = time.time() - 86_400
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COALESCE(SUM(pnl), 0.0) FROM trades WHERE ts >= ?",
                    (since_ts,),
                ).fetchone()
            return float(row[0]) if row else 0.0
        except Exception as exc:
            _log.error("SESSION_PNL_FAILED", error=str(exc))
            return 0.0

    def stats(self) -> dict:
        """Aggregate statistics across all logged trades."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """SELECT COUNT(*), COALESCE(SUM(pnl),0),
                              COALESCE(AVG(pnl),0),
                              SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END),
                              SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END)
                       FROM trades"""
                ).fetchone()
            total, pnl_sum, pnl_avg, wins, rejected = row
            win_rate = (wins / total) if total else 0.0
            return {
                "total_trades": total,
                "pnl_sum": round(pnl_sum or 0.0, 4),
                "pnl_avg": round(pnl_avg or 0.0, 6),
                "win_rate": round(win_rate, 4),
                "rejected": rejected or 0,
            }
        except Exception as exc:
            _log.error("TRADE_STATS_FAILED", error=str(exc))
            return {}
