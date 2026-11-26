#!/bin/bash
# P1 targeted inventory. Run on crypto-restore-01 as an ordinary user.
# Output is JSON on stdout. Run only after the operator authorizes the VPS check.
set -eu
exec /usr/bin/python3 -I -B - <<'PY'
import datetime
import hashlib
import http.client
import json
import os
import re
import socket
import stat
import subprocess

HOST = "crypto-restore-01"
API = "crypto-operator-api.service"
WEB = "crypto-operator-web.service"
UNITS = (API, WEB, "cat-scanner-universe.service", "cat-scanner-universe.timer")
PROPERTIES = ("ActiveState", "MainPID", "ExecMainStartTimestampMonotonic")
STATES = {"active", "inactive", "failed", "activating", "deactivating", "reloading", "maintenance"}
API_FILES = (
    "observability/operator_api/app.py",
    "observability/operator_api/scanner_universe_reader.py",
    "observability/operator_api/agent_invocation_reader.py",
    "observability/operator_api/agent_schedule.py",
    "agent_bench/observation/agents.py",
    "agent_bench/observation/market_observer.py",
)
API_DIRECTORIES = ("observability/operator_api", "observability/scanner_universe")
MAX_DIRECTORY_ENTRIES = 200
RELEASES = "opt/cat-app/releases/"
WEB_ROOT = RELEASES + "CAT-FOOTPRINT-FINANCE-V6-RC1/frontend/"
WEB_FILES = {
    "frontend/dist/index.html": (
        WEB_ROOT + "dist/index.html",
        RELEASES + "CAT-SCANNER-REFONTE-107f084a/dist/index.html",
    ),
    "frontend/scripts/web01_local_frontend_server.mjs": (
        WEB_ROOT + "scripts/web01_local_frontend_server.mjs",
        RELEASES + "CAT-SYSTEM-AGENTS-599-891e1865/server/web01_local_frontend_server.mjs",
    ),
}
MAX_BYTES = 2 * 1024 * 1024
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def unknown(reason):
    return {"state": "UNKNOWN", "reason": reason}


