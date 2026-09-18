"""Strict read-only reader for the WEB-02 PPL comparison artifact."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_PPL_COMPARISON_PATH = Path(
    os.getenv(
        "PPL_COMPARISON_SNAPSHOT_PATH",
        "databases/ppl_comparison_snapshot.json",
    )
)


def _env_stale_after_s() -> float:
    raw = os.getenv("PPL_COMPARISON_STALE_AFTER_S", "90")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 90.0
    return value if math.isfinite(value) and value > 0 else 90.0


DEFAULT_STALE_AFTER_S = _env_stale_after_s()

_TOP_KEYS = {
    "schema_version",
    "product",
    "domain",
    "authority",
    "mode",
    "generated_at_utc",
    "process_instance_id",
    "cycle",
    "source_sha",
    "shadow_status",
    "paper_epoch_id",
    "comparison_available",
    "comparison_unavailable_reason",
    "legacy_source",
    "ppl_source",
    "summary",
    "comparisons",
    "positions",
    "closed_session",
    "ppl_events",
}
_SOURCE_KEYS = {"value", "status", "provenance"}
_COMPARISON_KEYS = {
    "comparison_id",
    "domain",
    "field",
    "trade_id",
    "classification",
    "relation",
    "legacy",
    "ppl",
    "delta_ppl_minus_legacy",
    "comparison_rule",
    "note",
}
_GROUP_KEYS = {
    "trade_id",
    "relation",
    "legacy_present",
    "ppl_present",
    "field_comparison_ids",
}
_EVENT_KEYS = {
    "event_id",
    "sequence",
    "event_type",
    "trade_id",
    "decision_id",
    "timestamp",
    "payload",
}
_SUMMARY_KEYS = {
    "total",
    "comparable",
    "partial",
    "unresolved",
    "equal",
    "different",
    "legacy_only",
    "ppl_only",
    "not_comparable",
}
_COMPARISON_CLASSES = {"COMPARABLE", "PARTIAL", "UNRESOLVED"}
_RELATIONS = {
    "EQUAL",
    "DIFFERENT",
    "LEGACY_ONLY",
    "PPL_ONLY",
    "NOT_COMPARABLE",
}
_GROUP_RELATIONS = {"BOTH", "LEGACY_ONLY", "PPL_ONLY", "NEITHER"}
_SHADOW_STATUSES = {"OFF", "WAITING_CLEAN_BOUNDARY", "ACTIVE", "DEGRADED"}


@dataclass(frozen=True)
class PplComparisonReadResult:
    ok: bool
    snapshot: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    snapshot_age_s: Optional[float] = None
    freshness_classification: Optional[str] = None


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _parse_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _valid_source(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == _SOURCE_KEYS
        and isinstance(value["status"], str)
        and bool(value["status"])
        and isinstance(value["provenance"], str)
        and bool(value["provenance"])
    )


def _valid_comparison(row: Any) -> bool:
    if not isinstance(row, dict) or set(row) != _COMPARISON_KEYS:
        return False
    if not isinstance(row["comparison_id"], str) or not row[
        "comparison_id"
    ].startswith("web02-"):
        return False
    if not isinstance(row["domain"], str) or not row["domain"]:
        return False
    if not isinstance(row["field"], str) or not row["field"]:
        return False
    if row["trade_id"] is not None and not isinstance(row["trade_id"], str):
        return False
    if row["classification"] not in _COMPARISON_CLASSES:
        return False
    if row["relation"] not in _RELATIONS:
        return False
    if not _valid_source(row["legacy"]) or not _valid_source(row["ppl"]):
        return False
    delta = row["delta_ppl_minus_legacy"]
    if delta is not None and not _finite_number(delta):
        return False
    if row["classification"] != "COMPARABLE" and delta is not None:
        return False
    if not isinstance(row["comparison_rule"], str):
        return False
    if row["note"] is not None and not isinstance(row["note"], str):
        return False
    return True


def _valid_group(row: Any) -> bool:
    if not isinstance(row, dict) or set(row) != _GROUP_KEYS:
        return False
    if not isinstance(row["trade_id"], str) or not row["trade_id"]:
        return False
    if row["relation"] not in _GROUP_RELATIONS:
        return False
    if not isinstance(row["legacy_present"], bool):
        return False
    if not isinstance(row["ppl_present"], bool):
        return False
    ids = row["field_comparison_ids"]
    return isinstance(ids, list) and all(
        isinstance(x, str) and x.startswith("web02-") for x in ids
    )


def _valid_event(row: Any) -> bool:
    if not isinstance(row, dict) or set(row) != _EVENT_KEYS:
        return False
    if not isinstance(row["event_id"], str) or not row["event_id"]:
        return False
    if (
        not isinstance(row["sequence"], int)
        or isinstance(row["sequence"], bool)
        or row["sequence"] < 1
    ):
        return False
    if not isinstance(row["event_type"], str) or not row["event_type"]:
        return False
    if row["trade_id"] is not None and not isinstance(row["trade_id"], str):
        return False
    if row["decision_id"] is not None and not isinstance(
        row["decision_id"], str
    ):
        return False
    if not _finite_number(row["timestamp"]):
        return False
    return isinstance(row["payload"], dict)


def validate_ppl_comparison_snapshot(doc: Any) -> bool:
    """Closed-schema admission gate for producer-authored WEB-02 evidence."""

    if not isinstance(doc, dict) or set(doc) != _TOP_KEYS:
        return False
    if doc["schema_version"] != "1.0.0":
        return False
    if doc["product"] != "PPLComparator":
        return False
    if doc["domain"] != "ppl_comparison":
        return False
    if doc["authority"] != "OBSERVATIONAL_TELEMETRY":
        return False
    if doc["mode"] != "SHADOW_COMPARISON":
        return False
    if _parse_utc(doc["generated_at_utc"]) is None:
        return False
    if not isinstance(doc["process_instance_id"], str):
        return False
    if (
        not isinstance(doc["cycle"], int)
        or isinstance(doc["cycle"], bool)
        or doc["cycle"] < 0
    ):
        return False
    if doc["source_sha"] is not None and not isinstance(
        doc["source_sha"], str
    ):
        return False
    if doc["shadow_status"] not in _SHADOW_STATUSES:
        return False
    if doc["paper_epoch_id"] is not None and not isinstance(
        doc["paper_epoch_id"], str
    ):
        return False
    if not isinstance(doc["comparison_available"], bool):
        return False
    if doc["comparison_unavailable_reason"] is not None and not isinstance(
        doc["comparison_unavailable_reason"], str
    ):
        return False
    if doc["comparison_available"] and doc["shadow_status"] != "ACTIVE":
        return False

    if not isinstance(doc["legacy_source"], dict):
        return False
    if not isinstance(doc["ppl_source"], dict):
        return False

    summary = doc["summary"]
    if not isinstance(summary, dict) or set(summary) != _SUMMARY_KEYS:
        return False
    if not all(
        isinstance(summary[k], int)
        and not isinstance(summary[k], bool)
        and summary[k] >= 0
        for k in _SUMMARY_KEYS
    ):
        return False

    comparisons = doc["comparisons"]
    if not isinstance(comparisons, list) or not all(
        _valid_comparison(row) for row in comparisons
    ):
        return False
    if summary["total"] != len(comparisons):
        return False

    if not isinstance(doc["positions"], list) or not all(
        _valid_group(row) for row in doc["positions"]
    ):
        return False
    if not isinstance(doc["closed_session"], list) or not all(
        _valid_group(row) for row in doc["closed_session"]
    ):
        return False
    if not isinstance(doc["ppl_events"], list) or not all(
        _valid_event(row) for row in doc["ppl_events"]
    ):
        return False
    sequences = [row["sequence"] for row in doc["ppl_events"]]
    if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
        return False
    return True


class PplComparisonSnapshotReader:
    def __init__(
        self,
        path: Path = DEFAULT_PPL_COMPARISON_PATH,
        *,
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        now_fn=time.time,
    ) -> None:
        self._path = Path(path)
        self._stale_after_s = float(stale_after_s)
        self._now_fn = now_fn
        if (
            not math.isfinite(self._stale_after_s)
            or self._stale_after_s <= 0
        ):
            raise ValueError("stale_after_s must be finite and > 0")

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> PplComparisonReadResult:
        if not self._path.exists():
            return PplComparisonReadResult(
                ok=False,
                error_code="PPL_COMPARISON_SNAPSHOT_MISSING",
                error_message=(
                    f"PPL comparison snapshot not found: {self._path}"
                ),
            )
        if not self._path.is_file():
            return PplComparisonReadResult(
                ok=False,
                error_code="PPL_COMPARISON_INVALID_PATH",
                error_message="PPL comparison path is not a regular file.",
            )

        try:
            doc = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            return PplComparisonReadResult(
                ok=False,
                error_code="PPL_COMPARISON_UNREADABLE",
                error_message=str(exc),
            )
        except json.JSONDecodeError as exc:
            return PplComparisonReadResult(
                ok=False,
                error_code="PPL_COMPARISON_MALFORMED_JSON",
                error_message=str(exc),
            )

        if not validate_ppl_comparison_snapshot(doc):
            return PplComparisonReadResult(
                ok=False,
                error_code="PPL_COMPARISON_INVALID_SCHEMA",
                error_message=(
                    "PPL comparison snapshot failed the WEB-02 "
                    "closed schema contract."
                ),
            )

        generated = _parse_utc(doc["generated_at_utc"])
        assert generated is not None
        age = max(
            0.0, float(self._now_fn()) - generated.timestamp()
        )
        freshness = "STALE" if age > self._stale_after_s else "FRESH"
        return PplComparisonReadResult(
            ok=True,
            snapshot=dict(doc),
            snapshot_age_s=age,
            freshness_classification=freshness,
        )


__all__ = [
    "DEFAULT_PPL_COMPARISON_PATH",
    "DEFAULT_STALE_AFTER_S",
    "PplComparisonReadResult",
    "PplComparisonSnapshotReader",
    "validate_ppl_comparison_snapshot",
]
