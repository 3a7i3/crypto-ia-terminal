"""Synthetic test values, not active agents or authenticated decisions."""

from sentinel_activity import SCHEMA_VERSION

NOW = "2026-10-18T08:00:00.000000Z"


def candidate(event_id="fixture-event-1", event_type="OBSERVATION_RECORDED", actor="fixture-sentinel",
              kind="AGENT", quest=None, cause=None, payload=None):
    return {
        "schema_version": SCHEMA_VERSION, "event_id": event_id,
        "occurred_at_utc": None, "actor_id": actor, "actor_kind": kind, "actor_version": None,
        "event_type": event_type, "quest_id": quest, "correlation_id": "fixture-demo",
        "causation_event_id": cause, "source_kind": "SIMULATED", "summary": "Synthetic activity",
        "reason_declared": "Synthetic declared reason", "payload": {"cost": None, **(
            {"code": "FIXTURE_OBSERVATION", "related_event_id": None} if payload is None else payload)},
        "evidence_refs": ["fixture:demo/proof"], "authorization_ref": None,
    }
