"""Lab-only fast seeding of a valid synthetic J01 journal (qualification helper).

Builds OBSERVATION_RECORDED events with the recorder's own functions and
inserts them in one transaction, so large journals can be prepared without
O(N^2) appends. Callers must verify the result through ActivityStore.snapshot;
this helper is never an ingestion path and is not shipped in sentinel_activity.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sentinel_activity import SCHEMA_VERSION
from sentinel_activity.canonical import canonical_bytes, digest, format_utc
from sentinel_activity.contracts import candidate_from, event_hash, validate_candidate, validate_recorded
from sentinel_activity.quests import project, projection_bytes
from sentinel_activity.store import ActivityStore, DB_NAME, Limits

POLICY = {"version": "fixture-seed-policy-1", "producers": {
    "fixture-observer": {"actor_id": "fixture-observer", "actor_kind": "AGENT", "actor_version": None, "role": "OBSERVER"},
    "fixture-observer-2": {"actor_id": "fixture-observer-2", "actor_kind": "AGENT", "actor_version": None, "role": "OBSERVER"}}}
T0 = datetime(2026, 10, 20, tzinfo=timezone.utc)

def seed(root: Path, count: int, *, ledger_id="fixture-seed-journal", limits=Limits()):
    """Create a journal at root and fill it with count valid synthetic events."""
    store = ActivityStore.create(root, POLICY, ledger_id=ledger_id, limits=limits, clock=lambda: T0)
    events, previous = [], "GENESIS"
    for i in range(1, count + 1):
        producer = "fixture-observer" if i % 2 else "fixture-observer-2"
        cand = validate_candidate({
            "schema_version": SCHEMA_VERSION, "event_id": f"fixture-seed-{i}", "occurred_at_utc": None,
            "actor_id": producer, "actor_kind": "AGENT", "actor_version": None,
            "event_type": "OBSERVATION_RECORDED", "quest_id": None, "correlation_id": "fixture-seed",
            "causation_event_id": None, "source_kind": "SIMULATED", "summary": f"Synthetic observation {i}",
            "reason_declared": None, "payload": {"cost": None, "code": "FIXTURE_OBSERVATION", "related_event_id": None},
            "evidence_refs": ["fixture:seed/proof"], "authorization_ref": None})
        cand.update(ledger_id=ledger_id, producer_id=producer, ingestion_policy_version=POLICY["version"],
                    sequence=i, recorded_at_utc=format_utc(T0 + timedelta(milliseconds=i)),
                    integrity={"previous_hash": previous})
        cand["integrity"]["event_hash"] = event_hash(cand)
        validate_recorded(cand)
        previous = cand["integrity"]["event_hash"]
        events.append(cand)
    conn = sqlite3.connect(root / DB_NAME, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for e in events:
            conn.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)", (
                e["sequence"], e["event_id"], e["producer_id"],
                digest({"candidate": candidate_from(e), "producer_id": e["producer_id"]}),
                e["quest_id"], e["actor_id"], e["correlation_id"], e["recorded_at_utc"], canonical_bytes(e).decode()))
        conn.execute("UPDATE projection SET body=? WHERE id=1", (projection_bytes(project(events, POLICY)).decode(),))
        conn.commit()
    finally:
        conn.close()
    return store
