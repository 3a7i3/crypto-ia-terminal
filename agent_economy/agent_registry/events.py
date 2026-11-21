"""AgentRegistryEvent V1: deterministic identities and local validation.

Implements A1 sections 7.2 and 8 and the event-local parts of AE-01 ... AE-07,
AE-09 and AC-02/AC-03. Rules that need the registry history (sequence,
projected state, referenced specs) live in ``integrity``. This module verifies
events; it never emits one and defines no registrar (Q1 stays UNRESOLVED).
"""

from __future__ import annotations

from typing import Any

from .canonical import (
    AgentRegistryError,
    compile_schema_pattern,
    find_float,
    is_pure_int,
    iter_strings,
    parse_utc_timestamp,
    sha256_hex,
    text_violation,
)

EVENT_SCHEMA = "AGENT_REGISTRY_EVENT_V1"
EVENT_IDENTITY_SCHEMA = "agent-econ.a1.agent-event-identity.v1"
GENESIS = "GENESIS"

EVENT_FIELDS = (
    "event_schema",
    "event_id",
    "registry_sequence",
    "agent_transition_ordinal",
    "agent_id",
    "agent_spec_id",
    "spec_artifact_hash",
    "event_type",
    "previous_state",
    "new_state",
    "reason_code",
    "reason_detail",
    "evidence_refs",
    "occurred_at_utc",
    "previous_event_hash",
    "event_hash",
)
# Fields of the event identity document (A1 section 8.3). Excluded on purpose:
# registry_sequence, occurred_at_utc, reason_detail, spec_artifact_hash, hashes.
EVENT_IDENTITY_FIELDS = (
    "agent_id",
    "agent_transition_ordinal",
    "event_type",
    "previous_state",
    "new_state",
    "agent_spec_id",
    "evidence_refs",
    "reason_code",
)

AGENT_REGISTERED = "AGENT_REGISTERED"
AGENT_SPEC_REVISED = "AGENT_SPEC_REVISED"
AGENT_SUSPENDED = "AGENT_SUSPENDED"
AGENT_REINSTATED = "AGENT_REINSTATED"
AGENT_RETIRED = "AGENT_RETIRED"
EVENT_TYPES = frozenset(
    {
        AGENT_REGISTERED,
        AGENT_SPEC_REVISED,
        AGENT_SUSPENDED,
        AGENT_REINSTATED,
        AGENT_RETIRED,
    }
)

# Agent states. There is deliberately no ACTIVE / RUNNING state (A1 section 7.1).
REGISTERED = "REGISTERED"
SUSPENDED = "SUSPENDED"
RETIRED = "RETIRED"
AGENT_STATES = frozenset({REGISTERED, SUSPENDED, RETIRED})

REVISION_REASON_CODES = frozenset(
    {
        "SPEC_REVISION_ESCALATING",
        "SPEC_REVISION_NON_ESCALATING",
        "SPEC_REVISION_REDUCING",
    }
)
REASON_CODES = frozenset(
    {
        "REGISTRATION_INITIAL",
        "REINSTATEMENT_GOVERNANCE",
        "RETIREMENT_GOVERNANCE",
        "RETIREMENT_SUPERSEDED_BY_NEW_AGENT",
        "SUSPENSION_GOVERNANCE",
        "SUSPENSION_INCIDENT",
    }
    | REVISION_REASON_CODES
)

# event_type -> (allowed previous_state values, new_state rule, reason codes).
# For a revision the new state must equal the previous one (AE-05).
TRANSITIONS: dict[str, tuple[frozenset[Any], frozenset[str] | None, frozenset[str]]] = {
    AGENT_REGISTERED: (
        frozenset({None}),
        frozenset({REGISTERED}),
        frozenset({"REGISTRATION_INITIAL"}),
    ),
    AGENT_SPEC_REVISED: (
        frozenset({REGISTERED, SUSPENDED}),
        None,
        REVISION_REASON_CODES,
    ),
    AGENT_SUSPENDED: (
        frozenset({REGISTERED}),
        frozenset({SUSPENDED}),
        frozenset({"SUSPENSION_GOVERNANCE", "SUSPENSION_INCIDENT"}),
    ),
    AGENT_REINSTATED: (
        frozenset({SUSPENDED}),
        frozenset({REGISTERED}),
        frozenset({"REINSTATEMENT_GOVERNANCE"}),
    ),
    AGENT_RETIRED: (
        frozenset({REGISTERED, SUSPENDED}),
        frozenset({RETIRED}),
        frozenset({"RETIREMENT_GOVERNANCE", "RETIREMENT_SUPERSEDED_BY_NEW_AGENT"}),
    ),
}

