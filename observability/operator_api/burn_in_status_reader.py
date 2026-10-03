"""Strict GET-only reader for APP-UNIFY-01 U2 BurnInStatusSnapshot.

This module deliberately imports only the pure presentation contract.  The
Operator API never imports PPL projection/store code and never reads JSONL.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from observability.burn_in_status_contract import validate_burn_in_status_snapshot


DEFAULT_BURN_IN_STATUS_PATH = Path(
    os.getenv("BURN_IN_STATUS_SNAPSHOT_PATH", "databases/burn_in_status_snapshot.json")
)


def _env_stale_after_s() -> float:
    raw = os.getenv("BURN_IN_STATUS_STALE_AFTER_S", "90")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 90.0
    return value if math.isfinite(value) and value > 0 else 90.0


DEFAULT_STALE_AFTER_S = _env_stale_after_s()


@dataclass(frozen=True)
class BurnInStatusReadResult:
    ok: bool
    snapshot: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    snapshot_age_s: Optional[float] = None
    freshness_classification: Optional[str] = None


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class BurnInStatusSnapshotReader:
    def __init__(
        self,
        path: Path = DEFAULT_BURN_IN_STATUS_PATH,
        *,
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        now_fn=time.time,
    ) -> None:
        self._path = Path(path)
        self._stale_after_s = float(stale_after_s)
        self._now_fn = now_fn
        if not math.isfinite(self._stale_after_s) or self._stale_after_s <= 0:
            raise ValueError("stale_after_s must be finite and > 0")

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> BurnInStatusReadResult:
        if not self._path.exists():
            return BurnInStatusReadResult(
                ok=False,
                error_code="BURN_IN_STATUS_MISSING",
                error_message=f"BurnInStatusSnapshot not found: {self._path}",
            )
        if not self._path.is_file() or self._path.is_symlink():
            return BurnInStatusReadResult(
                ok=False,
                error_code="BURN_IN_STATUS_INVALID_PATH",
                error_message="BurnInStatusSnapshot path must be a regular non-symlink file.",
            )
        try:
            doc = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            return BurnInStatusReadResult(
                ok=False,
                error_code="BURN_IN_STATUS_UNREADABLE",
                error_message=str(exc),
            )
        except json.JSONDecodeError as exc:
            return BurnInStatusReadResult(
                ok=False,
                error_code="BURN_IN_STATUS_MALFORMED_JSON",
                error_message=str(exc),
            )

        if not validate_burn_in_status_snapshot(doc):
            return BurnInStatusReadResult(
                ok=False,
                error_code="BURN_IN_STATUS_INVALID_SCHEMA",
                error_message="BurnInStatusSnapshot failed the closed schema/authority contract.",
            )

        generated = _parse_utc(doc["generated_at_utc"]).timestamp()
        age = max(0.0, float(self._now_fn()) - generated)
        freshness = "STALE" if age > self._stale_after_s else "FRESH"
        return BurnInStatusReadResult(
            ok=True,
            snapshot=dict(doc),
            snapshot_age_s=age,
            freshness_classification=freshness,
        )


__all__ = [
    "BurnInStatusReadResult",
    "BurnInStatusSnapshotReader",
    "DEFAULT_BURN_IN_STATUS_PATH",
    "DEFAULT_STALE_AFTER_S",
]
