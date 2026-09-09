"""observability/operator_api/reader.py — O-02W-D1 safe canonical snapshot
reader.

Implements mission §5 (SAFE FILE READER). This is the ONE reusable
component every endpoint uses to load the canonical operator snapshot. It:

1. Reads the runtime manifest.
2. Reads the snapshot.
3. Re-reads the runtime manifest.
4. Performs a bounded retry if the manifest changed during the read.
5. Validates JSON structure.
6. Validates required envelope fields AND their values (§ O-02W-D1-R1
   correction C, extended by R1.1 correction A to cover the four source/
   runtime-evidence fields, and by R1.2 corrections A/B to a closed
   vocabulary for `deployment_evidence.source` and whitespace-only
   rejection for evidence strings — key presence alone is not enough).
7. Compares manifest and snapshot ``process_instance_id``, requiring the
   manifest to be minimally usable for identity purposes first (R1.1
   correction B).
8. Never replaces missing/corrupt data with empty successful data.
9. Never mutates the loaded document.
10. Never persists a repaired/default document.

It never writes to either file, never instantiates
``MexcSimulator``/``WalletSync``/``RealAccountsObserver``, never imports
``core.advisor_loop`` (or any producer/writer module — see
``observability/operator_api/paths.py`` for why), and never infers
process liveness from anything it reads here (§14.2 of
docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md).
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from observability.operator_api.paths import DEFAULT_MANIFEST_PATH, DEFAULT_SNAPSHOT_PATH

# §14.1/§14.2 INSTANCE_RELATION vocabulary — identity/succession only,
# never a liveness claim.
INSTANCE_RELATION_CURRENT = "CURRENT_INSTANCE"
INSTANCE_RELATION_PREVIOUS = "PREVIOUS_INSTANCE"
INSTANCE_RELATION_UNKNOWN = "UNKNOWN"

# Higher-level convenience projection (§14.1) derived deterministically
# from INSTANCE_RELATION — never an independent judgment.
RUNTIME_STATE_CURRENT = "CURRENT"
RUNTIME_STATE_LAST_KNOWN = "LAST_KNOWN"

# Contractual stale reason (R1 correction B) — set ONLY when the relation
# is PREVIOUS_INSTANCE (a genuine, evidenced producer restart). Never set
# for CURRENT_INSTANCE (nothing to explain) or UNKNOWN (a missing/corrupt
# manifest is not evidence of a restart — it is evidence of nothing).
STALE_REASON_PRODUCER_RESTARTED = "PRODUCER_RESTARTED"

_REQUIRED_ENVELOPE_FIELDS = (
    "schema_version",
    "snapshot_id",
    "cycle",
    "process_instance_id",
    "generated_at_utc",
    "portfolio",
    "decision_pipeline",
    "system_health",
    # R1.1 correction A: the four source/runtime-evidence fields the
    # certified O-02W-B contract (§14/§15) defines and O-02W-C produces
    # (observability/source_evidence.py::SourceEvidence.to_dict()).
    "source_sha",
    "worktree_state",
    "deployment_evidence",
    "runtime_sha_evidence_status",
)

# Snapshot schema versions this reader understands. Duplicated here
# (rather than imported from `observability.operator_snapshot_builder`)
# deliberately — see `paths.py` docstring: the API package must not
# import the producer module at all, even for a constant.
_SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0.0"})

# The manifest's own `schema_version` (an int, per
# observability/operator_runtime_manifest.py::SCHEMA_VERSION) — duplicated
# here for the same reason as above.
_SUPPORTED_MANIFEST_SCHEMA_VERSIONS = frozenset({1})

# A cycle number is a plain, non-negative integer identity — not a
# timestamp, not unbounded. This is intentionally generous (mission §5
# gives no explicit contractual upper bound); the point is to reject
# malformed types (bool, float, string, negative), not to guess a real
# ceiling.
_CYCLE_MIN = 0
_CYCLE_MAX = 2**63 - 1

_DOMAIN_KEYS = ("portfolio", "decision_pipeline", "system_health")

_WORKTREE_STATES = frozenset({"CLEAN", "DIRTY", "UNKNOWN"})
_RUNTIME_SHA_EVIDENCE_STATUSES = frozenset({"VERIFIED", "CLAIMED_ONLY", "UNKNOWN"})
_DEPLOYMENT_EVIDENCE_STATUSES = frozenset({"VERIFIED", "CLAIMED_ONLY", "UNKNOWN"})
_DEPLOYMENT_EVIDENCE_REQUIRED_KEYS = ("status", "source", "evidence_ref", "observed_at_utc")

# R1.2 correction A: `deployment_evidence.source` is a CLOSED vocabulary
# per the certified contract (§15) — a producer-identity provenance tag,
# not free-form text. Any value outside this set (including an invented
# label, a differently-cased variant, or whitespace) is rejected; `None`
# (unavailable) is handled separately, not as a member of this set.
_DEPLOYMENT_EVIDENCE_SOURCES = frozenset(
    {"deploy_tag", "deploy_audit", "post_deploy_verification"}
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
    stale_reason: Optional[str] = None
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


def _is_valid_identifier(value: Any) -> bool:
    """A non-empty, non-whitespace-only string — a whitespace-only value
    is exactly as useless as an empty one. Used for genuine identity/
    evidence fields (`snapshot_id`, `process_instance_id`, `source_sha`
    on both snapshot and manifest, `deployment_evidence.evidence_ref`)
    (R1.1 correction B / R1.2 correction B: "reject whitespace-only
    identifiers"/"evidence strings")."""

    return isinstance(value, str) and len(value.strip()) > 0


def _is_valid_deployment_evidence_source(value: Any) -> bool:
    """R1.2 correction A: `deployment_evidence.source` is validated
    against the certified contract's closed vocabulary — never merely
    "is this a non-empty string." `None` is accepted separately by the
    caller (this helper only judges a non-null candidate value)."""

    return value in _DEPLOYMENT_EVIDENCE_SOURCES


def _is_valid_cycle(value: Any) -> bool:
    # bool is a subclass of int in Python — explicitly excluded, a cycle
    # number is never a boolean (mission §8 test 8/R1).
    if isinstance(value, bool):
        return False
    if not isinstance(value, int):
        return False
    return _CYCLE_MIN <= value <= _CYCLE_MAX


def _parse_timestamp(value: Any) -> "tuple[Optional[_dt.datetime], Optional[str]]":
    """Parse an ISO-8601 UTC timestamp. Returns (parsed_dt, error_code).

    ``error_code`` is ``None`` on success, or a code describing exactly
    why the value could not be trusted — never a silently-swallowed
    ``None`` result mistaken for "no timestamp field" (R1 correction D).

    R1.1 correction C: a field named ``*_utc`` must carry genuine UTC
    evidence — tz-aware alone is not enough. A tz-aware value with a
    non-zero UTC offset (a mislabeled local timestamp) is rejected just
    as a naive one is; this reader never silently normalizes it.
    """

    if not isinstance(value, str) or not value:
        return None, "INVALID_TIMESTAMP_TYPE"
    ts = value
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(ts)
    except ValueError:
        return None, "INVALID_TIMESTAMP_FORMAT"
    if parsed.tzinfo is None:
        # A naive timestamp cannot be honestly compared to UTC "now" —
        # never silently assumed to already be UTC here (the producer's
        # own `_iso_utc()` always emits an explicit offset; a naive value
        # reaching this reader is itself a schema violation).
        return None, "TIMESTAMP_NOT_TIMEZONE_AWARE"
    if parsed.utcoffset() != _dt.timedelta(0):
        # Tz-aware but NOT actually UTC — a field named `_utc` claiming a
        # non-zero offset is a mislabeled local timestamp, never silently
        # accepted as canonical UTC evidence.
        return None, "TIMESTAMP_NOT_UTC_OFFSET_ZERO"
    return parsed, None


def _validate_deployment_evidence(value: Any) -> Optional[str]:
    """Validate `deployment_evidence` (R1.1 correction A). Returns an
    error code, or `None` if valid. Never repairs or defaults the object
    — an invalid/incomplete evidence object is a structured failure."""

    if not isinstance(value, dict):
        return "SNAPSHOT_INVALID_DEPLOYMENT_EVIDENCE_TYPE"

    for key in _DEPLOYMENT_EVIDENCE_REQUIRED_KEYS:
        if key not in value:
            return "SNAPSHOT_DEPLOYMENT_EVIDENCE_MISSING_FIELD"

    status = value["status"]
    if status not in _DEPLOYMENT_EVIDENCE_STATUSES:
        return "SNAPSHOT_INVALID_DEPLOYMENT_EVIDENCE_STATUS"

    # R1.2 correction A: closed vocabulary, never "any non-empty string."
    # `None` (unavailable) is legal; anything else must be an EXACT match
    # to one of the contract's three source labels — never trimmed,
    # normalized, or case-folded before comparison.
    source = value["source"]
    if source is not None and not _is_valid_deployment_evidence_source(source):
        return "SNAPSHOT_INVALID_DEPLOYMENT_EVIDENCE_SOURCE"

    # R1.2 correction B: whitespace-only is exactly as invalid as empty.
    evidence_ref = value["evidence_ref"]
    if evidence_ref is not None and not _is_valid_identifier(evidence_ref):
        return "SNAPSHOT_INVALID_DEPLOYMENT_EVIDENCE_REF"

    observed_at_utc = value["observed_at_utc"]
    if observed_at_utc is not None:
        _, ts_err = _parse_timestamp(observed_at_utc)
        if ts_err is not None:
            return "SNAPSHOT_INVALID_DEPLOYMENT_EVIDENCE_TIMESTAMP"

    return None


def _validate_snapshot_schema(snapshot: Dict[str, Any]) -> Optional[str]:
    """Validate VALUES, not just key presence (R1 correction C, extended
    by R1.1 correction A to the four source/runtime-evidence fields).

    Returns ``None`` if the snapshot is valid, or an explicit error code
    otherwise. Never repairs or coerces an invalid value.
    """

    schema_version = snapshot.get("schema_version")
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        return "SNAPSHOT_UNSUPPORTED_SCHEMA_VERSION"

    if not _is_valid_identifier(snapshot.get("snapshot_id")):
        return "SNAPSHOT_INVALID_SNAPSHOT_ID"

    if not _is_valid_identifier(snapshot.get("process_instance_id")):
        return "SNAPSHOT_INVALID_PROCESS_INSTANCE_ID"

    if not _is_valid_cycle(snapshot.get("cycle")):
        return "SNAPSHOT_INVALID_CYCLE"

    _, ts_err = _parse_timestamp(snapshot.get("generated_at_utc"))
    if ts_err is not None:
        return "SNAPSHOT_INVALID_TIMESTAMP"

    for key in _DOMAIN_KEYS:
        if not isinstance(snapshot.get(key), dict):
            return f"SNAPSHOT_INVALID_DOMAIN_TYPE_{key.upper()}"

    # R1.1 correction A — source/runtime-evidence fields. R1.2 correction
    # B: whitespace-only is exactly as invalid as empty.
    source_sha = snapshot.get("source_sha")
    if source_sha is not None and not _is_valid_identifier(source_sha):
        return "SNAPSHOT_INVALID_SOURCE_SHA"

    if snapshot.get("worktree_state") not in _WORKTREE_STATES:
        return "SNAPSHOT_INVALID_WORKTREE_STATE"

    dep_err = _validate_deployment_evidence(snapshot.get("deployment_evidence"))
    if dep_err is not None:
        return dep_err

    if snapshot.get("runtime_sha_evidence_status") not in _RUNTIME_SHA_EVIDENCE_STATUSES:
        return "SNAPSHOT_INVALID_RUNTIME_SHA_EVIDENCE_STATUS"

    return None


def _manifest_usable_for_identity(manifest: Optional[Dict[str, Any]], manifest_err: Optional[str]) -> bool:
    """R1.1 correction B: a manifest may participate in identity
    comparison only when it carries ALL of its minimum contractual
    fields with valid values — not merely a non-empty
    `process_instance_id` (the R1 defect).

    Returns `False` for anything short of a fully usable manifest — the
    caller treats that as `INSTANCE_RELATION_UNKNOWN`, never as a reason
    to fail the whole read (an unusable manifest is an identity-evidence
    gap, not necessarily a snapshot-data failure).
    """

    if manifest_err is not None or manifest is None:
        return False

    if not _is_valid_identifier(manifest.get("process_instance_id")):
        return False

    _, ts_err = _parse_timestamp(manifest.get("boot_timestamp_utc"))
    if ts_err is not None:
        return False

    pid = manifest.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False

    # source_sha's KEY must be present (the contract's minimum manifest
    # field list includes it) even though its VALUE may be null — a
    # manifest missing the key entirely is not the same as one that
    # explicitly declares "no source SHA claim." R1.2 correction B:
    # whitespace-only is exactly as invalid as empty.
    if "source_sha" not in manifest:
        return False
    source_sha = manifest["source_sha"]
    if source_sha is not None and not _is_valid_identifier(source_sha):
        return False

    if "schema_version" in manifest and manifest["schema_version"] not in _SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        return False

    return True


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

        schema_err = _validate_snapshot_schema(snapshot)
        if schema_err is not None:
            return SnapshotReadResult(
                ok=False,
                error_code=schema_err,
                error_message=f"Snapshot failed schema value validation: {schema_err}",
                retries_used=retries_used,
            )

        # R1 correction D: clock-skew/timestamp honesty. The timestamp
        # itself already passed format validation above; here we reject
        # a snapshot claiming to have been generated in the future
        # relative to this reader's clock — never silently clamped to a
        # plausible-looking zero-second age (the previous `max(0.0, ...)`
        # defect). This is a structured failure, not a fabricated value.
        parsed_ts, _ = _parse_timestamp(snapshot.get("generated_at_utc"))
        now_dt = _dt.datetime.fromtimestamp(self._now_fn(), tz=_dt.timezone.utc)
        raw_age_s = (now_dt - parsed_ts).total_seconds()
        if raw_age_s < 0:
            return SnapshotReadResult(
                ok=False,
                error_code="SNAPSHOT_CLOCK_SKEW_FUTURE_TIMESTAMP",
                error_message=(
                    "Snapshot generated_at_utc is in the future relative to this "
                    f"reader's clock (age would be {raw_age_s:.3f}s) — never "
                    "silently clamped to zero."
                ),
                retries_used=retries_used,
            )

        # §14.1/§14.2 INSTANCE_RELATION — a manifest that is missing,
        # unreadable, corrupt, OR simply not minimally usable for
        # identity purposes (R1.1 correction B: process_instance_id,
        # boot_timestamp_utc, pid, source_sha, schema_version all
        # individually valid) => UNKNOWN. Never coerced to
        # CURRENT_INSTANCE, and an unusable manifest never fails the
        # whole read with a 503 — the snapshot is still served, labeled
        # UNKNOWN/LAST_KNOWN (an identity-evidence gap, not snapshot-data
        # corruption).
        manifest_usable = _manifest_usable_for_identity(manifest, manifest_err)
        snapshot_pid = snapshot["process_instance_id"]  # already schema-validated identifier

        if not manifest_usable:
            instance_relation = INSTANCE_RELATION_UNKNOWN
        elif manifest["process_instance_id"] == snapshot_pid:
            instance_relation = INSTANCE_RELATION_CURRENT
        else:
            instance_relation = INSTANCE_RELATION_PREVIOUS

        if instance_relation == INSTANCE_RELATION_CURRENT:
            runtime_state = RUNTIME_STATE_CURRENT
            stale_reason = None
        elif instance_relation == INSTANCE_RELATION_PREVIOUS:
            # A genuine, evidenced identity mismatch on a fully usable
            # manifest: the manifest names a DIFFERENT instance than the
            # one that produced this snapshot — the only case honestly
            # describable as a producer restart. This holds regardless of
            # elapsed time (R1 correction B): a one-second-old snapshot
            # from I1 is LAST_KNOWN/PRODUCER_RESTARTED the instant the I2
            # manifest is published.
            runtime_state = RUNTIME_STATE_LAST_KNOWN
            stale_reason = STALE_REASON_PRODUCER_RESTARTED
        else:
            # UNKNOWN: a missing/corrupt/unusable manifest is evidence of
            # nothing about restart history — never mislabeled as
            # PRODUCER_RESTARTED (R1 correction B; R1.1 correction B
            # extends this to "unusable," not merely "absent").
            runtime_state = RUNTIME_STATE_LAST_KNOWN
            stale_reason = None

        return SnapshotReadResult(
            ok=True,
            snapshot=copy.deepcopy(snapshot),
            manifest=copy.deepcopy(manifest) if manifest is not None else None,
            instance_relation=instance_relation,
            runtime_state=runtime_state,
            stale_reason=stale_reason,
            snapshot_age_s=raw_age_s,
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
    "STALE_REASON_PRODUCER_RESTARTED",
    "SnapshotReadResult",
    "SafeSnapshotReader",
]
