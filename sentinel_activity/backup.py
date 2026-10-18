"""Explicit SQLite backup/restore into an empty private lab destination.

Partial destinations are retained on failure for inspection. Never overwrite,
truncate, prune or repair an existing journal. No independent trust anchor is
created by the adjacent manifest.
"""

import hashlib
import os
import sqlite3
from pathlib import Path

from sentinel_activity.canonical import canonical_bytes, require, strict_loads
from sentinel_activity.integrity import report
from sentinel_activity.store import ActivityStore, DB_NAME, _private_file, _root, _translate


def _file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65_536):
            result.update(chunk)
    return result.hexdigest()


def _write_once(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            require(written > 0, "UNAVAILABLE")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def backup(source: Path, destination: Path, *, _expected: dict | None = None) -> dict:
    store = ActivityStore(source)
    destination = _root(Path(destination))
    require(not list(destination.iterdir()), "ALREADY_EXISTS")
    target = destination / DB_NAME
    with _translate(), store._connection(readonly=True) as conn:
        conn.execute("BEGIN")
        meta, events, _ = store._verified(conn)
        verification = report(meta, events)
        if _expected is not None:
            require(all(_expected[k] == meta[k] for k in ("ledger_id", "storage_version", "policy_hash", "mode")),
                    "CORRUPTED")
            require(_expected["event_count"] == verification["event_count"] and
                    _expected["head_hash"] == verification["head_hash"], "CORRUPTED")
        _write_once(target, b"")
        target_conn = sqlite3.connect(target, isolation_level=None, timeout=2)
        try:
            target_conn.execute("PRAGMA synchronous=FULL")
            conn.backup(target_conn)
        finally:
            target_conn.close()
    copied = ActivityStore(destination).snapshot()
    require(report(copied[0], copied[1]) == verification, "CORRUPTED")
    manifest = {"backup_schema": "j01-backup/1", "ledger_id": meta["ledger_id"],
                "storage_version": meta["storage_version"], "policy_hash": meta["policy_hash"],
                "event_count": verification["event_count"], "head_hash": verification["head_hash"],
                "database_sha256": _file_hash(target), "mode": "SIMULATED_ONLY"}
    with _translate():
        _write_once(destination / "manifest.json", canonical_bytes(manifest))
        fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return manifest


def restore(source: Path, destination: Path) -> dict:
    source = _root(Path(source))
    with _translate():
        manifest_path = source / "manifest.json"
        _private_file(manifest_path)
        require(manifest_path.stat().st_size <= 4096, "CORRUPTED")
        manifest = strict_loads(manifest_path.read_bytes(), 4096)
        require(type(manifest) is dict and set(manifest) == {
            "backup_schema", "ledger_id", "storage_version", "policy_hash", "event_count", "head_hash",
            "database_sha256", "mode"}, "CORRUPTED")
        require(manifest["backup_schema"] == "j01-backup/1", "UNKNOWN_VERSION")
        _private_file(source / DB_NAME)
        require(manifest["database_sha256"] == _file_hash(source / DB_NAME), "CORRUPTED")
        store = ActivityStore(source)
        meta, events, _ = store.snapshot()
        verification = report(meta, events)
        require(all(manifest[k] == meta[k] for k in ("ledger_id", "storage_version", "policy_hash", "mode")),
                "CORRUPTED")
        require(manifest["event_count"] == verification["event_count"] and
                manifest["head_hash"] == verification["head_hash"], "CORRUPTED")
        # Recheck the approved snapshot inside the copy transaction, before any destination write.
        copied = backup(source, destination, _expected=manifest)
        require(all(copied[k] == manifest[k] for k in ("ledger_id", "policy_hash", "event_count", "head_hash")),
                "CORRUPTED")
        return copied
