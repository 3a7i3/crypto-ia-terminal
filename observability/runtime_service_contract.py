"""U2b closed host observation contract; no systemd or Advisor I/O here."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

UNIT = "crypto-advisor.service"
SCHEMA_VERSION = "1.0.0"
PRODUCT = "RuntimeServiceSnapshot"
DOMAIN = "runtime_service"
AUTHORITY = "HOST_SYSTEMD_OBSERVATION"
MAX_BYTES = 16_384
MAX_INTEGER = 9_007_199_254_740_991
LOAD_STATES = {
    "stub",
    "loaded",
    "not-found",
    "bad-setting",
    "error",
    "merged",
    "masked",
}
ACTIVE_STATES = {
    "active",
    "reloading",
    "inactive",
    "failed",
    "activating",
    "deactivating",
    "maintenance",
    "refreshing",
}
SUB_STATES = {
    "dead",
    "condition",
    "start-pre",
    "start",
    "start-post",
    "running",
    "exited",
    "reload",
    "reload-signal",
    "reload-notify",
    "stop",
    "stop-watchdog",
    "stop-sigterm",
    "stop-sigkill",
    "stop-post",
    "final-sigterm",
    "final-sigkill",
    "failed",
    "auto-restart",
    "auto-restart-queued",
    "cleaning",
    "maintenance",
}
QUERY_STATES = {
    "OK",
    "NOT_FOUND",
    "TIMEOUT",
    "COMMAND_UNAVAILABLE",
    "COMMAND_FAILED",
    "INVALID_PROPERTIES",
    "OUTPUT_LIMIT",
}
DEPLOYMENT_REASONS = {
    "NO_EVIDENCE",
    "INVALID_EVIDENCE",
    "HOST_MISMATCH",
    "INVOCATION_MISMATCH",
    "SERVICE_UNAVAILABLE",
    "EVIDENCE_TIME_MISMATCH",
}
SERVICE_FIELDS = {
    "unit",
    "query_status",
    "load_state",
    "active_state",
    "sub_state",
    "main_pid",
    "restart_count",
    "exec_main_started_at_utc",
    "invocation_id",
}
DEPLOYMENT_FIELDS = {
    "status",
    "reason",
    "source_code_sha",
    "evidence_ref",
    "observed_at_utc",
    "artifact_sha256",
    "host_id",
    "invocation_id",
}
BASE_FIELDS = {
    "schema_version",
    "product",
    "domain",
    "authority",
    "mode",
    "generated_at_utc",
    "observed_at_utc",
    "host_id",
    "service",
    "deployment",
}


def utc_seconds(value: Any) -> float | None:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value
    ):
        return None
    try:
        return (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .timestamp()
        )
    except ValueError:
        return None


def exact(value: Any, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def safe_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", value) is not None
    )


def hex_string(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None
    )


def unsigned(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= MAX_INTEGER
    )


def _validate(doc: Any, *, transport: bool = False) -> bool:
    keys = BASE_FIELDS | (
        {"snapshot_age_s", "freshness_classification"} if transport else set()
    )
    if not exact(doc, keys):
        return False
    for key, expected in {
        "schema_version": SCHEMA_VERSION,
        "product": PRODUCT,
        "domain": DOMAIN,
        "authority": AUTHORITY,
        "mode": "READ_ONLY",
    }.items():
        if doc[key] != expected:
            return False
    observed, generated = (
        utc_seconds(doc["observed_at_utc"]),
        utc_seconds(doc["generated_at_utc"]),
    )
    if (
        observed is None
        or generated is None
        or observed > generated
        or not safe_text(doc["host_id"])
    ):
        return False
    s = doc["service"]
    if (
        not exact(s, SERVICE_FIELDS)
        or s["unit"] != UNIT
        or s["query_status"] not in QUERY_STATES
    ):
        return False
    if s["query_status"] == "OK":
        if (
            s["load_state"] not in LOAD_STATES - {"not-found"}
            or s["active_state"] not in ACTIVE_STATES
            or s["sub_state"] not in SUB_STATES
        ):
            return False
        if not unsigned(s["main_pid"]) or not unsigned(s["restart_count"]):
            return False
        started = utc_seconds(s["exec_main_started_at_utc"])
        if s["exec_main_started_at_utc"] is not None and (
            started is None or started > observed
        ):
            return False
        if s["invocation_id"] is not None and not hex_string(s["invocation_id"], 32):
            return False
        # active/running without a main process or invocation is contradictory.
        if (
            s["active_state"] == "active"
            and s["sub_state"] == "running"
            and (not s["main_pid"] or started is None or s["invocation_id"] is None)
        ):
            return False
    else:
        if any(
            s[key] is not None
            for key in SERVICE_FIELDS - {"unit", "query_status", "load_state"}
        ):
            return False
        if s["load_state"] != (
            "not-found" if s["query_status"] == "NOT_FOUND" else None
        ):
            return False
    d = doc["deployment"]
    if not exact(d, DEPLOYMENT_FIELDS):
        return False
    if d["status"] == "PRESENT":
        stamp = utc_seconds(d["observed_at_utc"])
        started = utc_seconds(s["exec_main_started_at_utc"])
        if (
            d["reason"] is not None
            or d["host_id"] != doc["host_id"]
            or d["invocation_id"] != s["invocation_id"]
            or s["query_status"] != "OK"
            or s["invocation_id"] is None
            or started is None
            or stamp is None
            or not started <= stamp <= observed
        ):
            return False
        if (
            not hex_string(d["source_code_sha"], 40)
            or not hex_string(d["artifact_sha256"], 64)
            or not safe_text(d["evidence_ref"])
        ):
            return False
    elif d["status"] == "NOT_AVAILABLE":
        if d["reason"] not in DEPLOYMENT_REASONS or any(
            d[key] is not None for key in DEPLOYMENT_FIELDS - {"status", "reason"}
        ):
            return False
    else:
        return False
    if transport:
        age = doc["snapshot_age_s"]
        if (
            isinstance(age, bool)
            or not isinstance(age, (int, float))
            or not math.isfinite(age)
            or age < 0
            or doc["freshness_classification"] not in {"FRESH", "STALE"}
        ):
            return False
    return True


def validate_runtime_service_snapshot(doc: Any, *, transport: bool = False) -> bool:
    try:
        return _validate(doc, transport=transport)
    except (TypeError, ValueError, OverflowError):
        return False
