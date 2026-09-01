#!/usr/bin/env python3
"""Observe the fixed systemd triggers for three static oneshot services.

The pack accepts no arguments. It reads only explicitly allowlisted systemd
metadata for three immutable service/timer pairs and emits bounded JSON.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Sequence


SCHEMA_VERSION = 1
PACK_NAME = "service_trigger_matrix"
SYSTEMCTL = "/usr/bin/systemctl"
QUERY_TIMEOUT_SECONDS = 3
MAX_OUTPUT_BYTES = 24_000
MAX_DEPENDENCIES = 32
MAX_SCALAR_LENGTH = 160
UNIT_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.@:-]{1,128}$")

# The lists intentionally exclude Environment*, ExecStart*, ExecStop,
# FragmentPath, DropInPaths, command lines, journal fields, and cgroup content.
TIMER_PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "UnitFileState",
    "Unit",
    "Triggers",
    "Wants",
    "Requires",
    "After",
    "Before",
    "LastTriggerUSec",
    "NextElapseUSecRealtime",
    "NextElapseUSecMonotonic",
    "Persistent",
    "AccuracyUSec",
    "RandomizedDelayUSec",
    "Result",
)

SERVICE_PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "UnitFileState",
    "Type",
    "TriggeredBy",
    "Wants",
    "Requires",
    "After",
    "StateChangeTimestamp",
    "ActiveEnterTimestamp",
    "Result",
    "ExecMainStatus",
)


@dataclass(frozen=True)
class TriggerSpec:
    """One immutable timer/service relationship and its expected cadence."""

    timer: str
    service: str
    role: str
    expected_schedule: str


TRIGGER_CATALOG = (
    TriggerSpec(
        "crypto-market-observer.timer",
        "crypto-market-observer.service",
        "market_observer",
        "every_15_minutes_after_boot",
    ),
    TriggerSpec(
        "crypto-market-radar.timer",
        "crypto-market-radar.service",
        "market_radar",
        "daily_0600_utc",
    ),
    TriggerSpec(
        "crypto-market-horizons.timer",
        "crypto-market-horizons.service",
        "market_horizons",
        "daily_0615_utc",
    ),
)

RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def utc_now() -> str:
    """Return a second-resolution UTC observation timestamp."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def catalog_sha256(catalog: Sequence[TriggerSpec] = TRIGGER_CATALOG) -> str:
    """Hash the ordered timer/service/schedule catalog for reproducibility."""

    canonical = json.dumps(
        [
            [item.timer, item.service, item.role, item.expected_schedule]
            for item in catalog
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def parse_properties(stdout: str, allowed_properties: Sequence[str]) -> dict[str, str]:
    """Parse systemctl output and discard every non-allowlisted property."""

    allowed = set(allowed_properties)
    parsed: dict[str, str] = {}
    for line in stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in allowed:
            parsed[key] = value
    return parsed


def bounded_scalar(value: str | None) -> str:
    """Normalize one short systemd scalar without allowing control characters."""

    if value is None or value == "":
        return "unknown"
    if len(value) > MAX_SCALAR_LENGTH:
        return "over_limit"
    if any(ord(character) < 32 for character in value):
        return "invalid"
    return value


def bounded_unit_list(value: str | None) -> list[str]:
    """Return at most 32 syntactically valid systemd unit-name tokens."""

    if not value:
        return []
    units = [token for token in value.split() if UNIT_TOKEN_RE.fullmatch(token)]
    return units[:MAX_DEPENDENCIES]


def bounded_integer(value: str | None) -> int | None:
    """Convert only a short unsigned decimal status value."""

    if value is None or not value.isdecimal() or len(value) > 20:
        return None
    return int(value)


def query_unit(
    unit: str,
    properties: Sequence[str],
    run_command: RunCommand = subprocess.run,
) -> dict[str, Any]:
    """Query one fixed unit with a timeout and without exposing raw stderr."""

    command = [
        SYSTEMCTL,
        "show",
        "--no-pager",
        f"--property={','.join(properties)}",
        "--",
        unit,
    ]
    environment = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LC_ALL": "C",
        "TZ": "UTC",
        "SYSTEMD_PAGER": "cat",
        "SYSTEMD_COLORS": "0",
    }
    try:
        result = run_command(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT_SECONDS,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return {"query_status": "timeout", "command_exit_code": None, "properties": {}}
    except OSError:
        return {
            "query_status": "command_unavailable",
            "command_exit_code": None,
            "properties": {},
        }

    parsed = parse_properties(result.stdout, properties)
    if parsed.get("LoadState") == "not-found" or result.returncode == 4:
        query_status = "not_found"
    elif result.returncode == 0:
        query_status = "ok"
    else:
        query_status = "command_failed"
    return {
        "query_status": query_status,
        "command_exit_code": result.returncode,
        "properties": parsed,
    }


def timer_state(properties: dict[str, str], query_status: str) -> str:
    """Normalize timer scheduling state without asserting application health."""

    if query_status == "not_found":
        return "not_found"
    if query_status != "ok":
        return "unknown"
    active = properties.get("ActiveState", "unknown")
    sub = properties.get("SubState", "unknown")
    if active == "active" and sub == "waiting":
        return "scheduled_waiting"
    if active == "active":
        return f"active_{bounded_scalar(sub)}"
    if active in {"inactive", "failed", "activating", "deactivating"}:
        return active
    return "unknown"


def relationship_status(
    spec: TriggerSpec,
    timer_query: dict[str, Any],
    service_query: dict[str, Any],
) -> str:
    """Compare runtime timer linkage with the fixed expected service name."""

    if timer_query["query_status"] == "not_found":
        return "timer_not_found"
    if service_query["query_status"] == "not_found":
        return "service_not_found"
    if timer_query["query_status"] != "ok" or service_query["query_status"] != "ok":
        return "unknown"

    timer_properties = timer_query["properties"]
    service_properties = service_query["properties"]
    linked_services = set(bounded_unit_list(timer_properties.get("Triggers")))
    timer_unit = bounded_scalar(timer_properties.get("Unit"))
    if timer_unit not in {"unknown", "invalid", "over_limit"}:
        linked_services.add(timer_unit)
    triggered_by = set(bounded_unit_list(service_properties.get("TriggeredBy")))

    timer_points_to_service = spec.service in linked_services
    service_points_to_timer = not triggered_by or spec.timer in triggered_by
    return "match" if timer_points_to_service and service_points_to_timer else "mismatch"


def build_pair_record(
    spec: TriggerSpec,
    timer_query: dict[str, Any],
    service_query: dict[str, Any],
) -> dict[str, Any]:
    """Build the stable evidence schema for one timer/service pair."""

    timer = timer_query["properties"]
    service = service_query["properties"]
    return {
        "role": spec.role,
        "expected_schedule": spec.expected_schedule,
        "timer": spec.timer,
        "service": spec.service,
        "relationship_status": relationship_status(spec, timer_query, service_query),
        "timer_observation": {
            "query_status": timer_query["query_status"],
            "command_exit_code": timer_query["command_exit_code"],
            "load_state": bounded_scalar(timer.get("LoadState")),
            "active_state": bounded_scalar(timer.get("ActiveState")),
            "sub_state": bounded_scalar(timer.get("SubState")),
            "unit_file_state": bounded_scalar(timer.get("UnitFileState")),
            "scheduling_state": timer_state(timer, timer_query["query_status"]),
            "trigger_unit": bounded_scalar(timer.get("Unit")),
            "triggers": bounded_unit_list(timer.get("Triggers")),
            "last_trigger_utc": bounded_scalar(timer.get("LastTriggerUSec")),
            "next_elapse_realtime_utc": bounded_scalar(
                timer.get("NextElapseUSecRealtime")
            ),
            "next_elapse_monotonic": bounded_scalar(
                timer.get("NextElapseUSecMonotonic")
            ),
            "persistent": bounded_scalar(timer.get("Persistent")),
            "accuracy": bounded_scalar(timer.get("AccuracyUSec")),
            "randomized_delay": bounded_scalar(timer.get("RandomizedDelayUSec")),
            "result": bounded_scalar(timer.get("Result")),
            "wants": bounded_unit_list(timer.get("Wants")),
            "requires": bounded_unit_list(timer.get("Requires")),
            "after": bounded_unit_list(timer.get("After")),
            "before": bounded_unit_list(timer.get("Before")),
        },
        "service_observation": {
            "query_status": service_query["query_status"],
            "command_exit_code": service_query["command_exit_code"],
            "load_state": bounded_scalar(service.get("LoadState")),
            "active_state": bounded_scalar(service.get("ActiveState")),
            "sub_state": bounded_scalar(service.get("SubState")),
            "unit_file_state": bounded_scalar(service.get("UnitFileState")),
            "service_type": bounded_scalar(service.get("Type")),
            "triggered_by": bounded_unit_list(service.get("TriggeredBy")),
            "last_state_change_utc": bounded_scalar(
                service.get("StateChangeTimestamp")
            ),
            "last_active_enter_utc": bounded_scalar(
                service.get("ActiveEnterTimestamp")
            ),
            "result": bounded_scalar(service.get("Result")),
            "exec_main_status": bounded_integer(service.get("ExecMainStatus")),
            "wants": bounded_unit_list(service.get("Wants")),
            "requires": bounded_unit_list(service.get("Requires")),
            "after": bounded_unit_list(service.get("After")),
        },
    }


def collect_matrix(
    catalog: Sequence[TriggerSpec] = TRIGGER_CATALOG,
    run_command: RunCommand = subprocess.run,
    observed_at_utc: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Collect the three pairs and derive completeness plus bounded summaries."""

    pairs: list[dict[str, Any]] = []
    query_statuses: list[str] = []
    for spec in catalog:
        timer_query = query_unit(spec.timer, TIMER_PROPERTIES, run_command)
        service_query = query_unit(spec.service, SERVICE_PROPERTIES, run_command)
        query_statuses.extend(
            [timer_query["query_status"], service_query["query_status"]]
        )
        pairs.append(build_pair_record(spec, timer_query, service_query))

    complete_statuses = {"ok", "not_found"}
    collection_status = (
        "complete"
        if all(status in complete_statuses for status in query_statuses)
        else "partial"
    )
    summary = {
        "pair_count": len(pairs),
        "scheduled_waiting_count": sum(
            pair["timer_observation"]["scheduling_state"] == "scheduled_waiting"
            for pair in pairs
        ),
        "inactive_timer_count": sum(
            pair["timer_observation"]["active_state"] == "inactive"
            for pair in pairs
        ),
        "failed_timer_count": sum(
            pair["timer_observation"]["active_state"] == "failed" for pair in pairs
        ),
        "not_found_timer_count": sum(
            pair["timer_observation"]["query_status"] == "not_found"
            for pair in pairs
        ),
        "relationship_mismatch_count": sum(
            pair["relationship_status"] == "mismatch" for pair in pairs
        ),
        "query_error_count": sum(
            status not in complete_statuses for status in query_statuses
        ),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pack": PACK_NAME,
        "observed_at_utc": observed_at_utc or utc_now(),
        "collection_status": collection_status,
        "catalog_sha256": catalog_sha256(catalog),
        "contract": {
            "fixed_pair_count": len(catalog),
            "query_timeout_seconds": QUERY_TIMEOUT_SECONDS,
            "max_output_bytes": MAX_OUTPUT_BYTES,
            "max_dependencies_per_field": MAX_DEPENDENCIES,
            "raw_stderr_emitted": False,
            "journal_read": False,
            "environment_read": False,
            "exec_command_read": False,
            "unit_file_content_read": False,
        },
        "summary": summary,
        "pairs": pairs,
    }
    return payload, 0 if collection_status == "complete" else 69


def render_matrix(payload: dict[str, Any]) -> str:
    """Render deterministic JSON and enforce the hard stdout ceiling."""

    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if len(rendered.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError("service trigger matrix exceeds output limit")
    return rendered


def main(argv: Sequence[str] | None = None) -> int:
    """Reject caller input, emit one matrix, and return collection status."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print(
            "SERVICE_TRIGGER_MATRIX_REJECTED: arguments are not accepted",
            file=sys.stderr,
        )
        return 64

    payload, exit_code = collect_matrix()
    try:
        sys.stdout.write(render_matrix(payload))
    except ValueError:
        print("SERVICE_TRIGGER_MATRIX_OUTPUT_LIMIT_EXCEEDED", file=sys.stderr)
        return 70
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
