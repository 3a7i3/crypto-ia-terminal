"""U2b external read-only host collector. Never imported by Advisor or API.

Only a fixed systemctl show command is allowed. No environment/command lines,
journal, process probing, trading imports or service mutations are performed.
Deployment identity is supplied evidence, never the collector's git HEAD.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import selectors
import socket
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from observability.runtime_service_artifact import read_document
from observability.runtime_service_contract import (
    ACTIVE_STATES,
    AUTHORITY,
    DOMAIN,
    LOAD_STATES,
    MAX_BYTES,
    PRODUCT,
    SCHEMA_VERSION,
    SERVICE_FIELDS,
    SUB_STATES,
    UNIT,
    exact,
    hex_string,
    safe_text,
    unsigned,
    utc_seconds,
    validate_runtime_service_snapshot,
)

DEFAULT_PATH = Path("databases/runtime_service_snapshot.json")
SAFE_PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "MainPID",
    "NRestarts",
    "ExecMainStartTimestamp",
    "InvocationID",
)
COMMAND = (
    "/usr/bin/systemctl",
    "show",
    "--no-pager",
    f"--property={','.join(SAFE_PROPERTIES)}",
    "--",
    UNIT,
)
QUERY_TIMEOUT_S = 3
QUERY_MAX_BYTES = 4096


class QueryOutputLimit(RuntimeError):
    """The fixed query exceeded its byte budget."""


def run_systemctl(command, *, env, timeout, **_options):
    """Capture at most 4097 bytes; discard stderr and bound total wall time."""
    if tuple(command) != COMMAND:
        raise ValueError("INVALID_COMMAND")
    deadline = time.monotonic() + timeout
    with subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
        shell=False,
    ) as process:
        try:
            data = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise subprocess.TimeoutExpired(command, timeout)
                    chunk = os.read(
                        process.stdout.fileno(), QUERY_MAX_BYTES + 1 - len(data)
                    )
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > QUERY_MAX_BYTES:
                        raise QueryOutputLimit()
            code = process.wait(timeout=max(0, deadline - time.monotonic()))
            return subprocess.CompletedProcess(command, code, data.decode("utf-8"), "")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def unavailable_service(status: str) -> dict:
    return {
        **dict.fromkeys(SERVICE_FIELDS),
        "unit": UNIT,
        "query_status": status,
        "load_state": "not-found" if status == "NOT_FOUND" else None,
    }


def _start_timestamp(value: str) -> str | None:
    if not value or value == "n/a":
        return None
    # LC_ALL=C / TZ=UTC makes systemd's textual timestamp deterministic.
    parsed = datetime.strptime(value, "%a %Y-%m-%d %H:%M:%S UTC").replace(
        tzinfo=timezone.utc
    )
    return parsed.isoformat().replace("+00:00", "Z")


def collect_service(*, run_command=run_systemctl) -> dict:
    environment = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "TZ": "UTC",
        "SYSTEMD_PAGER": "cat",
        "SYSTEMD_COLORS": "0",
    }
    try:
        result = run_command(
            list(COMMAND),
            check=False,
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT_S,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return unavailable_service("TIMEOUT")
    except QueryOutputLimit:
        return unavailable_service("OUTPUT_LIMIT")
    except UnicodeError:
        return unavailable_service("INVALID_PROPERTIES")
    except OSError:
        return unavailable_service("COMMAND_UNAVAILABLE")
    if len(result.stdout.encode("utf-8")) > QUERY_MAX_BYTES:
        return unavailable_service("OUTPUT_LIMIT")
    properties = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition("=")
        if not sep or key not in SAFE_PROPERTIES or key in properties:
            return unavailable_service("INVALID_PROPERTIES")
        properties[key] = value
    if properties.get("LoadState") == "not-found" and result.returncode in {0, 4}:
        return unavailable_service("NOT_FOUND")
    if result.returncode != 0:
        return unavailable_service("COMMAND_FAILED")
    if set(properties) != set(SAFE_PROPERTIES):
        return unavailable_service("INVALID_PROPERTIES")
    try:
        pid, restarts = properties["MainPID"], properties["NRestarts"]
        if (
            not pid.isascii()
            or not restarts.isascii()
            or not pid.isdecimal()
            or not restarts.isdecimal()
            or max(len(pid), len(restarts)) > 16
        ):
            raise ValueError("invalid counters")
        invocation = properties["InvocationID"] or None
        service = {
            "unit": UNIT,
            "query_status": "OK",
            "load_state": properties["LoadState"],
            "active_state": properties["ActiveState"],
            "sub_state": properties["SubState"],
            "main_pid": int(pid),
            "restart_count": int(restarts),
            "exec_main_started_at_utc": _start_timestamp(
                properties["ExecMainStartTimestamp"]
            ),
            "invocation_id": invocation,
        }
        if (
            service["load_state"] not in LOAD_STATES - {"not-found"}
            or service["active_state"] not in ACTIVE_STATES
            or service["sub_state"] not in SUB_STATES
            or not unsigned(service["main_pid"])
            or not unsigned(service["restart_count"])
            or (invocation is not None and not hex_string(invocation, 32))
        ):
            raise ValueError("invalid properties")
        return service
    except ValueError:
        return unavailable_service("INVALID_PROPERTIES")


def _missing_deployment(reason: str) -> dict:
    return {
        "status": "NOT_AVAILABLE",
        "reason": reason,
        "source_code_sha": None,
        "evidence_ref": None,
        "observed_at_utc": None,
        "artifact_sha256": None,
        "host_id": None,
        "invocation_id": None,
    }


def deployment_projection(
    path: Path | None, *, host_id: str, service: dict, observed: float
) -> dict:
    if path is None:
        return _missing_deployment("NO_EVIDENCE")
    try:
        evidence, raw = read_document(path)
    except (OSError, TypeError, ValueError, UnicodeError):
        return _missing_deployment("INVALID_EVIDENCE")
    fields = {
        "schema_version",
        "product",
        "host_id",
        "unit",
        "invocation_id",
        "source_code_sha",
        "evidence_ref",
        "observed_at_utc",
    }
    stamp = utc_seconds(evidence.get("observed_at_utc"))
    if (
        not exact(evidence, fields)
        or evidence["schema_version"] != SCHEMA_VERSION
        or evidence["product"] != "RuntimeServiceDeploymentEvidence"
        or evidence["unit"] != UNIT
        or not safe_text(evidence["host_id"])
        or not hex_string(evidence["invocation_id"], 32)
        or not hex_string(evidence["source_code_sha"], 40)
        or not safe_text(evidence["evidence_ref"])
        or stamp is None
    ):
        return _missing_deployment("INVALID_EVIDENCE")
    if evidence["host_id"] != host_id:
        return _missing_deployment("HOST_MISMATCH")
    if service["query_status"] != "OK":
        return _missing_deployment("SERVICE_UNAVAILABLE")
    if evidence["invocation_id"] != service["invocation_id"]:
        return _missing_deployment("INVOCATION_MISMATCH")
    started = utc_seconds(service["exec_main_started_at_utc"])
    if started is None or not started <= stamp <= observed:
        return _missing_deployment("EVIDENCE_TIME_MISMATCH")
    return {
        "status": "PRESENT",
        "reason": None,
        "source_code_sha": evidence["source_code_sha"],
        "evidence_ref": evidence["evidence_ref"],
        "observed_at_utc": evidence["observed_at_utc"],
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "host_id": evidence["host_id"],
        "invocation_id": evidence["invocation_id"],
    }


def build_runtime_service_snapshot(
    *,
    run_command=run_systemctl,
    now_fn=time.time,
    host_id: str | None = None,
    deployment_path: Path | None = None,
) -> dict[str, Any]:
    host = socket.gethostname() if host_id is None else host_id
    if not safe_text(host):
        raise ValueError("INVALID_HOST_ID")
    service = collect_service(run_command=run_command)
    observed = float(now_fn())
    # A malformed or contradictory host observation never becomes liveness.
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "product": PRODUCT,
        "domain": DOMAIN,
        "authority": AUTHORITY,
        "mode": "READ_ONLY",
        "generated_at_utc": _utc(observed),
        "observed_at_utc": _utc(observed),
        "host_id": host,
        "service": service,
        "deployment": _missing_deployment("NO_EVIDENCE"),
    }
    if not validate_runtime_service_snapshot(snapshot):
        snapshot["service"] = unavailable_service("INVALID_PROPERTIES")
    snapshot["deployment"] = deployment_projection(
        deployment_path, host_id=host, service=snapshot["service"], observed=observed
    )
    if not validate_runtime_service_snapshot(snapshot):
        raise ValueError("INVALID_SNAPSHOT")
    return snapshot


def write_runtime_service_snapshot(path: Path = DEFAULT_PATH, **kwargs) -> dict:
    target = Path(path)
    evidence_path = kwargs.get("deployment_path")
    if evidence_path is not None and target.resolve() == Path(evidence_path).resolve():
        raise ValueError("OUTPUT_SOURCE_COLLISION")
    snapshot = build_runtime_service_snapshot(**kwargs)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(snapshot, allow_nan=False, indent=2, sort_keys=True).encode()
    if len(content) > MAX_BYTES:
        raise ValueError("OUTPUT_LIMIT")
    # Unique temp file prevents concurrent collectors from sharing a .tmp.
    fd, name = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)
    return snapshot


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--deployment-evidence", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        write_runtime_service_snapshot(
            args.path, deployment_path=args.deployment_evidence
        )
    except (OSError, ValueError, OverflowError):
        # Never print raw command output, paths supplied in evidence or errors.
        print("RUNTIME_SERVICE_PUBLISH_FAILED")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
