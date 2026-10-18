"""Closed activity events; no permission is conveyed by a valid event.

ActorSpec/AgentRegistryEvent identities remain owned by A1. A fixture actor
is not an A1 registration. All ingestion in J01 is synthetic only.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from sentinel_activity import SCHEMA_VERSION
from sentinel_activity.canonical import canonical_bytes, digest, parse_utc, pure_int, require


class EventType(str, Enum):
    QUEST_PROPOSED = "QUEST_PROPOSED"
    QUEST_APPROVED = "QUEST_APPROVED"
    QUEST_REJECTED = "QUEST_REJECTED"
    QUEST_PUBLISHED = "QUEST_PUBLISHED"
    QUEST_ACCEPTED = "QUEST_ACCEPTED"
    QUEST_DECLINED = "QUEST_DECLINED"
    WORK_STARTED = "WORK_STARTED"
    ARTIFACT_SUBMITTED = "ARTIFACT_SUBMITTED"
    REVIEW_PASSED = "REVIEW_PASSED"
    REVIEW_FAILED = "REVIEW_FAILED"
    QUEST_COMPLETED = "QUEST_COMPLETED"
    QUEST_FAILED = "QUEST_FAILED"
    OBSERVATION_RECORDED = "OBSERVATION_RECORDED"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    RUN_INTERRUPTED = "RUN_INTERRUPTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    POLICY_DENIED = "POLICY_DENIED"
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"


SOURCE_KINDS = frozenset({"SIMULATED", "AGENT_REPORTED", "SYSTEM_OBSERVED", "OPERATOR_DECISION"})
ACTOR_KINDS = frozenset({"AGENT", "OPERATOR", "SYSTEM"})
CANDIDATE_FIELDS = frozenset({
    "schema_version", "event_id", "occurred_at_utc", "actor_id", "actor_kind", "actor_version",
    "event_type", "quest_id", "correlation_id", "causation_event_id", "source_kind", "summary",
    "reason_declared", "payload", "evidence_refs", "authorization_ref",
})
RECORDER_FIELDS = frozenset({
    "ledger_id", "producer_id", "ingestion_policy_version", "sequence", "recorded_at_utc", "integrity",
})
PAYLOAD_FIELDS = {
    "QUEST_PROPOSED": {"title", "scope", "budget_units", "acceptance_criteria"},
    "QUEST_APPROVED": {"expected_revision", "proposal_event_id"},
    "QUEST_REJECTED": {"expected_revision", "proposal_event_id"},
    "QUEST_PUBLISHED": {"expected_revision", "approval_event_id"},
    "QUEST_ACCEPTED": {"expected_revision"},
    "QUEST_DECLINED": {"expected_revision"},
    "WORK_STARTED": {"expected_revision", "attempt"},
    "ARTIFACT_SUBMITTED": {"expected_revision", "attempt", "artifact_ref", "artifact_sha256"},
    "REVIEW_PASSED": {"expected_revision", "submission_event_id"},
    "REVIEW_FAILED": {"expected_revision", "submission_event_id"},
    "QUEST_COMPLETED": {"expected_revision", "review_event_id"},
    "QUEST_FAILED": {"expected_revision", "reason_code"},
}
SUPERVISION_FIELDS = {"code", "related_event_id"}
QUEST_TYPES = frozenset(PAYLOAD_FIELDS)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_HASH = re.compile(r"[0-9a-f]{64}")
_REF = re.compile(
    r"(?:fixture:[a-z0-9][a-z0-9_.:/-]{0,180}|sha256:[0-9a-f]{64}|git:commit:[0-9a-f]{40}|"
    r"github:issue:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*|"
    r"github:pr:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*@[0-9a-f]{40})"
)


def identifier(value: Any) -> bool:
    return type(value) is str and _ID.fullmatch(value) is not None


def hash_value(value: Any) -> bool:
    return type(value) is str and _HASH.fullmatch(value) is not None


def reference(value: Any) -> bool:
    return type(value) is str and len(value) <= 240 and _REF.fullmatch(value) is not None


def text(value: Any, maximum: int) -> bool:
    return type(value) is str and 0 < len(value) <= maximum and value == value.strip()


def candidate_from(event: dict) -> dict:
    return {key: event[key] for key in CANDIDATE_FIELDS}


def validate_candidate(event: Any) -> dict:
    # This canonical round-trip also freezes mutable caller input.
    from sentinel_activity.canonical import strict_loads

    canonical_bytes(event, 24_576)
    require(type(event) is dict and set(event) == CANDIDATE_FIELDS)
    require(event["schema_version"] == SCHEMA_VERSION, "UNKNOWN_VERSION")
    for key in ("event_id", "actor_id"):
        require(identifier(event[key]))
    for key in ("quest_id", "correlation_id", "causation_event_id"):
        require(event[key] is None or identifier(event[key]))
    require(type(event["actor_kind"]) is str and event["actor_kind"] in ACTOR_KINDS)
    require(event["actor_version"] is None or text(event["actor_version"], 128))
    require(type(event["source_kind"]) is str and event["source_kind"] in SOURCE_KINDS)
    require(type(event["event_type"]) is str and event["event_type"] in {item.value for item in EventType})
    require(text(event["summary"], 300))
    require(event["reason_declared"] is None or text(event["reason_declared"], 1000))
    if event["occurred_at_utc"] is not None:
        parse_utc(event["occurred_at_utc"])
    refs = event["evidence_refs"]
    require(type(refs) is list and len(refs) <= 16 and all(reference(ref) for ref in refs),
            "EVIDENCE_INVALID")
    require(refs == sorted(set(refs)), "EVIDENCE_INVALID")
    require(event["authorization_ref"] is None or reference(event["authorization_ref"]),
            "EVIDENCE_INVALID")
    payload = event["payload"]
    require(type(payload) is dict)
    expected = PAYLOAD_FIELDS.get(event["event_type"], SUPERVISION_FIELDS) | {"cost"}
    require(set(payload) == expected)
    canonical_bytes(payload, 16_384)
    # Cost accounting and AIC are out of J01. Unknown is explicit, never zero.
    require(payload["cost"] is None)
    for key, value in payload.items():
        if key == "expected_revision":
            require(pure_int(value, 1))
        elif key == "attempt":
            require(pure_int(value, 1, 1000))
        elif key == "budget_units":
            require(pure_int(value, 1, 1_000_000))
        elif key in {"scope", "acceptance_criteria"}:
            require(type(value) is list and 0 < len(value) <= 16)
            require(all(text(v, 300) for v in value))
            require(value == sorted(set(value)))
        elif key in {"title", "code", "reason_code"}:
            require(text(value, 300))
        elif key.endswith("event_id"):
            require(value is None and key == "related_event_id" or identifier(value))
        elif key == "artifact_ref":
            require(reference(value), "EVIDENCE_INVALID")
        elif key == "artifact_sha256":
            require(hash_value(value), "EVIDENCE_INVALID")
    require((event["quest_id"] is not None) == (event["event_type"] in QUEST_TYPES))
    return strict_loads(canonical_bytes(event))


def event_hash(event: dict) -> str:
    material = dict(event)
    material["integrity"] = {"previous_hash": event["integrity"]["previous_hash"]}
    return digest(material)


def validate_recorded(event: Any) -> None:
    canonical_bytes(event)
    require(type(event) is dict and set(event) == CANDIDATE_FIELDS | RECORDER_FIELDS)
    validate_candidate(candidate_from(event))
    for key in ("ledger_id", "producer_id", "ingestion_policy_version"):
        require(identifier(event[key]))
    require(pure_int(event["sequence"], 1))
    recorded = parse_utc(event["recorded_at_utc"])
    if event["occurred_at_utc"] is not None:
        require((parse_utc(event["occurred_at_utc"]) - recorded).total_seconds() <= 120,
                "INVALID_TIME")
    integrity = event["integrity"]
    require(type(integrity) is dict and set(integrity) == {"previous_hash", "event_hash"})
    require(hash_value(integrity["event_hash"]))
    require(integrity["previous_hash"] == "GENESIS" if event["sequence"] == 1
            else hash_value(integrity["previous_hash"]))
    require(event_hash(event) == integrity["event_hash"], "CORRUPTED")
