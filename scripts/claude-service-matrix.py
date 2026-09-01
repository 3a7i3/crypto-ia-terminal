#!/usr/bin/env python3
"""Emit a bounded, read-only matrix for a fixed catalog of systemd services.

The program accepts no service name or other caller-controlled input.  It asks
systemd only for explicitly allowlisted metadata properties and never emits
commands, environments, journal content, or raw stderr.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Sequence


SCHEMA_VERSION = 1
PACK_NAME = "service_matrix"
SYSTEMCTL = "/usr/bin/systemctl"
QUERY_TIMEOUT_SECONDS = 3
MAX_OUTPUT_BYTES = 24_000

# Never add Environment, EnvironmentFiles, ExecStart, ExecStartPre,
# ExecStartPost, ExecReload, ExecStop, or journal fields here.  Those can expose
# secrets, command lines, or unbounded application content.
SAFE_PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "UnitFileState",
    "MainPID",
    "NRestarts",
    "ExecMainCode",
    "ExecMainStatus",
    "Result",
    "ActiveEnterTimestamp",
    "StateChangeTimestamp",
    "NeedDaemonReload",
)


@dataclass(frozen=True)
class ServiceSpec:
    """One immutable service identity and its research-infrastructure role."""

    unit: str
    role: str
    tier: str


SERVICE_CATALOG = (
    ServiceSpec("crypto-advisor.service", "decision_engine", "core"),
    ServiceSpec("crypto-watchdog.service", "runtime_safety", "safety"),
    ServiceSpec("crypto-dashboard.service", "web_interface", "interface"),
    ServiceSpec("crypto-lmi-observatory.service", "live_market_observation", "observation"),
    ServiceSpec("crypto-market-horizons.service", "market_horizons", "observation"),
    ServiceSpec("crypto-market-observer.service", "market_observer", "observation"),
    ServiceSpec("crypto-market-radar.service", "market_radar", "observation"),
    ServiceSpec("crypto-quant-observer.service", "telegram_quant_observer", "interface"),
    ServiceSpec("crypto-radar-bot.service", "telegram_radar", "interface"),
    ServiceSpec("paper-arena.service", "paper_execution_interface", "interface"),
)

RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def utc_now() -> str:
    """Return the observation time as a second-resolution UTC timestamp."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def catalog_sha256(catalog: Sequence[ServiceSpec] = SERVICE_CATALOG) -> str:
    """Hash the fixed unit/role/tier catalog for reproducibility."""

    canonical = json.dumps(
        [[item.unit, item.role, item.tier] for item in catalog],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def parse_properties(stdout: str) -> dict[str, str]:
    """Parse systemctl key/value output and retain only safe properties."""

    allowed = set(SAFE_PROPERTIES)
    parsed: dict[str, str] = {}
    for line in stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in allowed:
            parsed[key] = value
    return parsed


def operational_state(properties: dict[str, str], query_status: str) -> str:
    """Normalize systemd state without claiming that an active unit is healthy."""

    if query_status == "not_found":
        return "not_found"
    if query_status != "ok":
        return "unknown"
    active_state = properties.get("ActiveState", "unknown")
    if active_state in {
        "active",
        "inactive",
        "activating",
        "deactivating",
        "failed",
        "reloading",
        "maintenance",
    }:
        return active_state
    return "unknown"


def query_service(
    spec: ServiceSpec,
    run_command: RunCommand = subprocess.run,
) -> dict[str, Any]:
    """Query one fixed unit with a timeout and return a content-safe record."""

    command = [
        SYSTEMCTL,
        "show",
        "--no-pager",
        f"--property={','.join(SAFE_PROPERTIES)}",
        "--",
        spec.unit,
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
        properties: dict[str, str] = {}
        query_status = "timeout"
        return _service_record(spec, properties, query_status, None)
    except OSError:
        properties = {}
        query_status = "command_unavailable"
        return _service_record(spec, properties, query_status, None)

    properties = parse_properties(result.stdout)
    if properties.get("LoadState") == "not-found" or result.returncode == 4:
        query_status = "not_found"
    elif result.returncode == 0:
        query_status = "ok"
    else:
        query_status = "command_failed"
    return _service_record(spec, properties, query_status, result.returncode)


def _bounded_integer(value: str | None) -> int | None:
    """Convert a short unsigned decimal field without accepting arbitrary text."""

    if value is None or not value.isdecimal() or len(value) > 20:
        return None
    return int(value)


def _service_record(
    spec: ServiceSpec,
    properties: dict[str, str],
    query_status: str,
    command_exit_code: int | None,
) -> dict[str, Any]:
    """Map allowlisted properties to the stable public service record schema."""

    return {
        "unit": spec.unit,
        "role": spec.role,
        "tier": spec.tier,
        "query_status": query_status,
        "command_exit_code": command_exit_code,
        "operational_state": operational_state(properties, query_status),
        "load_state": properties.get("LoadState", "unknown"),
        "active_state": properties.get("ActiveState", "unknown"),
        "sub_state": properties.get("SubState", "unknown"),
        "unit_file_state": properties.get("UnitFileState", "unknown"),
        "main_pid": _bounded_integer(properties.get("MainPID")),
        "restart_count": _bounded_integer(properties.get("NRestarts")),
        "exec_main_code": properties.get("ExecMainCode", "unknown"),
        "exec_main_status": _bounded_integer(properties.get("ExecMainStatus")),
        "result": properties.get("Result", "unknown"),
        "active_enter_timestamp_utc": properties.get(
            "ActiveEnterTimestamp", "unknown"
        ),
        "state_change_timestamp_utc": properties.get(
            "StateChangeTimestamp", "unknown"
        ),
        "need_daemon_reload": properties.get("NeedDaemonReload", "unknown"),
    }


def collect_matrix(
    catalog: Sequence[ServiceSpec] = SERVICE_CATALOG,
    run_command: RunCommand = subprocess.run,
    observed_at_utc: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Collect every catalog entry and derive completeness plus summary counts."""

    records = [query_service(item, run_command=run_command) for item in catalog]
    complete_statuses = {"ok", "not_found"}
    collection_status = (
        "complete"
        if all(record["query_status"] in complete_statuses for record in records)
        else "partial"
    )
    summary = {
        "catalog_count": len(records),
        "active_count": sum(
            record["active_state"] == "active" for record in records
        ),
        "failed_count": sum(
            record["active_state"] == "failed" for record in records
        ),
        "inactive_count": sum(
            record["active_state"] == "inactive" for record in records
        ),
        "not_found_count": sum(
            record["query_status"] == "not_found" for record in records
        ),
        "query_error_count": sum(
            record["query_status"] not in complete_statuses for record in records
        ),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pack": PACK_NAME,
        "observed_at_utc": observed_at_utc or utc_now(),
        "collection_status": collection_status,
        "catalog_sha256": catalog_sha256(catalog),
        "contract": {
            "query_timeout_seconds": QUERY_TIMEOUT_SECONDS,
            "max_output_bytes": MAX_OUTPUT_BYTES,
            "raw_stderr_emitted": False,
            "journal_read": False,
            "environment_read": False,
            "exec_command_read": False,
        },
        "summary": summary,
        "services": records,
    }
    return payload, 0 if collection_status == "complete" else 69


def render_matrix(payload: dict[str, Any]) -> str:
    """Render deterministic JSON and enforce the hard stdout size ceiling."""

    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if len(rendered.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError("service matrix exceeds output limit")
    return rendered


def main(argv: Sequence[str] | None = None) -> int:
    """Reject caller input, emit one matrix, and return its collection status."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("SERVICE_MATRIX_REJECTED: arguments are not accepted", file=sys.stderr)
        return 64

    payload, exit_code = collect_matrix()
    try:
        sys.stdout.write(render_matrix(payload))
    except ValueError:
        print("SERVICE_MATRIX_OUTPUT_LIMIT_EXCEEDED", file=sys.stderr)
        return 70
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
