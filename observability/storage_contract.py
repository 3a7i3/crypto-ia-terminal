"""Closed observational storage contract; no filesystem scan or runtime imports."""
from __future__ import annotations

import re

from observability.event_center_contract import exact, finite, unsigned, utc_seconds

MAX_ENTRIES = 10_000
PATTERN = "decision_packets_*.jsonl"
STATUSES = {"PRESENT", "NOT_CONFIGURED", "MISSING", "READ_ERROR", "INVALID_PATH",
            "OUTPUT_LIMIT", "SOURCE_CHANGED", "INVALID_METADATA"}
METRICS = {"entries_observed", "matched_file_count", "total_bytes", "latest_file_modified_at_utc", "inventory_sha256"}
KEYS = {"schema_version", "product", "domain", "authority", "mode", "generated_at_utc",
        "observed_at_utc", "category", "scope", "pattern", "source_status"} | METRICS


def validate_storage_snapshot(doc, *, transport=False):
    try:
        return _validate(doc, transport=transport)
    except (ValueError, TypeError, OverflowError, KeyError):
        return False


def _validate(doc, *, transport):
    if not exact(doc, KEYS | ({"snapshot_age_s", "freshness_classification"} if transport else set())):
        return False
    if (doc["schema_version"], doc["product"], doc["domain"], doc["authority"], doc["mode"],
        doc["category"], doc["scope"], doc["pattern"]) != (
        "1.0.0", "StorageSnapshot", "storage", "FILESYSTEM_METADATA_OBSERVATION", "READ_ONLY",
        "DECISION_PACKET_LOGS", "DIRECT_CHILDREN_PATTERN", PATTERN
    ):
        return False
    observed, generated = utc_seconds(doc["observed_at_utc"]), utc_seconds(doc["generated_at_utc"])
    if observed is None or generated is None or observed > generated or doc["source_status"] not in STATUSES:
        return False
    if transport:
        age = doc["snapshot_age_s"]
        if not finite(age) or age < 0 or doc["freshness_classification"] != ("STALE" if age > 90 else "FRESH"):
            return False
    if doc["source_status"] != "PRESENT":
        return all(doc[key] is None for key in METRICS)
    if not all(unsigned(doc[key]) for key in ("entries_observed", "matched_file_count", "total_bytes")):
        return False
    count = doc["matched_file_count"]
    if count > doc["entries_observed"] or doc["entries_observed"] > MAX_ENTRIES:
        return False
    if not isinstance(doc["inventory_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", doc["inventory_sha256"]):
        return False
    latest = utc_seconds(doc["latest_file_modified_at_utc"])
    if count == 0:
        return latest is None and doc["latest_file_modified_at_utc"] is None and doc["total_bytes"] == 0
    return latest is not None and latest <= observed
