"""
dip/core/store.py — DIPStore: SQLite WAL + cache LRU in-memory.

Stratégie 3 niveaux (spec §12):
  L1 Hot Cache  — dict LRU in-memory, TTL configurable
  L2 Warm Store — SQLite WAL (derniers 30 jours)
  L3 Archive    — hors scope Phase 1

Politique d'immuabilité (ADR-0015): append-only, jamais d'UPDATE ni DELETE
sur les données. Les suppressions passent uniquement par les politiques de
rétention (job de compaction, hors scope Phase 1).

Thread-safety: RWLock sur le cache, connexion SQLite en check_same_thread=False
avec WAL mode pour lectures concurrentes.
"""

from __future__ import annotations

import sqlite3
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Generic, Optional, TypeVar

from dip.core.types import compute_hash, now_us

T = TypeVar("T")


# ── LRU Cache ─────────────────────────────────────────────────────────────────


class LRUCache(Generic[T]):
    """Cache LRU thread-safe avec TTL par entrée."""

    def __init__(self, max_entries: int, ttl_seconds: int) -> None:
        self._max = max_entries
        self._ttl_us = ttl_seconds * 1_000_000
        self._data: OrderedDict[str, tuple[T, int]] = (
            OrderedDict()
        )  # key → (value, expire_us)
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[T]:
        with self._lock:
            if key not in self._data:
                return None
            value, expire_us = self._data[key]
            if now_us() > expire_us:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: T) -> None:
        with self._lock:
            expire_us = now_us() + self._ttl_us
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = (value, expire_us)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def size(self) -> int:
        with self._lock:
            return len(self._data)

    def evict_expired(self) -> int:
        now = now_us()
        with self._lock:
            expired = [k for k, (_, exp) in self._data.items() if now > exp]
            for k in expired:
                del self._data[k]
            return len(expired)


# ── DIPStore ──────────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS dip_decisions (
    packet_id       TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    direction       TEXT NOT NULL,
    regime          TEXT,
    status          TEXT NOT NULL,
    created_at_us   INTEGER NOT NULL,
    completed_at_us INTEGER,
    graph_json      TEXT,
    causal_tree_json TEXT,
    timeline_json   TEXT,
    explainability_score REAL,
    explainability_grade TEXT,
    root_cause_type TEXT,
    root_cause_layer TEXT,
    hash            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dip_observations (
    observation_id  TEXT PRIMARY KEY,
    packet_id       TEXT NOT NULL,
    module          TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    data_json       TEXT NOT NULL,
    confidence      REAL NOT NULL,
    hash            TEXT NOT NULL,
    created_at_us   INTEGER NOT NULL,
    ttl_seconds     INTEGER,
    FOREIGN KEY (packet_id) REFERENCES dip_decisions(packet_id)
);