def unit(name):
    try:
        result = subprocess.run(
            ("/usr/bin/systemctl", "show", "--property=" + ",".join(PROPERTIES), name),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
            timeout=3, text=True, errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return unknown("SYSTEMD_UNAVAILABLE")
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    state = values.get("ActiveState")
    pid = values.get("MainPID", "")
    stamp = values.get("ExecMainStartTimestampMonotonic", "")
    return {
        "active": state if state in STATES else "UNKNOWN",
        "pid": int(pid) if re.fullmatch(r"[1-9][0-9]{0,9}", pid) and int(pid) < 2**31 else None,
        "start_monotonic_us": int(stamp) if re.fullmatch(r"[1-9][0-9]{0,19}", stamp) else None,
    }


def identity(info):
    if info.get("active") == "active" and info.get("pid") and info.get("start_monotonic_us"):
        return info["pid"], info["start_monotonic_us"]
    return None


def file_stamp(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def fingerprint(anchor, path):
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return unknown("INVALID_PATH")
    # /proc/<pid>/{cwd,root} is an intentional kernel anchor. All following
    # components are opened relative to descriptors and reject symlinks.
    try:
        parent = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in parts[:-1]:
                child = os.open(component, DIR_FLAGS, dir_fd=parent)
                os.close(parent)
                parent = child
            fd = os.open(parts[-1], FILE_FLAGS, dir_fd=parent)
            with os.fdopen(fd, "rb") as source:
                before = os.fstat(source.fileno())
                if not stat.S_ISREG(before.st_mode):
                    return unknown("NOT_REGULAR")
                if before.st_size > MAX_BYTES:
                    return unknown("TOO_LARGE")
                content = source.read(MAX_BYTES + 1)
                after = os.fstat(source.fileno())
        finally:
            os.close(parent)
    except OSError:
        return unknown("FILE_UNAVAILABLE")
    if len(content) > MAX_BYTES:
        return unknown("TOO_LARGE")
    if file_stamp(before) != file_stamp(after) or len(content) != before.st_size:
        return unknown("FILE_CHANGED")
    return {
        "state": "OBSERVED",
        "size": len(content),
        "git_blob_sha1": hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest(),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def inventory_directory(anchor, path):
    """Hash eligible files directly under a named directory, with a bounded scan."""
    try:
        fd = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in path.split("/"):
                child = os.open(component, DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = child
            before = os.fstat(fd)
            names = []
            with os.scandir(fd) as entries:
                for count, entry in enumerate(entries, 1):
                    if count > MAX_DIRECTORY_ENTRIES:
                        return {}, unknown("DIRECTORY_LIMIT")
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}\.py", entry.name) and entry.is_file(follow_symlinks=False):
                        names.append(entry.name)
            files = {
                f"{path}/{name}": {"observation": fingerprint(f"/proc/self/fd/{fd}", name)}
                for name in sorted(names)
            }
            if file_stamp(before) != file_stamp(os.fstat(fd)):
                return {}, unknown("DIRECTORY_CHANGED")
            state = (
                {"state": "OBSERVED"}
                if all(row["observation"]["state"] == "OBSERVED" for row in files.values())
                else unknown("FILE_UNAVAILABLE")
            )
            return files, state
        finally:
            os.close(fd)
    except OSError:
        return {}, unknown("DIRECTORY_UNAVAILABLE")


def health_status():
    # GET /healthz is the transport readiness route. Record only the status.
    # HTTPConnection uses no proxy and never follows redirects.
    connection = http.client.HTTPConnection("127.0.0.1", 8090, timeout=2)
    try:
        connection.request("GET", "/healthz", headers={"Connection": "close"})
        with connection.getresponse() as response:
            return {"state": "OBSERVED", "status": response.status}
    except (OSError, http.client.HTTPException):
        return unknown("HTTP_UNAVAILABLE")
    finally:
        connection.close()


def inventory():
    if socket.gethostname() != HOST:
        return unknown("WRONG_HOST")
    units = {name: unit(name) for name in UNITS}
    api_process, web_process = identity(units[API]), identity(units[WEB])
    files = {
        path: {
            "observation": fingerprint(f"/proc/{api_process[0]}/cwd", path)
            if api_process else unknown("PROCESS_UNAVAILABLE"),
        }
        for path in API_FILES
    }
    directories = {}
    for directory in API_DIRECTORIES:
        discovered, status = (
            inventory_directory(f"/proc/{api_process[0]}/cwd", directory)
            if api_process else ({}, unknown("PROCESS_UNAVAILABLE"))
        )
        files.update(discovered)
        directories[directory] = status
    api_paths = tuple(files)
    for path, (target, expected_source) in WEB_FILES.items():
        observed = (
            fingerprint(f"/proc/{web_process[0]}/root", target)
            if web_process else unknown("PROCESS_UNAVAILABLE")
        )
        candidate = fingerprint("/", expected_source)
        files[path] = {
            "observation": observed,
            "expected_mount_source": "/" + expected_source,
            "mount_content_matches": (
                observed["sha256"] == candidate["sha256"]
                if observed["state"] == candidate["state"] == "OBSERVED" else None
            ),
        }

    health = health_status() if api_process else unknown("PROCESS_UNAVAILABLE")
    for name, process, paths in ((API, api_process, api_paths), (WEB, web_process, WEB_FILES)):
        if process and process != identity(unit(name)):
            for path in paths:
                files[path]["observation"] = unknown("PROCESS_CHANGED")
                if "mount_content_matches" in files[path]:
                    files[path]["mount_content_matches"] = None
            if name == API:
                health = unknown("PROCESS_CHANGED")
                directories = dict.fromkeys(API_DIRECTORIES, unknown("PROCESS_CHANGED"))

    return {
        "inventory_schema": "cat-prod-inventory/3.0.0",
        "host": HOST,
        "observed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "units": units,
        "files": files,
        "directories": directories,
        "routes": {"GET /healthz": health},
    }


if __name__ == "__main__":
    report = inventory()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("state") == "UNKNOWN":
        raise SystemExit(1)
PY
