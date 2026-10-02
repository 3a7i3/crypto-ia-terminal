"""GET transport of U3b artifact with temporal annotations only, no LMI I/O."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from observability.market_microstructure_artifact import read_document
from observability.market_microstructure_contract import (
    STALE_AFTER_S,
    finite,
    utc_seconds,
    validate_microstructure_snapshot,
)

DEFAULT_PATH = Path(
    os.getenv(
        "MARKET_MICROSTRUCTURE_SNAPSHOT_PATH",
        "databases/market_microstructure_snapshot.json",
    )
)


@dataclass(frozen=True)
class MicrostructureReadResult:
    ok: bool
    snapshot: dict | None = None
    error_code: str | None = None


class MarketMicrostructureReader:
    def __init__(self, path=DEFAULT_PATH, *, now_fn=time.time):
        self.path, self.now_fn = Path(path), now_fn

    def read(self):
        try:
            doc, _ = read_document(self.path)
        except FileNotFoundError:
            return MicrostructureReadResult(False, error_code="MICROSTRUCTURE_MISSING")
        except (OSError, ValueError, TypeError, UnicodeError):
            return MicrostructureReadResult(
                False, error_code="MICROSTRUCTURE_INVALID_ARTIFACT"
            )
        if not validate_microstructure_snapshot(doc):
            return MicrostructureReadResult(
                False, error_code="MICROSTRUCTURE_INVALID_SCHEMA"
            )
        now = self.now_fn()
        if not finite(now) or now < utc_seconds(doc["generated_at_utc"]):
            return MicrostructureReadResult(
                False, error_code="MICROSTRUCTURE_FUTURE_TIMESTAMP"
            )
        read_at = (
            datetime.fromtimestamp(now, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        now = utc_seconds(read_at)
        source_age = now - utc_seconds(doc["source_updated_at_utc"])
        rows = []
        for row in doc["rows"]:
            age = (
                None
                if row["observed_at_utc"] is None
                else now - utc_seconds(row["observed_at_utc"])
            )
            classification = (
                "NOT_AVAILABLE"
                if row["availability"] == "UNAVAILABLE"
                else "UNKNOWN"
                if age is None
                else "STALE"
                if source_age > STALE_AFTER_S or age > STALE_AFTER_S
                else "FRESH"
            )
            rows.append(
                {
                    **row,
                    "observation_age_s": age,
                    "freshness_classification": classification,
                }
            )
        result = {
            **doc,
            "rows": rows,
            "read_at_utc": read_at,
            "source_age_s": source_age,
            "freshness_classification": "STALE"
            if source_age > STALE_AFTER_S
            else "FRESH",
        }
        if not validate_microstructure_snapshot(result, transport=True):
            return MicrostructureReadResult(
                False, error_code="MICROSTRUCTURE_INVALID_SCHEMA"
            )
        return MicrostructureReadResult(True, result)