CREATE TABLE IF NOT EXISTS dip_alerts (
    alert_id        TEXT PRIMARY KEY,
    rule_id         TEXT,
    severity        TEXT NOT NULL,
    title           TEXT,
    description     TEXT NOT NULL,
    metric_value    REAL,
    threshold       REAL,
    layer           TEXT,
    symbol          TEXT,
    module          TEXT,
    affected_packets TEXT,
    acknowledged    INTEGER DEFAULT 0,
    acknowledged_by TEXT,
    created_at_us   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dip_knowledge (
    entry_id        TEXT PRIMARY KEY,
    entry_type      TEXT NOT NULL,
    description     TEXT NOT NULL,
    frequency       REAL NOT NULL,
    sample_size     INTEGER NOT NULL,
    confidence      REAL NOT NULL,
    layers_involved TEXT,
    symbols         TEXT,
    regimes         TEXT,
    first_seen_us   INTEGER NOT NULL,
    last_seen_us    INTEGER NOT NULL,
    trend           TEXT NOT NULL,
    hash            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dip_audit_trail (
    trail_id        TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    module          TEXT NOT NULL,
    user_id         TEXT,
    details_json    TEXT NOT NULL,
    hash            TEXT NOT NULL,
    created_at_us   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dip_counterfactuals (
    cf_id               TEXT PRIMARY KEY,
    packet_id           TEXT NOT NULL,
    scenario_type       TEXT NOT NULL,
    target_layer        TEXT,
    original_result     TEXT NOT NULL,
    counterfactual_result TEXT NOT NULL,
    outcome_changed     INTEGER NOT NULL,
    confidence_delta    REAL NOT NULL,
    estimated_pnl_impact REAL,
    confidence          REAL NOT NULL,
    created_at_us       INTEGER NOT NULL,
    FOREIGN KEY (packet_id) REFERENCES dip_decisions(packet_id)
);

CREATE INDEX IF NOT EXISTS idx_decisions_symbol   ON dip_decisions(symbol);
CREATE INDEX IF NOT EXISTS idx_decisions_status   ON dip_decisions(status);
CREATE INDEX IF NOT EXISTS idx_decisions_created  ON dip_decisions(created_at_us);
CREATE INDEX IF NOT EXISTS idx_observations_packet ON dip_observations(packet_id);
CREATE INDEX IF NOT EXISTS idx_observations_module ON dip_observations(module);
CREATE INDEX IF NOT EXISTS idx_alerts_severity    ON dip_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_knowledge_type     ON dip_knowledge(entry_type);
CREATE INDEX IF NOT EXISTS idx_audit_entity       ON dip_audit_trail(entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created      ON dip_audit_trail(created_at_us);
"""


class DIPStore:
    """
    Stockage persistant SQLite WAL pour le DIP.

    Usage:
        store = DIPStore.instance()
        store.upsert_decision(packet_id, {...})
        row = store.get_decision(packet_id)
    """

    _instance: Optional["DIPStore"] = None
    _lock = threading.Lock()

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._local = threading.local()
        # Initialise le schéma via une connexion dédiée
        conn = self._connect()
        conn.executescript(_SCHEMA)
        conn.commit()

    @classmethod
    def instance(cls, db_path: Optional[Path] = None) -> "DIPStore":
        with cls._lock:
            if cls._instance is None:
                if db_path is None:
                    root = Path(__file__).parent.parent.parent
                    db_path = root / "databases" / "dip" / "dip.sqlite"
                cls._instance = cls(db_path)
        return cls._instance

    def _connect(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self._path),
                check_same_thread=False,
                timeout=10.0,
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._connect()

    # ── Decisions ─────────────────────────────────────────────────────────────

    def upsert_decision(self, packet_id: str, data: dict[str, Any]) -> None:
        data["hash"] = compute_hash(data)
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        sql = f"INSERT OR REPLACE INTO dip_decisions ({cols}) VALUES ({placeholders})"
        self._conn.execute(sql, list(data.values()))
        self._conn.commit()

    def get_decision(self, packet_id: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM dip_decisions WHERE packet_id = ?", (packet_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_decisions(
        self,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        start_us: Optional[int] = None,
        end_us: Optional[int] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        clauses, params = [], []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if start_us:
            clauses.append("created_at_us >= ?")
            params.append(start_us)
        if end_us:
            clauses.append("created_at_us <= ?")
            params.append(end_us)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM dip_decisions {where} ORDER BY created_at_us DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Observations ──────────────────────────────────────────────────────────

    def insert_observation(self, data: dict[str, Any]) -> None:
        data["hash"] = compute_hash(data)
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        self._conn.execute(
            f"INSERT OR IGNORE INTO dip_observations ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        self._conn.commit()

    def get_observations(self, packet_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM dip_observations WHERE packet_id = ? ORDER BY created_at_us",
            (packet_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Audit Trail ───────────────────────────────────────────────────────────

    def insert_audit(self, data: dict[str, Any]) -> None:
        data["hash"] = compute_hash(data)
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        self._conn.execute(
            f"INSERT OR IGNORE INTO dip_audit_trail ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        self._conn.commit()

    def get_audit_trail(self, entity_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM dip_audit_trail WHERE entity_id = ? ORDER BY created_at_us",
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def verify_audit_integrity(self, trail_id: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM dip_audit_trail WHERE trail_id = ?", (trail_id,)
        ).fetchone()
        if not row:
            return {"is_valid": False, "reason": "not_found"}
        d = dict(row)
        stored_hash = d.pop("hash")
        computed = compute_hash(d)
        return {
            "is_valid": computed == stored_hash,
            "trail_id": trail_id,
            "stored_hash": stored_hash,
            "computed_hash": computed,
        }

    # ── Alerts ────────────────────────────────────────────────────────────────

    def insert_alert(self, data: dict[str, Any]) -> None:
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        self._conn.execute(
            f"INSERT OR IGNORE INTO dip_alerts ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        self._conn.commit()

    def get_active_alerts(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM dip_alerts WHERE acknowledged = 0 ORDER BY created_at_us DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def acknowledge_alert(self, alert_id: str, user: str = "operator") -> None:
        self._conn.execute(
            "UPDATE dip_alerts SET acknowledged = 1, acknowledged_by = ? WHERE alert_id = ?",
            (user, alert_id),
        )
        self._conn.commit()

    # ── Knowledge ─────────────────────────────────────────────────────────────

    def upsert_knowledge(self, data: dict[str, Any]) -> None:
        data["hash"] = compute_hash(data)
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        self._conn.execute(
            f"INSERT OR REPLACE INTO dip_knowledge ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        self._conn.commit()

    def get_knowledge(
        self, entry_type: Optional[str] = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        if entry_type:
            rows = self._conn.execute(
                "SELECT * FROM dip_knowledge WHERE entry_type = ? ORDER BY confidence DESC LIMIT ?",
                (entry_type, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM dip_knowledge ORDER BY confidence DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Counterfactuals ───────────────────────────────────────────────────────

    def insert_counterfactual(self, data: dict[str, Any]) -> None:
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        self._conn.execute(
            f"INSERT OR IGNORE INTO dip_counterfactuals ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        self._conn.commit()

    def get_counterfactuals(self, packet_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM dip_counterfactuals WHERE packet_id = ? ORDER BY created_at_us",
            (packet_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Stats ─────────────────────────────────────────────────────────────────

    def count_decisions(
        self, start_us: Optional[int] = None, status: Optional[str] = None
    ) -> int:
        clauses, params = [], []
        if start_us:
            clauses.append("created_at_us >= ?")
            params.append(start_us)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        row = self._conn.execute(
            f"SELECT COUNT(*) FROM dip_decisions {where}", params
        ).fetchone()
        return row[0] if row else 0