# Patterns copied verbatim from AGENT_ECON_A1_AGENT_REGISTRY_EVENT_V1.schema.json
# (a test compares them with the schema file).
PATTERN_SHA256 = "^[0-9a-f]{64}$"
PATTERN_PREVIOUS_EVENT_HASH = "^(GENESIS|[0-9a-f]{64})$"
PATTERN_EVIDENCE_REF = (
    "^(github:issue:[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}"
    "#[1-9][0-9]{0,8}|github:pr:[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/"
    "[A-Za-z0-9._-]{1,100}#[1-9][0-9]{0,8}@[0-9a-f]{40}|git:commit:[0-9a-f]{40}|"
    "sha256:[0-9a-f]{64})$"
)
PATTERN_OCCURRED_AT = (
    "^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):"
    "[0-5][0-9]:[0-5][0-9](\\.[0-9]{1,6})?Z$"
)

_SHA256 = compile_schema_pattern(PATTERN_SHA256)
_PREVIOUS_HASH = compile_schema_pattern(PATTERN_PREVIOUS_EVENT_HASH)
_EVIDENCE_REF = compile_schema_pattern(PATTERN_EVIDENCE_REF)
_OCCURRED_AT = compile_schema_pattern(PATTERN_OCCURRED_AT)

MAX_EVIDENCE_REFS = 32
MAX_REASON_DETAIL = 1000


def _fail(code: str, detail: str) -> AgentRegistryError:
    return AgentRegistryError(code, detail)


def compute_event_id(event: dict[str, Any]) -> str:
    """A1 section 8.3: identity of the logical transition."""
    missing = [name for name in EVENT_IDENTITY_FIELDS if name not in event]
    if missing:
        raise _fail("EVENT_SCHEMA_VIOLATION", f"missing identity fields: {missing}")
    document: dict[str, Any] = {"agent_event_identity_schema": EVENT_IDENTITY_SCHEMA}
    for name in EVENT_IDENTITY_FIELDS:
        document[name] = event[name]
    return sha256_hex(document)


def compute_event_hash(event: dict[str, Any]) -> str:
    """A1 section 8.6: SHA-256 of the canonical event without ``event_hash``."""
    if not isinstance(event, dict):
        raise _fail("EVENT_SCHEMA_VIOLATION", "event must be an object")
    return sha256_hex({k: v for k, v in event.items() if k != "event_hash"})


def has_source_anchor(evidence_refs: list[str]) -> bool:
    """AE-09: a PR-at-sha or commit reference anchors the spec in governed source."""
    return any(ref.startswith(("github:pr:", "git:commit:")) for ref in evidence_refs)


def _validate_evidence(refs: Any) -> list[str]:
    if not isinstance(refs, list):
        raise _fail("EVENT_SCHEMA_VIOLATION", "evidence_refs must be a list")
    if not refs or len(refs) > MAX_EVIDENCE_REFS:
        raise _fail("EVIDENCE_INVALID", "evidence_refs must hold 1..32 references")
    for ref in refs:
        if not isinstance(ref, str) or not _EVIDENCE_REF.fullmatch(ref):
            raise _fail("EVIDENCE_INVALID", f"reference outside the closed grammar: {ref!r}")
    if len(set(refs)) != len(refs):
        raise _fail("EVIDENCE_INVALID", "evidence_refs contains duplicates")
    if refs != sorted(refs):
        raise _fail("EVIDENCE_INVALID", "evidence_refs is not sorted")
    return refs


def validate_event(event: Any) -> None:
    """Validate everything knowable from one event alone. Raises on violation."""
    try:
        _validate_event(event)
    except RecursionError as exc:
        raise _fail("EVENT_SCHEMA_VIOLATION", "event nesting is too deep") from exc


