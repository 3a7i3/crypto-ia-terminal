"""Pure verification of an ordered AgentRegistryEvent sequence (A1 section 9).

``verify_chain(events, specs)`` checks AC-01 ... AC-06 and the history-dependent
parts of AE-05 ... AE-11 against the exact published spec artifacts. Any
violation yields ``NOT_CERTIFIABLE``: nothing is repaired, no event is skipped
and no partial "healthy" state is returned.

A structurally valid chain proves only integrity. It does NOT prove writer
authenticity (registrar: UNRESOLVED), tail completeness (anti-rollback anchor:
UNRESOLVED) or human authority; it is therefore never upgraded to AVAILABLE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .canonical import AgentRegistryError, parse_utc_timestamp, sha256_hex_of_bytes
from .events import (
    AGENT_REGISTERED,
    AGENT_REINSTATED,
    AGENT_SPEC_REVISED,
    GENESIS,
    RETIRED,
    validate_event,
)
from .publication import parse_spec_artifact
from .spec import (
    classify_revision,
    compute_spec_artifact_bytes,
    validate_agent_spec,
)

STRUCTURALLY_VALID_CHAIN = "STRUCTURALLY_VALID_CHAIN"
NOT_CERTIFIABLE = "NOT_CERTIFIABLE"
TIMESTAMP_REGRESSION = "TIMESTAMP_REGRESSION"


@dataclass(frozen=True)
class ChainWarning:
    """AC-06: reported anomaly, kept as data; never a failure on its own."""

    code: str
    registry_sequence: int
    detail: str


@dataclass(frozen=True)
class AgentFacts:
    """Contract facts of one agent after the verified events (no liveness)."""

    agent_id: str
    current_agent_spec_id: str
    state: str
    agent_transition_ordinal: int
    last_registry_sequence: int


@dataclass(frozen=True)
class ChainVerification:
    status: str
    verified_event_count: int
    last_registry_sequence: int | None
    last_event_hash: str | None
    failure_code: str | None = None
    failure_detail: str | None = None
    failure_position: int | None = None  # 1-based index of the offending event
    failure_cause: str | None = None
    warnings: tuple[ChainWarning, ...] = ()
    # Filled only when status is STRUCTURALLY_VALID_CHAIN.
    agent_facts: tuple[AgentFacts, ...] = field(default=())


@dataclass
class _AgentRecord:
    state: str
    spec_id: str
    spec: dict[str, Any]
    ordinal: int
    last_sequence: int


def _fail(code: str, detail: str, **kwargs: Any) -> AgentRegistryError:
    return AgentRegistryError(code, detail, **kwargs)


def _load_artifact(
    event: dict[str, Any],
    specs: Mapping[str, bytes],
    recorded_hashes: dict[str, str],
    *,
    full_validation: bool,
) -> dict[str, Any]:
    """AE-08 / AE-11: exact published bytes, bound to the event by hash."""
    spec_id = event["agent_spec_id"]
    raw = specs.get(spec_id)
    if raw is None:
        raise _fail("SPEC_REFERENCE_INVALID", f"spec {spec_id} is not published")
    if not isinstance(raw, (bytes, bytearray)):
        raise _fail("SPEC_REFERENCE_INVALID", "published artifact must be bytes")
    raw = bytes(raw)
    event_hash_value = event["spec_artifact_hash"]
    known = recorded_hashes.get(spec_id)
    if known is not None and known != event_hash_value:
        raise _fail(
            "AGENT_SPEC_PROVENANCE_CONFLICT",
            "two artifacts are bound to the same agent_spec_id",
        )
    if sha256_hex_of_bytes(raw) != event_hash_value:
        raise _fail(
            "SPEC_ARTIFACT_HASH_MISMATCH",
            "spec_artifact_hash is not the SHA-256 of the exact artifact bytes",
        )
    try:
        spec = parse_spec_artifact(raw)
        if full_validation:
            identities = validate_agent_spec(spec)
            if identities.agent_spec_id != spec_id:
                raise _fail("SPEC_REFERENCE_INVALID", "artifact is for another spec")
            if compute_spec_artifact_bytes(spec) != raw:
                raise _fail(
                    "SPEC_REFERENCE_INVALID",
                    "artifact is not in the certified publication form",
                )
    except AgentRegistryError as exc:
        if exc.code == "SPEC_REFERENCE_INVALID":
            raise
        raise _fail(
            "SPEC_REFERENCE_INVALID",
            f"referenced spec is invalid: {exc.detail}",
            cause=exc.code,
        ) from exc
    if spec.get("agent_spec_id") != spec_id or spec.get("agent_id") != event["agent_id"]:
        raise _fail("SPEC_REFERENCE_INVALID", "artifact identity differs from the event")
    return spec


def _verify_event(
    position: int,
    event: Any,
    specs: Mapping[str, bytes],
    agents: dict[str, _AgentRecord],
    seen_event_ids: set[str],
    recorded_hashes: dict[str, str],
    previous_hash: str | None,
) -> dict[str, Any]:
    validate_event(event)  # AE-01 ... AE-07, AE-09, AE-03, AE-04, AC-02 (local)

    if event["registry_sequence"] != position:  # AC-01
        raise _fail(
            "SEQUENCE_GAP_OR_DUPLICATE",
            f"expected registry_sequence {position}, got {event['registry_sequence']}",
        )
    expected_previous = GENESIS if previous_hash is None else previous_hash
    if event["previous_event_hash"] != expected_previous:  # AC-02
        raise _fail("CHAIN_BREAK", "previous_event_hash does not link to the prior event")
    if event["event_id"] in seen_event_ids:  # AC-04
        raise _fail("EVENT_ID_COLLISION", "event_id already appears in the chain")

    agent = agents.get(event["agent_id"])
    if agent is not None and agent.state == RETIRED:  # AC-05
        raise _fail("EVENT_AFTER_TERMINAL", "agent is already RETIRED")
    expected_ordinal = 1 if agent is None else agent.ordinal + 1  # AC-03
    if event["agent_transition_ordinal"] != expected_ordinal:
        raise _fail(
            "ORDINAL_GAP",
            f"expected ordinal {expected_ordinal}, got {event['agent_transition_ordinal']}",
        )
    current_state = None if agent is None else agent.state  # AE-05
    if event["previous_state"] != current_state:
        raise _fail(
            "ILLEGAL_TRANSITION",
            f"previous_state {event['previous_state']!r} differs from projected "
            f"state {current_state!r}",
        )

    event_type = event["event_type"]
    # REINSTATED revalidates the current spec under the schema in force (AE-08);
    # SUSPENDED / RETIRED are the safe-direction brakes and only need the exact,
    # already-bound artifact.
    full = event_type in {AGENT_REGISTERED, AGENT_SPEC_REVISED, AGENT_REINSTATED}
    spec = _load_artifact(event, specs, recorded_hashes, full_validation=full)

    if event_type == AGENT_REGISTERED:
        if spec["spec_revision"] != 1 or spec["supersedes_spec_id"] is not None:
            raise _fail("SPEC_REFERENCE_INVALID", "REGISTERED requires spec_revision 1")
    elif event_type == AGENT_SPEC_REVISED:
        if agent is None:
            raise _fail("ILLEGAL_TRANSITION", "a revision needs a registered agent")
        if (
            event["agent_spec_id"] == agent.spec_id
            or spec["supersedes_spec_id"] != agent.spec_id
            or spec["spec_revision"] != agent.spec["spec_revision"] + 1
        ):
            raise _fail(
                "SUPERSESSION_BREAK",
                "the revision must supersede the current spec as revision + 1",
            )
        if classify_revision(agent.spec, spec) != event["reason_code"]:  # AE-10
            raise _fail(
                "REVISION_CLASS_MISMATCH",
                f"computed class is {classify_revision(agent.spec, spec)}",
            )
    else:  # SUSPENDED, REINSTATED, RETIRED keep the current spec
        if agent is None:
            raise _fail("ILLEGAL_TRANSITION", f"{event_type} needs a registered agent")
        if event["agent_spec_id"] != agent.spec_id:
            raise _fail("SPEC_REFERENCE_INVALID", f"{event_type} must keep the current spec")
    return spec


def _fail_result(
    exc: AgentRegistryError,
    position: int,
    verified: int,
    last_sequence: int | None,
    last_hash: str | None,
    warnings: list[ChainWarning],
) -> ChainVerification:
    return ChainVerification(
        status=NOT_CERTIFIABLE,
        verified_event_count=verified,
        last_registry_sequence=last_sequence,
        last_event_hash=last_hash,
        failure_code=exc.code,
        failure_detail=exc.detail,
        failure_position=position,
        failure_cause=exc.cause,
        warnings=tuple(warnings),
    )


def verify_chain(
    events: Any, specs: Mapping[str, bytes] | None = None
) -> ChainVerification:
    """Verify an ordered event sequence against exact published spec artifacts.

    ``specs`` maps ``agent_spec_id`` to the exact artifact bytes. On the first
    violation the result is ``NOT_CERTIFIABLE`` and carries no agent state;
    ``verified_event_count`` then only describes the verified prefix.
    """
    specs = {} if specs is None else specs
    if not isinstance(events, (list, tuple)) or not isinstance(specs, Mapping):
        return _fail_result(
            _fail("EVENT_SCHEMA_VIOLATION", "events must be a list, specs a mapping"),
            0,
            0,
            None,
            None,
            [],
        )

    agents: dict[str, _AgentRecord] = {}
    seen_event_ids: set[str] = set()
    recorded_hashes: dict[str, str] = {}
    warnings: list[ChainWarning] = []
    previous_hash: str | None = None
    previous_time = None
    last_sequence: int | None = None

    for position, event in enumerate(events, start=1):
        try:
            spec = _verify_event(
                position, event, specs, agents, seen_event_ids, recorded_hashes, previous_hash
            )
        except AgentRegistryError as exc:
            return _fail_result(
                exc, position, position - 1, last_sequence, previous_hash, warnings
            )

        occurred = parse_utc_timestamp(event["occurred_at_utc"])
        if previous_time is not None and occurred < previous_time:  # AC-06 (WARN)
            warnings.append(
                ChainWarning(
                    TIMESTAMP_REGRESSION,
                    event["registry_sequence"],
                    "occurred_at_utc is earlier than the previous event",
                )
            )
        previous_time = occurred
        seen_event_ids.add(event["event_id"])
        recorded_hashes.setdefault(event["agent_spec_id"], event["spec_artifact_hash"])
        agents[event["agent_id"]] = _AgentRecord(
            state=event["new_state"],
            spec_id=event["agent_spec_id"],
            spec=spec,
            ordinal=event["agent_transition_ordinal"],
            last_sequence=event["registry_sequence"],
        )
        previous_hash = event["event_hash"]
        last_sequence = event["registry_sequence"]

    facts = tuple(
        AgentFacts(
            agent_id=agent_id,
            current_agent_spec_id=record.spec_id,
            state=record.state,
            agent_transition_ordinal=record.ordinal,
            last_registry_sequence=record.last_sequence,
        )
        for agent_id, record in sorted(agents.items())
    )
    return ChainVerification(
        status=STRUCTURALLY_VALID_CHAIN,
        verified_event_count=len(events),
        last_registry_sequence=last_sequence,
        last_event_hash=previous_hash,
        warnings=tuple(warnings),
        agent_facts=facts,
    )


__all__ = [
    "AgentFacts",
    "ChainVerification",
    "ChainWarning",
    "NOT_CERTIFIABLE",
    "STRUCTURALLY_VALID_CHAIN",
    "TIMESTAMP_REGRESSION",
    "verify_chain",
]
