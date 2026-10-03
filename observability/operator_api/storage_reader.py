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
