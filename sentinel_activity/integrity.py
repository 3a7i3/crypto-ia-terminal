"""Pure bounded verification. A valid prefix is not a completeness attestation."""

from __future__ import annotations

from sentinel_activity.canonical import LedgerError, digest, parse_utc, require
from sentinel_activity.contracts import validate_recorded
from sentinel_activity.policy import admit, validate_policy
from sentinel_activity.quests import project


def validate_causation(event: dict, seen: dict) -> None:
    cause = event["causation_event_id"]
    if cause is not None:
        require(cause in seen, "CAUSATION_INVALID")
        parent = seen[cause]
        require(parent["quest_id"] == event["quest_id"] and parent["correlation_id"] == event["correlation_id"],
                "CAUSATION_INVALID")
    related = event["payload"].get("related_event_id")
    if related is not None:
        require(related in seen and related == cause, "CAUSATION_INVALID")


def verify_events(meta: dict, events: list[dict]) -> dict:
    """Revalidate all producer bindings, event hashes, order and quest rules."""
    try:
        validate_policy(meta["policy"])
        require(meta["mode"] == "SIMULATED_ONLY" and meta["policy_hash"] == digest(meta["policy"]), "CORRUPTED")
        require(type(events) is list and len(events) <= meta["limits"]["max_events"], "CORRUPTED")
        seen, counts = {}, {}
        previous = "GENESIS"
        previous_recorded = None
        for sequence, event in enumerate(events, 1):
            validate_recorded(event)
            admit(event, event["producer_id"], meta["policy"])
            require(event["ledger_id"] == meta["ledger_id"] and event["ingestion_policy_version"] ==
                    meta["policy"]["version"], "CORRUPTED")
            require(event["sequence"] == sequence and event["integrity"]["previous_hash"] == previous, "CORRUPTED")
            require(event["event_id"] not in seen, "CORRUPTED")
            validate_causation(event, seen)
            recorded = parse_utc(event["recorded_at_utc"])
            require(previous_recorded is None or recorded >= previous_recorded, "CORRUPTED")
            previous_recorded = recorded
            counts[event["producer_id"]] = counts.get(event["producer_id"], 0) + 1
            require(counts[event["producer_id"]] <= meta["limits"]["per_producer"], "CORRUPTED")
            previous = event["integrity"]["event_hash"]
            seen[event["event_id"]] = event
        return project(events, meta["policy"])
    except LedgerError as exc:
        if exc.code == "UNKNOWN_VERSION":
            raise
        raise LedgerError("CORRUPTED") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise LedgerError("CORRUPTED") from exc


def report(meta: dict, events: list[dict]) -> dict:
    verify_events(meta, events)
    warnings = []
    previous = None
    for event in events:
        occurred = event["occurred_at_utc"]
        if occurred is not None:
            current = parse_utc(occurred)
            if previous is not None and current < previous:
                warnings.append({"code": "TIMESTAMP_REGRESSION", "sequence": event["sequence"]})
            previous = current
    return {
        "status": "PREFIX_VERIFIED" if events else "NO_DATA", "mode": "SIMULATED_ONLY",
        "ledger_id": meta["ledger_id"], "event_count": len(events),
        "last_sequence": len(events), "head_hash": events[-1]["integrity"]["event_hash"] if events else "GENESIS",
        "completeness": "UNKNOWN", "authenticity": "NOT_PROVEN", "anchor": "NOT_CONFIGURED",
        "warnings": warnings,
    }
