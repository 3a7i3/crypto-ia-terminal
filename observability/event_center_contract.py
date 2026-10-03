"""Closed passive event presentation contract; no producer/runtime imports."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

MAX_BYTES = 2_097_152
MAX_RECORDS = 10_000
MAX_EVENTS_PER_SOURCE = 100
SOURCE_IDS = ("p12_alerts", "supervision_alerts", "ppl_lifecycles")
FORMATS = ("P12_ALERT_JSONL", "SUPERVISION_AUDIT_JSONL", "BURN_IN_LIFECYCLE_PROJECTION")
STATUSES = {"PRESENT", "NOT_CONFIGURED", "MISSING", "READ_ERROR", "INVALID", "OUTPUT_LIMIT"}
KINDS = {
    "DRAWDOWN", "MEMORY", "ERROR_RATE", "RECONCILE", "BOOT_BLOCKED",
    "HIGH_LATENCY", "EXCEPTION", "OTHER_ALERT", "POSITION_OPENED",
    "POSITION_CLOSED", "POSITION_UNRESOLVED",
}
SEVERITIES = {"INFO", "WARNING", "CRITICAL", "UNKNOWN"}
TOP_KEYS = {"schema_version", "product", "domain", "authority", "mode",
            "generated_at_utc", "sources", "events", "order"}
SOURCE_KEYS = {"source_id", "format", "status", "source_sha256", "records_observed",
               "events_observed", "excluded_records", "published_count", "undated_count",
               "truncated", "source_generated_at_utc", "paper_epoch_id"}
EVENT_KEYS = {"event_id", "source_id", "source_record", "kind", "severity",
              "occurred_at_utc", "time_status", "symbol", "sequence"}


def exact(value, keys) -> bool:
    return isinstance(value, dict) and set(value) == keys


def unsigned(value) -> bool:
    return type(value) is int and 0 <= value <= 9_007_199_254_740_991


def finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def utc_seconds(value) -> float | None:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value
    ):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def canonical_time(value) -> str | None:
    """Explicit timezone only; naive legacy timestamps remain unavailable."""
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return None


def event_order(event):
    stamp = utc_seconds(event["occurred_at_utc"])
    return (SOURCE_IDS.index(event["source_id"]), stamp is None,
            -(stamp or 0), -event["source_record"], event["event_id"])


def validate_event_center(doc, *, transport=False) -> bool:
    try:
        return _validate_event_center(doc, transport=transport)
    except (TypeError, ValueError, OverflowError, KeyError, RecursionError):
        return False


def _validate_event_center(doc, *, transport=False) -> bool:
    keys = TOP_KEYS | ({"snapshot_age_s", "freshness_classification"} if transport else set())
    if not exact(doc, keys):
        return False
    if (doc["schema_version"], doc["product"], doc["domain"], doc["authority"], doc["mode"], doc["order"]) != (
        "1.0.0", "EventCenterSnapshot", "event_center", "OBSERVATIONAL_PRESENTATION",
        "READ_ONLY", "SOURCE_THEN_TIME_DESC_UNDATED_LAST"
    ):
        return False
    generated = utc_seconds(doc["generated_at_utc"])
    if generated is None or not isinstance(doc["sources"], list) or len(doc["sources"]) != 3:
        return False
    if not isinstance(doc["events"], list) or len(doc["events"]) > 3 * MAX_EVENTS_PER_SOURCE:
        return False
    for index, source in enumerate(doc["sources"]):
        source_keys = SOURCE_KEYS | ({"source_age_s", "freshness_classification"} if transport else set())
        if not exact(source, source_keys) or source["source_id"] != SOURCE_IDS[index] or source["format"] != FORMATS[index]:
            return False
        if source["status"] not in STATUSES:
            return False
        if transport:
            age = source["source_age_s"]
            freshness = source["freshness_classification"]
            if source["status"] != "PRESENT":
                if age is not None or freshness != "NOT_AVAILABLE":
                    return False
            elif index < 2:
                if age is not None or freshness != "UNKNOWN":
                    return False
            elif not finite(age) or age < 0 or freshness not in {"FRESH", "STALE"}:
                return False
        nullable = SOURCE_KEYS - {"source_id", "format", "status"}
        if source["status"] != "PRESENT":
            if any(source[k] is not None for k in nullable):
                return False
            continue
        digest = source["source_sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return False
        for key in ("records_observed", "events_observed", "excluded_records", "published_count", "undated_count"):
            if not unsigned(source[key]):
                return False
        if source["records_observed"] > MAX_RECORDS or source["published_count"] > MAX_EVENTS_PER_SOURCE:
            return False
        if source["published_count"] != min(source["events_observed"], MAX_EVENTS_PER_SOURCE) or source["undated_count"] > source["events_observed"]:
            return False
        if type(source["truncated"]) is not bool or source["truncated"] != (source["events_observed"] > source["published_count"]):
            return False
        if index < 2:
            if source["records_observed"] != source["events_observed"] + source["excluded_records"]:
                return False
            if source["source_generated_at_utc"] is not None or source["paper_epoch_id"] is not None:
                return False
        else:
            stamp = utc_seconds(source["source_generated_at_utc"])
            if stamp is None or stamp > generated or not isinstance(source["paper_epoch_id"], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", source["paper_epoch_id"]):
                return False
            if source["events_observed"] != source["records_observed"] or source["excluded_records"] != 0 or source["undated_count"] != 0:
                return False
    ids, records, sequences = set(), set(), set()
    for event in doc["events"]:
        if not exact(event, EVENT_KEYS) or event["source_id"] not in SOURCE_IDS:
            return False
        source = doc["sources"][SOURCE_IDS.index(event["source_id"])]
        if source["status"] != "PRESENT" or not unsigned(event["source_record"]) or event["source_record"] < 1:
            return False
        if event["source_record"] > source["records_observed"]:
            return False
        if not isinstance(event["event_id"], str) or not re.fullmatch(r"[0-9a-f]{64}", event["event_id"]) or event["event_id"] in ids:
            return False
        ids.add(event["event_id"])
        record_key = (event["source_id"], event["source_record"])
        if record_key in records:
            return False
        records.add(record_key)
        if event["kind"] not in KINDS or event["severity"] not in SEVERITIES:
            return False
        stamp = utc_seconds(event["occurred_at_utc"])
        if event["time_status"] == "PRESENT":
            if stamp is None or stamp > generated:
                return False
        elif event["time_status"] != "UNKNOWN" or event["occurred_at_utc"] is not None:
            return False
        if event["source_id"] == "ppl_lifecycles":
            if event["kind"] not in {"POSITION_OPENED", "POSITION_CLOSED", "POSITION_UNRESOLVED"} or event["time_status"] != "PRESENT" or event["severity"] != ("WARNING" if event["kind"] == "POSITION_UNRESOLVED" else "INFO"):
                return False
            if not isinstance(event["symbol"], str) or not re.fullmatch(r"[A-Z0-9]{2,24}(?:/[A-Z0-9]{2,24})?", event["symbol"]) or not unsigned(event["sequence"]) or event["sequence"] < 1:
                return False
            if event["sequence"] in sequences:
                return False
            sequences.add(event["sequence"])
            if stamp > utc_seconds(source["source_generated_at_utc"]):
                return False
        elif event["kind"].startswith("POSITION_") or event["symbol"] is not None or event["sequence"] is not None:
            return False
    for source in doc["sources"]:
        rows = [event for event in doc["events"] if event["source_id"] == source["source_id"]]
        if len(rows) != (source["published_count"] or 0):
            return False
        undated = sum(event["time_status"] == "UNKNOWN" for event in rows)
        if source["status"] == "PRESENT" and (undated > source["undated_count"] or (not source["truncated"] and undated != source["undated_count"])):
            return False
    if doc["events"] != sorted(doc["events"], key=event_order):
        return False
    if transport:
        if not finite(doc["snapshot_age_s"]) or doc["snapshot_age_s"] < 0 or doc["freshness_classification"] not in {"FRESH", "STALE"}:
            return False
    return True