def _validate_event(event: Any) -> None:
    if not isinstance(event, dict):  # AE-01
        raise _fail("EVENT_SCHEMA_VIOLATION", "event must be an object")
    missing = sorted(set(EVENT_FIELDS) - set(event))
    unknown = sorted(set(event) - set(EVENT_FIELDS))
    if missing:
        raise _fail("EVENT_SCHEMA_VIOLATION", f"missing fields {missing}")
    if unknown:
        raise _fail("EVENT_SCHEMA_VIOLATION", f"unknown fields {unknown}")

    path = find_float(event)  # AE-02
    if path is not None:
        raise _fail("EVENT_NUMERIC_AMBIGUITY", f"float at {path}")
    for field in ("registry_sequence", "agent_transition_ordinal"):
        if isinstance(event[field], bool):
            raise _fail("EVENT_NUMERIC_AMBIGUITY", f"{field} is a bool")
        if not is_pure_int(event[field]) or event[field] < 1:
            raise _fail("EVENT_SCHEMA_VIOLATION", f"{field} must be an integer >= 1")

    for where, text in iter_strings(event):
        violation = text_violation(text)
        if violation:
            raise _fail("EVENT_SCHEMA_VIOLATION", f"{where}: {violation}")

    if event["event_schema"] != EVENT_SCHEMA:
        raise _fail("EVENT_SCHEMA_VIOLATION", "event_schema must be AGENT_REGISTRY_EVENT_V1")
    for field in ("event_id", "agent_id", "agent_spec_id", "spec_artifact_hash", "event_hash"):
        value = event[field]
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise _fail("EVENT_SCHEMA_VIOLATION", f"{field} must be lowercase sha256")
    previous_hash = event["previous_event_hash"]
    if not isinstance(previous_hash, str) or not _PREVIOUS_HASH.fullmatch(previous_hash):
        raise _fail("EVENT_SCHEMA_VIOLATION", "previous_event_hash is malformed")
    event_type = event["event_type"]
    if not isinstance(event_type, str) or event_type not in EVENT_TYPES:
        raise _fail("EVENT_SCHEMA_VIOLATION", f"unknown event_type {event_type!r}")
    previous_state, new_state = event["previous_state"], event["new_state"]
    if previous_state is not None and (
        not isinstance(previous_state, str) or previous_state not in {REGISTERED, SUSPENDED}
    ):
        raise _fail("EVENT_SCHEMA_VIOLATION", f"unknown previous_state {previous_state!r}")
    if not isinstance(new_state, str) or new_state not in AGENT_STATES:
        raise _fail("EVENT_SCHEMA_VIOLATION", f"unknown new_state {new_state!r}")
    reason_code = event["reason_code"]
    if not isinstance(reason_code, str) or reason_code not in REASON_CODES:
        raise _fail("EVENT_SCHEMA_VIOLATION", f"unknown reason_code {reason_code!r}")
    detail = event["reason_detail"]
    if detail is not None and (
        not isinstance(detail, str) or len(detail) > MAX_REASON_DETAIL
    ):
        raise _fail("EVENT_SCHEMA_VIOLATION", "reason_detail must be null or <= 1000 chars")
    occurred = event["occurred_at_utc"]
    if (
        not isinstance(occurred, str)
        or not _OCCURRED_AT.fullmatch(occurred)
        or parse_utc_timestamp(occurred) is None
    ):
        raise _fail("EVENT_SCHEMA_VIOLATION", "occurred_at_utc is not ISO-8601 UTC")
    refs = _validate_evidence(event["evidence_refs"])  # AE-07

    allowed_previous, allowed_new, allowed_reasons = TRANSITIONS[event_type]
    if previous_state not in allowed_previous:  # AE-05 (table of section 7.2)
        raise _fail("ILLEGAL_TRANSITION", f"{event_type} from {previous_state!r}")
    if allowed_new is None:
        if new_state != previous_state:
            raise _fail("ILLEGAL_TRANSITION", "a revision must keep the state")
    elif new_state not in allowed_new:
        raise _fail("ILLEGAL_TRANSITION", f"{event_type} cannot lead to {new_state}")
    if reason_code not in allowed_reasons:  # AE-06
        raise _fail("REASON_CODE_MISMATCH", f"{reason_code} is not allowed for {event_type}")

    ordinal = event["agent_transition_ordinal"]
    if (event_type == AGENT_REGISTERED and ordinal != 1) or (
        event_type != AGENT_REGISTERED and ordinal < 2
    ):
        raise _fail("ORDINAL_GAP", f"ordinal {ordinal} is impossible for {event_type}")
    if (event["registry_sequence"] == 1) != (previous_hash == GENESIS):  # AC-02
        raise _fail("CHAIN_BREAK", "previous_event_hash is GENESIS iff sequence is 1")

    needs_anchor = event_type in {AGENT_REGISTERED, AGENT_REINSTATED} or (
        reason_code == "SPEC_REVISION_ESCALATING"
    )
    if needs_anchor and not has_source_anchor(refs):  # AE-09
        raise _fail("SOURCE_ANCHOR_MISSING", "a PR@sha or commit reference is required")

    if event["event_id"] != compute_event_id(event):  # AE-03
        raise _fail("EVENT_ID_MISMATCH", "event_id does not match its recomputation")
    if event["event_hash"] != compute_event_hash(event):  # AE-04
        raise _fail("EVENT_HASH_MISMATCH", "event_hash does not match its recomputation")
