"""Storage artifact transport; never scans source directories or opens journals."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from observability.event_center_contract import finite, utc_seconds
from observability.runtime_service_artifact import read_document
from observability.storage_contract import validate_storage_snapshot

DEFAULT_PATH = Path(os.getenv("STORAGE_SNAPSHOT_PATH", "databases/storage_snapshot.json"))


@dataclass(frozen=True)
class StorageReadResult:
    ok: bool
    snapshot: dict | None = None
    error_code: str | None = None


class StorageSnapshotReader:
    def __init__(self, path=DEFAULT_PATH, *, now_fn=time.time):
        self.path, self.now_fn = Path(path), now_fn

    def read(self):
        try:
            doc, _ = read_document(self.path)
            if not validate_storage_snapshot(doc):
                return StorageReadResult(False, error_code="STORAGE_INVALID_SCHEMA")
        except FileNotFoundError:
            return StorageReadResult(False, error_code="STORAGE_MISSING")
        except (OSError, ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
            return StorageReadResult(False, error_code="STORAGE_INVALID_ARTIFACT")
        now = self.now_fn()
        if not finite(now) or now < utc_seconds(doc["generated_at_utc"]):
            return StorageReadResult(False, error_code="STORAGE_FUTURE_TIMESTAMP")
        age = now - utc_seconds(doc["observed_at_utc"])
        return StorageReadResult(True, {**doc, "snapshot_age_s": age,
                                       "freshness_classification": "STALE" if age > 90 else "FRESH"})


def read_storage_inventory():
    """Read only the bounded, published metadata artifact."""
    from observability.storage_inventory import valid

    path = Path(os.getenv("STORAGE_INVENTORY_PATH", "databases/storage_inventory.json"))
    try:
        doc, _ = read_document(path)
        if valid(doc) and utc_seconds(doc["observed_at"]) <= time.time():
            return {**doc, "agent_reports": read_agent_report_inventory()}
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        pass
    return None

def read_agent_report_inventory():
    """Read aggregate metadata without opening agent reports."""
    path = Path("/var/lib/cat-agent-report-inventory/inventory.json")
    try:
        doc, _ = read_document(path)
        if set(doc) != {"observed_at", "runs", "rehearsals"}:
            return None
        if not 0 < utc_seconds(doc["observed_at"]) <= time.time():
            return None
        for kind in ("runs", "rehearsals"):
            row = doc[kind]
            if set(row) != {"files", "bytes"}:
                return None
            if any(type(value) is not int or not 0 <= value < 2**52 for value in row.values()):
                return None
            if row["files"] == 0 and row["bytes"] != 0:
                return None
        return doc
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        return None
