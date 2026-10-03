"""Transport-only event projection reader; never reads alert/PPL journals."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from observability.event_center_artifact import read_bytes, strict_json
from observability.event_center_contract import finite, utc_seconds, validate_event_center

DEFAULT_PATH = Path(os.getenv("EVENT_CENTER_SNAPSHOT_PATH", "databases/event_center_snapshot.json"))
STALE_AFTER_S = 90.0


@dataclass(frozen=True)
class EventCenterReadResult:
    ok: bool
    snapshot: dict | None = None
    error_code: str | None = None


class EventCenterReader:
    def __init__(self, path=DEFAULT_PATH, *, now_fn=time.time):
        self.path, self.now_fn = Path(path), now_fn

    def read(self):
        try:
            doc = strict_json(read_bytes(self.path))
            if not validate_event_center(doc):
                return EventCenterReadResult(False, error_code="EVENT_CENTER_INVALID_SCHEMA")
        except FileNotFoundError:
            return EventCenterReadResult(False, error_code="EVENT_CENTER_MISSING")
        except (OSError, ValueError, TypeError, KeyError, OverflowError, UnicodeError, RecursionError):
            return EventCenterReadResult(False, error_code="EVENT_CENTER_INVALID_ARTIFACT")
        now = self.now_fn()
        generated = utc_seconds(doc["generated_at_utc"])
        if not finite(now) or now < generated:
            return EventCenterReadResult(False, error_code="EVENT_CENTER_FUTURE_TIMESTAMP")
        age = now - generated
        sources = []
        for source in doc["sources"]:
            source_time = utc_seconds(source["source_generated_at_utc"])
            source_age = None if source_time is None else now - source_time
            freshness = "NOT_AVAILABLE" if source["status"] != "PRESENT" else (
                "UNKNOWN" if source_age is None else
                "STALE" if age > STALE_AFTER_S or source_age > STALE_AFTER_S else "FRESH"
            )
            sources.append({**source, "source_age_s": source_age, "freshness_classification": freshness})
        return EventCenterReadResult(True, {
            **doc, "sources": sources, "snapshot_age_s": age,
            "freshness_classification": "STALE" if age > STALE_AFTER_S else "FRESH",
        })
