"""Private, bounded local SQLite journal. No implicit create, no service hooks.

Only explicitly named j01-lab-* directories are admitted. The directory and
files must belong to the caller and be inaccessible to group/other users.
This reduces accidents; it is NOT a sandbox against the OS account itself.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sentinel_activity.canonical import (
    LedgerError, canonical_bytes, digest, format_utc, parse_utc, pure_int, require, strict_loads,
)
from sentinel_activity.contracts import QUEST_TYPES, candidate_from, event_hash, identifier, validate_candidate, validate_recorded
from sentinel_activity.policy import admit, validate_policy

STORAGE_VERSION = "j01-storage/1"
DB_NAME = "activity.sqlite3"
_SCHEMA = """
CREATE TABLE ledger_meta (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
CREATE TABLE events (
 sequence INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
 producer_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 quest_id TEXT, actor_id TEXT NOT NULL, correlation_id TEXT, recorded_at_utc TEXT NOT NULL,
 body TEXT NOT NULL
);
CREATE INDEX by_quest ON events(quest_id,sequence);
CREATE INDEX by_actor ON events(actor_id,sequence);
CREATE INDEX by_correlation ON events(correlation_id,sequence);
CREATE INDEX by_time ON events(recorded_at_utc,sequence);
CREATE TABLE projection (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append only'); END;
CREATE TRIGGER meta_no_update BEFORE UPDATE ON ledger_meta BEGIN SELECT RAISE(ABORT,'immutable meta'); END;
CREATE TRIGGER meta_no_delete BEFORE DELETE ON ledger_meta BEGIN SELECT RAISE(ABORT,'immutable meta'); END;
"""


@dataclass(frozen=True)
class Limits:
    max_events: int = 10_000
    max_bytes: int = 128 * 1024 * 1024
    per_producer: int = 5_000

    def __post_init__(self):
        require(pure_int(self.max_events, 1, 10_000), "BUDGET_EXCEEDED")
        require(pure_int(self.max_bytes, 65_536, 128 * 1024 * 1024), "BUDGET_EXCEEDED")
        require(pure_int(self.per_producer, 1, 5_000), "BUDGET_EXCEEDED")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _project(events: list[dict], policy: dict) -> dict:
    # Quest state support arrives in M3; prior stage fails closed.
    require(not any(e["event_type"] in QUEST_TYPES for e in events), "ILLEGAL_TRANSITION")
    return {"quests": {}, "participations": {}}


def _root(path: Path) -> Path:
    require(path.is_absolute() and ".." not in path.parts, "PATH_DENIED")
    require(path.name.startswith("j01-lab-"), "PATH_DENIED")
    for parent in [*reversed(path.parents), path]:
        require(not parent.is_symlink(), "PATH_DENIED")
    try:
        st = path.stat()
    except OSError as exc:
        raise LedgerError("UNAVAILABLE") from exc
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid() and stat.S_IMODE(st.st_mode) == 0o700,
            "PATH_DENIED")
    return path


def _private_file(path: Path, missing: bool = False) -> None:
    try:
        st = path.lstat()
    except FileNotFoundError:
        require(missing, "UNAVAILABLE")
        return
    require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.geteuid()
            and stat.S_IMODE(st.st_mode) == 0o600, "PATH_DENIED")


@contextmanager
def _translate():
    try:
        yield
    except sqlite3.Error as exc:
        code = getattr(exc, "sqlite_errorcode", None)
        if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise LedgerError("BUSY") from exc
        if code in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}:
            raise LedgerError("CORRUPTED") from exc
        raise LedgerError("UNAVAILABLE") from exc
    except OSError as exc:
        raise LedgerError("UNAVAILABLE") from exc


class ActivityStore:
    """No held connection; every operation owns and closes one transaction."""

    def __init__(self, root: Path, *, clock: Callable[[], datetime] = utc_now):
        self.root = _root(Path(root))
        self.path = self.root / DB_NAME
        self.clock = clock
        _private_file(self.path)
        with _translate(), self._connection(readonly=True) as conn:
            self._metadata(conn)

    @classmethod
    def create(cls, root: Path, policy: dict, *, ledger_id: str,
               limits: Limits = Limits(), clock: Callable[[], datetime] = utc_now):
        root = _root(Path(root))
        policy = validate_policy(policy)
        require(identifier(ledger_id) and ledger_id.startswith("fixture-"))
        path = root / DB_NAME
        # Never adopt stale sidecars or overwrite an existing destination.
        require(not any(root.glob(DB_NAME + "*")), "ALREADY_EXISTS")
        with _translate():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            conn = sqlite3.connect(path, isolation_level=None, timeout=2)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=FULL")
                conn.executescript("BEGIN IMMEDIATE;" + _SCHEMA)
                meta = {"storage_version": STORAGE_VERSION, "ledger_id": ledger_id, "mode": "SIMULATED_ONLY",
                        "policy": policy, "policy_hash": digest(policy),
                        "limits": {"max_events": limits.max_events, "max_bytes": limits.max_bytes,
                                   "per_producer": limits.per_producer}}
                conn.execute("INSERT INTO ledger_meta VALUES(1,?)", (canonical_bytes(meta).decode(),))
                conn.execute("INSERT INTO projection VALUES(1,?)", (canonical_bytes(_project([], policy)).decode(),))
                conn.commit()
            finally:
                conn.close()
        return cls(root, clock=clock)

    @contextmanager
    def _connection(self, readonly: bool = False):
        _root(self.root)
        for suffix in ("", "-wal", "-shm", "-journal"):
            _private_file(Path(str(self.path) + suffix), missing=bool(suffix))
        uri = self.path.as_uri() + ("?mode=ro" if readonly else "?mode=rw")
        conn = sqlite3.connect(uri, uri=True, timeout=2, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=2000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA trusted_schema=OFF")
            if readonly:
                conn.execute("PRAGMA query_only=ON")
            else:
                require(conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal", "CORRUPTED")
                conn.execute("PRAGMA synchronous=FULL")
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _metadata(conn):
        row = conn.execute("SELECT body FROM ledger_meta WHERE id=1").fetchone()
        require(row is not None, "CORRUPTED")
        meta = strict_loads(row[0])
        require(type(meta) is dict and set(meta) == {
            "storage_version", "ledger_id", "mode", "policy", "policy_hash", "limits"}, "CORRUPTED")
        require(meta["storage_version"] == STORAGE_VERSION, "UNKNOWN_VERSION")
        require(identifier(meta["ledger_id"]) and meta["ledger_id"].startswith("fixture-"), "CORRUPTED")
        require(meta["mode"] == "SIMULATED_ONLY", "PROVENANCE_DENIED")
        validate_policy(meta["policy"])
        require(meta["policy_hash"] == digest(meta["policy"]), "CORRUPTED")
        require(type(meta["limits"]) is dict and set(meta["limits"]) == {
            "max_events", "max_bytes", "per_producer"}, "CORRUPTED")
        Limits(**meta["limits"])
        return meta

    def _verified(self, conn):
        meta = self._metadata(conn)
        events = []
        rows = conn.execute("SELECT sequence,event_id,producer_id,request_hash,quest_id,actor_id,"
                            "correlation_id,recorded_at_utc,body FROM events ORDER BY sequence")
        previous = "GENESIS"
        seen = {}
        for row in rows:
            require(len(events) < meta["limits"]["max_events"], "CORRUPTED")
            try:
                event = strict_loads(row[8])
                validate_recorded(event)
                require(canonical_bytes(event).decode() == row[8], "CORRUPTED")
                admit(event, event["producer_id"], meta["policy"])
                expected = (event["sequence"], event["event_id"], event["producer_id"],
                            digest({"candidate": candidate_from(event), "producer_id": event["producer_id"]}),
                            event["quest_id"], event["actor_id"], event["correlation_id"], event["recorded_at_utc"])
                require(tuple(row[:8]) == expected, "CORRUPTED")
                require(event["ledger_id"] == meta["ledger_id"] and event["ingestion_policy_version"] ==
                        meta["policy"]["version"], "CORRUPTED")
                require(event["sequence"] == len(events) + 1 and event["integrity"]["previous_hash"] == previous,
                        "CORRUPTED")
                require(event["event_id"] not in seen, "CORRUPTED")
                self._causation(event, seen)
                if events:
                    require(parse_utc(event["recorded_at_utc"]) >= parse_utc(events[-1]["recorded_at_utc"]),
                            "CORRUPTED")
                previous = event["integrity"]["event_hash"]
                seen[event["event_id"]] = event
                events.append(event)
            except LedgerError as exc:
                if exc.code == "UNKNOWN_VERSION":
                    raise
                raise LedgerError("CORRUPTED") from exc
        try:
            projection = _project(events, meta["policy"])
            row = conn.execute("SELECT body FROM projection WHERE id=1").fetchone()
            require(row is not None and row[0] == canonical_bytes(projection).decode(), "CORRUPTED")
        except LedgerError as exc:
            raise LedgerError("CORRUPTED") from exc
        return meta, events, projection

    @staticmethod
    def _causation(event, seen):
        cause = event["causation_event_id"]
        if cause is not None:
            require(cause in seen, "CAUSATION_INVALID")
            parent = seen[cause]
            require(parent["quest_id"] == event["quest_id"] and parent["correlation_id"] == event["correlation_id"],
                    "CAUSATION_INVALID")
        related = event["payload"].get("related_event_id")
        if related is not None:
            require(related in seen and related == cause, "CAUSATION_INVALID")

    def snapshot(self):
        with _translate(), self._connection(readonly=True) as conn:
            conn.execute("BEGIN")
            return self._verified(conn)

    def append(self, candidate: dict, *, producer_id: str) -> dict:
        event = validate_candidate(candidate)
        require(identifier(producer_id), "ACTOR_DENIED")
        with _translate(), self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                meta, events, _ = self._verified(conn)
                admit(event, producer_id, meta["policy"])
                request_hash = digest({"candidate": event, "producer_id": producer_id})
                existing = next((e for e in events if e["event_id"] == event["event_id"]), None)
                if existing is not None:
                    require(digest({"candidate": candidate_from(existing), "producer_id": existing["producer_id"]})
                            == request_hash, "EVENT_ID_COLLISION")
                    conn.rollback()
                    return existing
                self._causation(event, {e["event_id"]: e for e in events})
                recorded = format_utc(self.clock())
                require(not events or parse_utc(recorded) >= parse_utc(events[-1]["recorded_at_utc"]),
                        "CLOCK_REGRESSION")
                event.update(ledger_id=meta["ledger_id"], producer_id=producer_id,
                             ingestion_policy_version=meta["policy"]["version"], sequence=len(events) + 1,
                             recorded_at_utc=recorded,
                             integrity={"previous_hash": events[-1]["integrity"]["event_hash"] if events else "GENESIS"})
                event["integrity"]["event_hash"] = event_hash(event)
                validate_recorded(event)
                projection = _project(events + [event], meta["policy"])
                limits = meta["limits"]
                require(len(events) < limits["max_events"], "BUDGET_EXCEEDED")
                require(sum(e["producer_id"] == producer_id for e in events) < limits["per_producer"],
                        "BUDGET_EXCEEDED")
                # Reserve for WAL frames, index pages and this bounded transaction.
                size = sum(p.stat().st_size for p in self.root.glob(DB_NAME + "*") if p.is_file())
                require(size + 65_536 + 4 * len(canonical_bytes(event)) <= limits["max_bytes"], "BUDGET_EXCEEDED")
                conn.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)", (
                    event["sequence"], event["event_id"], producer_id, request_hash, event["quest_id"],
                    event["actor_id"], event["correlation_id"], recorded, canonical_bytes(event).decode()))
                conn.execute("UPDATE projection SET body=? WHERE id=1", (canonical_bytes(projection).decode(),))
                conn.commit()
                return event
            except BaseException:
                conn.rollback()
                raise
