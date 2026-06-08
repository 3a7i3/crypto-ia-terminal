"""
RunRepository — persistance SQLite des runs et trades du simulateur CMVK.

Tables :
  runs         — un enregistrement par BacktestEngine.run()
  trades       — trades fermés (schema étendu TradeEvent — Phase B B3)
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_DDL_RUNS = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    strategy_id   TEXT NOT NULL,
    regime        TEXT NOT NULL,
    regime_atr    REAL,
    regime_slope  REAL,
    total_trades  INTEGER,
    final_balance REAL,
    total_pnl     REAL,
    win_rate      REAL,
    max_drawdown  REAL,
    profit_factor REAL,
    n_candles     INTEGER,
    created_at    TEXT NOT NULL
)
"""

# Schema complet TradeEvent (Phase B B3)
_DDL_TRADES = """
CREATE TABLE IF NOT EXISTS trades (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id       TEXT,
    run_id         TEXT NOT NULL,
    strategy_id    TEXT,
    symbol         TEXT,
    side           TEXT,
    entry_price    REAL,
    exit_price     REAL,
    quantity       REAL,
    execution_mode TEXT,
    gross_pnl_usd  REAL,
    fees_usd       REAL,
    slippage_usd   REAL,
    net_pnl_usd    REAL,
    pnl            REAL,
    signal_score   REAL,
    confidence     REAL,
    regime         TEXT,
    opened_at      TEXT,
    closed_at      TEXT,
    hold_seconds   REAL,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs (run_id)
)
"""

# Colonnes ajoutees en B3 — migration idempotente pour les DB existantes
_NEW_TRADE_COLS = {
    "trade_id": "TEXT",
    "side": "TEXT",
    "entry_price": "REAL",
    "quantity": "REAL",
    "execution_mode": "TEXT",
    "gross_pnl_usd": "REAL",
    "fees_usd": "REAL",
    "slippage_usd": "REAL",
    "net_pnl_usd": "REAL",
    "signal_score": "REAL",
    "regime": "TEXT",
    "opened_at": "TEXT",
    "closed_at": "TEXT",
    "hold_seconds": "REAL",
}


class RunRepository:
    def __init__(self, db_path: str = "databases/sim_runs.sqlite"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_DDL_RUNS)
            conn.execute(_DDL_TRADES)
            self._migrate_trades_schema(conn)
            conn.commit()

    def _migrate_trades_schema(self, conn: sqlite3.Connection) -> None:
        """Ajoute les colonnes TradeEvent manquantes (migration idempotente)."""
        existing = {
            row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()
        }
        for col, typ in _NEW_TRADE_COLS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {typ}")

    # ------------------------------------------------------------------ #
    # Write                                                                 #
    # ------------------------------------------------------------------ #

    def save_run(self, report: dict, n_candles: int = 0) -> None:
        """Persiste un rapport BacktestEngine.run() + ses trades fermes (TradeEvent)."""
        now = _now()
        trades = report.get("trades", [])
        gains = sum(t.net_pnl_usd for t in trades if t.net_pnl_usd > 0)
        losses = abs(sum(t.net_pnl_usd for t in trades if t.net_pnl_usd < 0))
        pf = gains / losses if losses > 0 else (float("inf") if gains > 0 else 0.0)

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO runs
                       (run_id, strategy_id, regime, regime_atr, regime_slope,
                        total_trades, final_balance, total_pnl, win_rate,
                        max_drawdown, profit_factor, n_candles, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        report["run_id"],
                        report.get("strategy_id", "unknown"),
                        report.get("regime", "sideways"),
                        report.get("regime_atr", 0.0),
                        report.get("regime_slope", 0.0),
                        report.get("total_trades", 0),
                        report.get("final_balance", 0.0),
                        report.get("total_pnl", 0.0),
                        report.get("win_rate", 0.0),
                        report.get("max_drawdown", 0.0),
                        pf,
                        n_candles,
                        now,
                    ),
                )
                for t in trades:
                    regime_val = (
                        t.regime.value if hasattr(t.regime, "value") else str(t.regime)
                    )
                    conn.execute(
                        """INSERT INTO trades
                           (trade_id, run_id, strategy_id, symbol, side,
                            entry_price, exit_price, quantity, execution_mode,
                            gross_pnl_usd, fees_usd, slippage_usd, net_pnl_usd,
                            pnl, signal_score, regime, opened_at, closed_at,
                            hold_seconds, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            t.trade_id,
                            report["run_id"],
                            report.get("strategy_id"),
                            t.symbol,
                            t.side,
                            t.entry_price,
                            t.exit_price,
                            t.quantity,
                            t.execution_mode,
                            t.gross_pnl_usd,
                            t.fees_usd,
                            t.slippage_usd,
                            t.net_pnl_usd,
                            t.net_pnl_usd,
                            t.signal_score,
                            regime_val,
                            t.opened_at.isoformat(),
                            t.closed_at.isoformat(),
                            t.hold_seconds,
                            now,
                        ),
                    )
                conn.commit()

    # ------------------------------------------------------------------ #
    # Read                                                                  #
    # ------------------------------------------------------------------ #

    def last_runs(self, n: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in rows]

    def runs_by_regime(self, regime: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE regime = ? ORDER BY created_at DESC",
                (regime,),
            ).fetchall()
        return [dict(r) for r in rows]

    def runs_by_strategy(self, strategy_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE strategy_id = ? ORDER BY created_at DESC",
                (strategy_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def aggregate(self, runs: list[dict] | None = None) -> dict:
        """Stats globales ou sur une liste filtree."""
        if runs is None:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM runs").fetchall()
            runs = [dict(r) for r in rows]

        if not runs:
            return {
                "n_runs": 0,
                "avg_pnl": 0.0,
                "avg_win_rate": 0.0,
                "avg_drawdown": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
            }

        n = len(runs)
        gains = sum(r["total_pnl"] for r in runs if r["total_pnl"] > 0)
        losses = abs(sum(r["total_pnl"] for r in runs if r["total_pnl"] < 0))
        return {
            "n_runs": n,
            "avg_pnl": round(sum(r["total_pnl"] for r in runs) / n, 2),
            "avg_win_rate": round(sum(r["win_rate"] for r in runs) / n, 3),
            "avg_drawdown": round(sum(r["max_drawdown"] for r in runs) / n, 4),
            "profit_factor": (
                round(gains / losses, 2)
                if losses > 0
                else (float("inf") if gains > 0 else 0.0)
            ),
            "total_trades": sum(r["total_trades"] for r in runs),
        }

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    def regime_distribution(self) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT regime, COUNT(*) as n FROM runs GROUP BY regime"
            ).fetchall()
        return {r["regime"]: r["n"] for r in rows}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
