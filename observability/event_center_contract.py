"""Closed passive event presentation contract; no producer/runtime imports."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

MAX_BYTES = 2_097_152
MAX_RECORDS = 10_000
MAX_EVENTS_PER_SOURCE = 100
# Tail window (1.1.0) for append-only JSONL sources: used when the file exceeds MAX_BYTES
# (last TAIL_WINDOW_BYTES) or holds more than MAX_RECORDS lines (last MAX_RECORDS lines).
TAIL_WINDOW_BYTES = 1_048_576
SOURCE_IDS = ("p12_alerts", "supervision_alerts", "ppl_lifecycles")
FORMATS = ("P12_ALERT_JSONL", "SUPERVISION_AUDIT_JSONL", "BURN_IN_LIFECYCLE_PROJECTION")
STATUSES = {"PRESENT", "PARTIAL_TAIL", "NOT_CONFIGURED", "MISSING", "READ_ERROR", "INVALID", "OUTPUT_LIMIT"}
# Sources whose rows were read (PARTIAL_TAIL = a bounded tail window, never exhaustive).
OBSERVED = {"PRESENT", "PARTIAL_TAIL"}
VERSION_BASE, VERSION_COVERAGE = "1.0.0", "1.1.0"
COVERAGE_KEYS = {"coverage", "source_bytes", "window_bytes"}
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


def source_keys_for(version):
    return SOURCE_KEYS | (COVERAGE_KEYS if version == VERSION_COVERAGE else set())


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


def _coverage_ok(source) -> bool:
    """1.1.0: coverage is explicit. FULL = whole file; TAIL_WINDOW = its last complete lines only."""
    size, window = source["source_bytes"], source["window_bytes"]
    if not unsigned(size) or not unsigned(window) or window > size:
        return False
    if source["status"] == "PRESENT":
        return source["coverage"] == "FULL" and window == size and size <= MAX_BYTES
    return (source["coverage"] == "TAIL_WINDOW" and 0 < window < size
            and window <= max(TAIL_WINDOW_BYTES, MAX_BYTES))


def validate_event_center(doc, *, transport=False) -> bool:
    try:
        return _validate_event_center(doc, transport=transport)
    except (TypeError, ValueError, OverflowError, KeyError, RecursionError):
        return False


def _validate_event_center(doc, *, transport=False) -> bool:
    keys = TOP_KEYS | ({"snapshot_age_s", "freshness_classification"} if transport else set())
    if not exact(doc, keys):
        return False
    version = doc["schema_version"]
    if version not in (VERSION_BASE, VERSION_COVERAGE):
        return False
    if (doc["product"], doc["domain"], doc["authority"], doc["mode"], doc["order"]) != (
        "EventCenterSnapshot", "event_center", "OBSERVATIONAL_PRESENTATION",
        "READ_ONLY", "SOURCE_THEN_TIME_DESC_UNDATED_LAST"
    ):
        return False
    generated = utc_seconds(doc["generated_at_utc"])
    if generated is None or not isinstance(doc["sources"], list) or len(doc["sources"]) != 3:
        return False
    if not isinstance(doc["events"], list) or len(doc["events"]) > 3 * MAX_EVENTS_PER_SOURCE:
        return False
    for index, source in enumerate(doc["sources"]):
        source_keys = source_keys_for(version) | ({"source_age_s", "freshness_classification"} if transport else set())
        if not exact(source, source_keys) or source["source_id"] != SOURCE_IDS[index] or source["format"] != FORMATS[index]:
            return False
        if source["status"] not in STATUSES:
            return False
        if source["status"] == "PARTIAL_TAIL" and (version != VERSION_COVERAGE or index == 2):
            return False  # tail windows exist only in 1.1.0 and only for JSONL sources
        if transport:
            age = source["source_age_s"]
            freshness = source["freshness_classification"]
            if source["status"] not in OBSERVED:
                if age is not None or freshness != "NOT_AVAILABLE":
                    return False
            elif index < 2:
                if age is not None or freshness != "UNKNOWN":
                    return False
            elif not finite(age) or age < 0 or freshness not in {"FRESH", "STALE"}:
                return False
        nullable = source_keys_for(version) - {"source_id", "format", "status"}
        if source["status"] not in OBSERVED:
            if any(source[k] is not None for k in nullable):
                return False
            continue
        if version == VERSION_COVERAGE and not _coverage_ok(source):
            return False
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
        if source["status"] not in OBSERVED or not unsigned(event["source_record"]) or event["source_record"] < 1:
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
            if not isinstance(event["symbol"], str) or not re.fullmatch(r"[A-Z0-9]{1,24}(?:/[A-Z0-9]{2,24})?", event["symbol"]) or not unsigned(event["sequence"]) or event["sequence"] < 1:
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
        if source["status"] in OBSERVED and (undated > source["undated_count"] or (not source["truncated"] and undated != source["undated_count"])):
            return False
    if doc["events"] != sorted(doc["events"], key=event_order):
        return False
    if transport:
        if not finite(doc["snapshot_age_s"]) or doc["snapshot_age_s"] < 0 or doc["freshness_classification"] not in {"FRESH", "STALE"}:
            return False
    return True
