"""observability/operator_api/reader.py — O-02W-D1 safe canonical snapshot
reader.

Implements mission §5 (SAFE FILE READER). This is the ONE reusable
component every endpoint uses to load the canonical operator snapshot. It:

1. Reads the runtime manifest.
2. Reads the snapshot.
3. Re-reads the runtime manifest.
4. Performs a bounded retry if the manifest changed during the read.
5. Validates JSON structure.
6. Validates required envelope fields.
7. Compares manifest and snapshot ``process_instance_id``.
8. Never replaces missing/corrupt data with empty successful data.
9. Never mutates the loaded document.
10. Never persists a repaired/default document.

It never writes to either file, never instantiates
``MexcSimulator``/``WalletSync``/``RealAccountsObserver``, never imports
``core.advisor_loop``, and never infers process liveness from anything it
reads here (§14.2 of
docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md).
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from observability.operator_runtime_manifest import DEFAULT_MANIFEST_PATH
from observability.operator_snapshot_builder import DEFAULT_SNAPSHOT_PATH

# §14.1/§14.2 INSTANCE_RELATION vocabulary — identity/succession only,
# never a liveness claim.
INSTANCE_RELATION_CURRENT = "CURRENT_INSTANCE"
INSTANCE_RELATION_PREVIOUS = "PREVIOUS_INSTANCE"
INSTANCE_RELATION_UNKNOWN = "UNKNOWN"

# Higher-level convenience projection (§14.1) derived deterministically
# from INSTANCE_RELATION — never an independent judgment.
RUNTIME_STATE_CURRENT = "CURRENT"
RUNTIME_STATE_LAST_KNOWN = "LAST_KNOWN"

_REQUIRED_ENVELOPE_FIELDS = (
    "schema_version",
    "snapshot_id",
    "cycle",
    "process_instance_id",
    "generated_at_utc",
    "portfolio",
    "decision_pipeline",
    "system_health",
)

DEFAULT_MAX_RETRIES = 3


@dataclass(frozen=True)
class SnapshotReadResult:
    """Outcome of one bounded, validated read attempt.

    ``ok=False`` means the caller MUST surface a structured failure
    (e.g. HTTP 503) — never HTTP 200 with fabricated empty domains
    (mission §5).
    """

    ok: bool
    snapshot: Optional[Dict[str, Any]] = None
    manifest: Optional[Dict[str, Any]] = None
    instance_relation: str = INSTANCE_RELATION_UNKNOWN
    runtime_state: str = RUNTIME_STATE_LAST_KNOWN
    snapshot_age_s: Optional[float] = None
    freshness_classification: str = "UNKNOWN"
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retries_used: int = 0


def _read_json_file(path: Path) -> "tuple[Optional[Dict[str, Any]], Optional[str]]":
    """Read+parse one JSON file. Returns (doc, error_code).

    ``error_code`` is one of ``None`` (success), ``MISSING``,
    ``UNREADABLE``, ``MALFORMED_JSON``, ``NOT_AN_OBJECT`` — never coerces
    a failure into an empty ``{}`` success.
    """

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "MISSING"
    except OSError:
        return None, "UNREADABLE"

    try:
        doc = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None, "MALFORMED_JSON"

    if not isinstance(doc, dict):
        return None, "NOT_AN_OBJECT"

    return doc, None


def _missing_required_fields(snapshot: Dict[str, Any]) -> List[str]:
    return [f for f in _REQUIRED_ENVELOPE_FIELDS if f not in snapshot]


def _compute_age_s(generated_at_utc: Any, now_fn) -> Optional[float]:
    if not isinstance(generated_at_utc, str):
        return None
    try:
        ts = generated_at_utc
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        parsed = _dt.datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        return None
    now = now_fn()
    now_dt = _dt.datetime.fromtimestamp(now, tz=_dt.timezone.utc)
    return max(0.0, (now_dt - parsed).total_seconds())


class SafeSnapshotReader:
    """Reusable, configurable-path canonical snapshot reader.

    Never mutates the JSON documents it loads (a fresh ``copy.deepcopy``
    is returned to callers so an accidental in-place edit downstream can
    never corrupt a cached/re-read structure), and never writes to either
    file.
    """

    def __init__(
        self,
        snapshot_path: Path = DEFAULT_SNAPSHOT_PATH,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
        max_retries: int = DEFAULT_MAX_RETRIES,
        now_fn=None,
    ) -> None:
        self._snapshot_path = Path(snapshot_path)
        self._manifest_path = Path(manifest_path)
        self._max_retries = max_retries
        if now_fn is None:
            import time as _time

            now_fn = _time.time
        self._now_fn = now_fn

    def read(self) -> SnapshotReadResult:
        retries_used = 0
        manifest_before, manifest_err = _read_json_file(self._manifest_path)

        while True:
            snapshot, snapshot_err = _read_json_file(self._snapshot_path)
            manifest_after, manifest_after_err = _read_json_file(self._manifest_path)

            manifest_changed = (
                manifest_before != manifest_after or manifest_err != manifest_after_err
            )
            if manifest_changed and retries_used < self._max_retries:
                retries_used += 1
                manifest_before, manifest_err = manifest_after, manifest_after_err
                continue
            break

        if manifest_changed:
            return SnapshotReadResult(
                ok=False,
                error_code="MANIFEST_CHANGED_DURING_READ",
                error_message=(
                    "Runtime manifest changed while reading the snapshot; "
                    f"bounded retry ({self._max_retries}) exhausted."
                ),
                retries_used=retries_used,
            )

        manifest, manifest_err = manifest_after, manifest_after_err

        if snapshot_err is not None:
            return SnapshotReadResult(
                ok=False,
                error_code=f"SNAPSHOT_{snapshot_err}",
                error_message=f"Canonical snapshot unreadable: {snapshot_err}",
                retries_used=retries_used,
            )

        missing = _missing_required_fields(snapshot)
        if missing:
            return SnapshotReadResult(
                ok=False,
                error_code="SNAPSHOT_MISSING_REQUIRED_FIELDS",
                error_message=f"Snapshot missing required envelope fields: {missing}",
                retries_used=retries_used,
            )

        # §14.1/§14.2 INSTANCE_RELATION — manifest missing/unreadable/
        # corrupt => UNKNOWN, never coerced to CURRENT_INSTANCE.
        if manifest_err is not None:
            instance_relation = INSTANCE_RELATION_UNKNOWN
        elif "process_instance_id" not in manifest:
            instance_relation = INSTANCE_RELATION_UNKNOWN
        elif manifest["process_instance_id"] == snapshot["process_instance_id"]:
            instance_relation = INSTANCE_RELATION_CURRENT
        else:
            instance_relation = INSTANCE_RELATION_PREVIOUS

        runtime_state = (
            RUNTIME_STATE_CURRENT
            if instance_relation == INSTANCE_RELATION_CURRENT
            else RUNTIME_STATE_LAST_KNOWN
        )

        age_s = _compute_age_s(snapshot.get("generated_at_utc"), self._now_fn)

        return SnapshotReadResult(
            ok=True,
            snapshot=copy.deepcopy(snapshot),
            manifest=copy.deepcopy(manifest) if manifest is not None else None,
            instance_relation=instance_relation,
            runtime_state=runtime_state,
            snapshot_age_s=age_s,
            # No governed freshness threshold exists for this envelope
            # today (mission §5) — age is exposed, classification stays
            # UNKNOWN rather than inventing a threshold.
            freshness_classification="UNKNOWN",
            retries_used=retries_used,
        )


__all__ = [
    "INSTANCE_RELATION_CURRENT",
    "INSTANCE_RELATION_PREVIOUS",
    "INSTANCE_RELATION_UNKNOWN",
    "RUNTIME_STATE_CURRENT",
    "RUNTIME_STATE_LAST_KNOWN",
    "SnapshotReadResult",
    "SafeSnapshotReader",
]
