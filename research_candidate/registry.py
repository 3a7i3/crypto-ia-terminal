"""RL-CANDIDATE-01 immutable registry state and promotion validation.

Research-only machinery. No runtime/PPL/exchange imports.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .candidate import (
    CANDIDATE_EVENT_IDENTITY_SCHEMA,
    PROMOTION_REQUEST_IDENTITY_SCHEMA,
    PROMOTION_REQUEST_SCHEMA,
    CandidateValidationError,
    canonical_json_bytes,
    compute_candidate_id,
    sha256_json,
    validate_candidate,
)

CANDIDATE_STATES = frozenset(
    {
        "CANDIDATE",
        "REPLAYED",
        "SHADOW_READY",
        "QUALIFIED",
        "PROMOTED_TO_NEW_EPOCH",
        "REJECTED",
        "DORMANT",
        "RETIRED",
    }
)

TERMINAL_STATES = frozenset({"REJECTED", "DORMANT", "RETIRED"})
PROMOTION_REQUEST_STATES = frozenset(
    {
        "REQUESTED",
        "READY_FOR_AUTHORIZATION",
        "AUTHORIZED",
        "EXECUTED",
        "REJECTED",
        "CANCELLED",
    }
)

LEGAL_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "CANDIDATE": frozenset({"REPLAYED", "REJECTED", "DORMANT", "RETIRED"}),
    "REPLAYED": frozenset({"SHADOW_READY", "REJECTED", "DORMANT", "RETIRED"}),
    "SHADOW_READY": frozenset({"QUALIFIED", "REJECTED", "DORMANT", "RETIRED"}),
    "QUALIFIED": frozenset(
        {"PROMOTED_TO_NEW_EPOCH", "REJECTED", "DORMANT", "RETIRED"}
    ),
    "PROMOTED_TO_NEW_EPOCH": frozenset({"RETIRED"}),
    "REJECTED": frozenset(),
    "DORMANT": frozenset(),
    "RETIRED": frozenset(),
}


class RegistryError(ValueError):
    """Candidate registry or promotion request fails closed."""


@dataclass(frozen=True)
class PublicationResult:
    candidate_id: str
    path: Path
    disposition: str


def _require_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegistryError(f"{field} must be a non-empty string")
    return value


def _require_sha40(value: Any, *, field: str) -> str:
    import re

    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise RegistryError(f"{field} must be a lowercase 40-char Git SHA")
    return value


def _require_sha256(value: Any, *, field: str) -> str:
    import re

    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RegistryError(f"{field} must be a lowercase SHA-256")
    return value


def _sorted_unique_strings(
    value: Any,
    *,
    field: str,
    nonempty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise RegistryError(f"{field} must be a list of non-empty strings")
    if nonempty and not value:
        raise RegistryError(f"{field} must not be empty")
    if value != sorted(value):
        raise RegistryError(f"{field} must be sorted")
    if len(set(value)) != len(value):
        raise RegistryError(f"{field} contains duplicates")
    return value


def candidate_event_identity(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_event_identity_schema": CANDIDATE_EVENT_IDENTITY_SCHEMA,
        "candidate_id": event["candidate_id"],
        "candidate_transition_ordinal": event["candidate_transition_ordinal"],
        "event_type": event["event_type"],
        "previous_state": event["previous_state"],
        "new_state": event["new_state"],
        "evidence_refs": event["evidence_refs"],
        "reason_code": event["reason_code"],
    }


def compute_event_id(event: Mapping[str, Any]) -> str:
    return sha256_json(candidate_event_identity(event))


def _validate_event_shape(event: Mapping[str, Any]) -> None:
    _require_sha256(event.get("candidate_id"), field="event.candidate_id")

    registry_sequence = event.get("registry_sequence")
    if not isinstance(registry_sequence, int) or isinstance(registry_sequence, bool):
        raise RegistryError("event.registry_sequence must be an integer")
    if registry_sequence < 1:
        raise RegistryError("event.registry_sequence must be >= 1")

    ordinal = event.get("candidate_transition_ordinal")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool):
        raise RegistryError("event.candidate_transition_ordinal must be an integer")
    if ordinal < 1:
        raise RegistryError("event.candidate_transition_ordinal must be >= 1")

    if event.get("event_type") != "STATE_TRANSITION":
        raise RegistryError("V1 registry event_type must be STATE_TRANSITION")

    previous = _require_string(event.get("previous_state"), field="event.previous_state")
    new = _require_string(event.get("new_state"), field="event.new_state")
    if previous not in CANDIDATE_STATES or new not in CANDIDATE_STATES:
        raise RegistryError("event state is unsupported")

    _sorted_unique_strings(
        event.get("evidence_refs"),
        field="event.evidence_refs",
    )
    _require_string(event.get("reason_code"), field="event.reason_code")

    detail = event.get("reason_detail")
    if detail is not None and not isinstance(detail, str):
        raise RegistryError("event.reason_detail must be a string or null")

    timestamp = _require_string(event.get("timestamp_utc"), field="event.timestamp_utc")
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RegistryError("event.timestamp_utc is not valid ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise RegistryError("event.timestamp_utc must be UTC")

    expected = compute_event_id(event)
    actual = _require_sha256(event.get("event_id"), field="event.event_id")
    if actual != expected:
        raise RegistryError(
            f"event_id mismatch: expected={expected}, actual={actual}"
        )


def project_candidate_states(
    candidates: Mapping[str, Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    *,
    allow_external_promotion: bool = False,
) -> dict[str, str]:
    """Project candidate states from immutable artifacts + ordered registry events."""

    states: dict[str, str] = {}
    domains: dict[str, tuple[str, ...]] = {}

    known_ids = set(candidates)
    for candidate_id, candidate in candidates.items():
        if candidate.get("candidate_id") != candidate_id:
            raise RegistryError("candidate map key does not match candidate_id")
        try:
            validate_candidate(
                candidate,
                known_candidate_ids=known_ids,
            )
        except CandidateValidationError as exc:
            raise RegistryError(f"invalid candidate {candidate_id}: {exc}") from exc
        states[candidate_id] = "CANDIDATE"
        domains[candidate_id] = tuple(candidate["target_domains"])

    previous_registry_sequence = 0
    ordinals = {candidate_id: 0 for candidate_id in candidates}
    seen_event_ids: set[str] = set()

    for event in events:
        _validate_event_shape(event)

        sequence = int(event["registry_sequence"])
        if sequence <= previous_registry_sequence:
            raise RegistryError("registry_sequence must be globally increasing")
        previous_registry_sequence = sequence

        event_id = str(event["event_id"])
        if event_id in seen_event_ids:
            raise RegistryError("duplicate event_id")
        seen_event_ids.add(event_id)

        candidate_id = str(event["candidate_id"])
        if candidate_id not in states:
            raise RegistryError(f"unknown candidate_id {candidate_id}")

        expected_ordinal = ordinals[candidate_id] + 1
        if event["candidate_transition_ordinal"] != expected_ordinal:
            raise RegistryError(
                f"candidate_transition_ordinal must be contiguous for {candidate_id}"
            )

        current = states[candidate_id]
        if event["previous_state"] != current:
            raise RegistryError(
                f"previous_state mismatch for {candidate_id}: "
                f"expected={current}, actual={event['previous_state']}"
            )

        new = str(event["new_state"])
        if new not in LEGAL_TRANSITIONS[current]:
            raise RegistryError(f"illegal transition {current} -> {new}")

        if new in {"REPLAYED", "SHADOW_READY", "QUALIFIED"} and not event["evidence_refs"]:
            raise RegistryError(
                f"{new} transition requires exact evidence_refs"
            )

        if domains[candidate_id] == ("RESEARCH_ONLY",) and new in {
            "SHADOW_READY",
            "QUALIFIED",
            "PROMOTED_TO_NEW_EPOCH",
        }:
            raise RegistryError("RESEARCH_ONLY candidate is non-promotable")

        if new == "PROMOTED_TO_NEW_EPOCH":
            if not allow_external_promotion:
                raise RegistryError(
                    "RL-CANDIDATE registry cannot record promotion without "
                    "external promotion authority"
                )
            if not event["evidence_refs"]:
                raise RegistryError(
                    "PROMOTED_TO_NEW_EPOCH requires exact promotion evidence refs"
                )
            if event["reason_code"] != "PROMOTION_EXECUTED":
                raise RegistryError(
                    "PROMOTED_TO_NEW_EPOCH requires PROMOTION_EXECUTED reason_code"
                )

        states[candidate_id] = new
        ordinals[candidate_id] = expected_ordinal

    return states


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        raise
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def publish_candidate(
    candidates_root: str | Path,
    candidate: Mapping[str, Any],
    *,
    evidence_catalog: Mapping[str, set[str]] | None = None,
    known_candidate_ids: set[str] | None = None,
) -> PublicationResult:
    """Write one immutable candidate artifact or prove identical idempotency."""

    try:
        candidate_id = validate_candidate(
            candidate,
            evidence_catalog=evidence_catalog,
            known_candidate_ids=known_candidate_ids,
        )
    except CandidateValidationError as exc:
        raise RegistryError(str(exc)) from exc

    encoded = json.dumps(
        candidate,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"

    root = Path(candidates_root).resolve()
    path = root / candidate_id / "candidate.json"

    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise RegistryError(f"cannot read existing candidate: {exc}") from exc
        if existing == encoded:
            return PublicationResult(
                candidate_id=candidate_id,
                path=path,
                disposition="ALREADY_EXISTS_IDENTICAL",
            )
        raise RegistryError("CANDIDATE_ID_COLLISION_OR_CORRUPTION")

    try:
        _write_exclusive(path, encoded)
    except FileExistsError:
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise RegistryError(f"cannot read concurrent candidate: {exc}") from exc
        if existing == encoded:
            return PublicationResult(
                candidate_id=candidate_id,
                path=path,
                disposition="ALREADY_EXISTS_IDENTICAL",
            )
        raise RegistryError("CANDIDATE_ID_COLLISION_OR_CORRUPTION")

    return PublicationResult(
        candidate_id=candidate_id,
        path=path,
        disposition="CREATED",
    )


def promotion_request_identity(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "promotion_request_identity_schema": PROMOTION_REQUEST_IDENTITY_SCHEMA,
        "candidate_id": request["candidate_id"],
        "qualification_evidence_refs": request["qualification_evidence_refs"],
        "target_environment": request["target_environment"],
        "target_source_sha": request["target_source_sha"],
        "target_config_hash": request["target_config_hash"],
        "baseline_epoch": request["baseline_epoch"],
        "requested_new_epoch": request["requested_new_epoch"],
        "rollback_boundary_identity": request["rollback_boundary_identity"],
        "preflight_contract_version": request["preflight_contract_version"],
    }


def compute_promotion_request_id(request: Mapping[str, Any]) -> str:
    return sha256_json(promotion_request_identity(request))


def validate_promotion_request(
    request: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    candidate_state: str,
    actor_boundary: str = "RL_CANDIDATE",
) -> str:
    if request.get("promotion_request_schema") != PROMOTION_REQUEST_SCHEMA:
        raise RegistryError("unsupported promotion_request_schema")

    candidate_id = _require_sha256(
        request.get("candidate_id"),
        field="promotion_request.candidate_id",
    )
    if candidate_id != candidate.get("candidate_id"):
        raise RegistryError("promotion request candidate_id mismatch")

    if candidate_state != "QUALIFIED":
        raise RegistryError("promotion request requires QUALIFIED candidate state")
    if request.get("candidate_state") != "QUALIFIED":
        raise RegistryError("promotion request must record candidate_state=QUALIFIED")

    if tuple(candidate.get("target_domains", ())) == ("RESEARCH_ONLY",):
        raise RegistryError("RESEARCH_ONLY candidate cannot be promoted")

    refs = _sorted_unique_strings(
        request.get("qualification_evidence_refs"),
        field="promotion_request.qualification_evidence_refs",
        nonempty=True,
    )
    for ref in refs:
        _require_sha256(ref, field="promotion_request.qualification_evidence_refs")

    if request.get("target_environment") != "PAPER_NEW_EPOCH":
        raise RegistryError("promotion target must be PAPER_NEW_EPOCH")

    target_source_sha = _require_sha40(
        request.get("target_source_sha"),
        field="promotion_request.target_source_sha",
    )
    target_config_hash = _require_sha256(
        request.get("target_config_hash"),
        field="promotion_request.target_config_hash",
    )

    components = candidate.get("proposal", {}).get("components", [])
    proposed_source_shas = {
        component.get("proposed_source_sha")
        for component in components
        if isinstance(component, dict) and component.get("kind") == "CODE_PATCH"
    }
    if "NOT_IMPLEMENTED" in proposed_source_shas:
        raise RegistryError(
            "candidate has no exact implemented source identity for promotion"
        )
    implemented = {value for value in proposed_source_shas if isinstance(value, str)}
    if len(implemented) > 1:
        raise RegistryError(
            "candidate CODE_PATCH components disagree on proposed source SHA"
        )
    expected_source_sha = (
        next(iter(implemented))
        if implemented
        else candidate.get("baseline", {}).get("source_code_sha")
    )
    if target_source_sha != expected_source_sha:
        raise RegistryError(
            "promotion target_source_sha does not match candidate source identity"
        )

    candidate_config_hash = candidate.get("candidate_config_hash")
    if candidate_config_hash == "NOT_AVAILABLE":
        raise RegistryError(
            "candidate_config_hash is NOT_AVAILABLE; promotion requires a successor "
            "candidate with exact material config identity"
        )
    if target_config_hash != candidate_config_hash:
        raise RegistryError(
            "promotion target_config_hash does not match candidate_config_hash"
        )

    baseline_epoch = _require_string(
        request.get("baseline_epoch"),
        field="promotion_request.baseline_epoch",
    )
    candidate_baseline_epoch = candidate.get("baseline", {}).get("paper_epoch_id")
    if (
        candidate_baseline_epoch is not None
        and baseline_epoch != candidate_baseline_epoch
    ):
        raise RegistryError("promotion baseline_epoch does not match candidate baseline")

    new_epoch = request.get("requested_new_epoch")
    if not isinstance(new_epoch, dict):
        raise RegistryError("requested_new_epoch must be an object")
    kind = new_epoch.get("kind")
    if kind == "EXACT_NEW_EPOCH":
        new_epoch_id = _require_string(
            new_epoch.get("paper_epoch_id"),
            field="requested_new_epoch.paper_epoch_id",
        )
        if new_epoch_id == baseline_epoch:
            raise RegistryError("promotion must target a new PAPER epoch")
    elif kind == "EPOCH_CREATION_INTENT":
        _require_sha256(
            new_epoch.get("intent_id"),
            field="requested_new_epoch.intent_id",
        )
    else:
        raise RegistryError("unsupported requested_new_epoch kind")

    rollback = request.get("rollback_boundary_identity")
    if not isinstance(rollback, dict) or not rollback:
        raise RegistryError("rollback_boundary_identity must be a non-empty object")

    rollback_plan = request.get("rollback_plan")
    if not isinstance(rollback_plan, dict) or not rollback_plan:
        raise RegistryError("rollback_plan must be a non-empty object")

    if request.get("required_operator_authorization") is not True:
        raise RegistryError("required_operator_authorization must be true")

    _sorted_unique_strings(
        request.get("required_preflight_checks"),
        field="promotion_request.required_preflight_checks",
        nonempty=True,
    )
    _require_string(
        request.get("preflight_contract_version"),
        field="promotion_request.preflight_contract_version",
    )

    status = _require_string(request.get("status"), field="promotion_request.status")
    if status not in PROMOTION_REQUEST_STATES:
        raise RegistryError(f"unsupported promotion request status {status!r}")
    if actor_boundary == "RL_CANDIDATE" and status not in {
        "REQUESTED",
        "READY_FOR_AUTHORIZATION",
        "REJECTED",
        "CANCELLED",
    }:
        raise RegistryError(
            "RL_CANDIDATE cannot record AUTHORIZED or EXECUTED promotion state"
        )

    expected = compute_promotion_request_id(request)
    actual = _require_sha256(
        request.get("promotion_request_id"),
        field="promotion_request.promotion_request_id",
    )
    if actual != expected:
        raise RegistryError(
            f"promotion_request_id mismatch: expected={expected}, actual={actual}"
        )
    return actual
