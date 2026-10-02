"""U2b transport reader: no subprocess, systemd, Advisor, manifest or PPL."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path

from observability.runtime_service_artifact import read_document
from observability.runtime_service_contract import (
    utc_seconds,
    validate_runtime_service_snapshot,
)

DEFAULT_RUNTIME_SERVICE_PATH = Path("databases/runtime_service_snapshot.json")
DEFAULT_STALE_AFTER_S = 90.0


@dataclass(frozen=True)
class RuntimeServiceReadResult:
    ok: bool
    snapshot: dict | None = None
    error_code: str | None = None


class RuntimeServiceSnapshotReader:
    def __init__(
        self,
        path: Path = DEFAULT_RUNTIME_SERVICE_PATH,
        *,
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        now_fn=time.time,
    ):
        self._path = Path(path)
        self._stale_after_s = float(stale_after_s)
        self._now_fn = now_fn
        if not math.isfinite(self._stale_after_s) or self._stale_after_s <= 0:
            raise ValueError("INVALID_STALE_THRESHOLD")

    def read(self) -> RuntimeServiceReadResult:
        try:
            doc, _ = read_document(self._path)
        except FileNotFoundError:
            return RuntimeServiceReadResult(False, error_code="RUNTIME_SERVICE_MISSING")
        except (OSError, TypeError, ValueError, UnicodeError):
            return RuntimeServiceReadResult(
                False, error_code="RUNTIME_SERVICE_INVALID_ARTIFACT"
            )
        if not validate_runtime_service_snapshot(doc):
            return RuntimeServiceReadResult(
                False, error_code="RUNTIME_SERVICE_INVALID_SCHEMA"
            )
        observed = utc_seconds(doc["observed_at_utc"])
        generated = utc_seconds(doc["generated_at_utc"])
        now = float(self._now_fn())
        if not math.isfinite(now) or generated > now:
            return RuntimeServiceReadResult(
                False, error_code="RUNTIME_SERVICE_FUTURE_TIMESTAMP"
            )
        # Freshness is measured from the actual host collection, not republishing.
        age = now - observed
        return RuntimeServiceReadResult(
            True,
            snapshot={
                **doc,
                "snapshot_age_s": age,
                "freshness_classification": "STALE"
                if age > self._stale_after_s
                else "FRESH",
            },
        )
