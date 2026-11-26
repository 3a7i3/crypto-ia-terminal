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
# R7: recursive, bounded inventory of every regular .py under the API process working directory.
# Excluded at any depth: tooling and caches. Excluded only at the top level: runtime data
# directories (a tracked module such as quant_hedge_ai/databases/*.py stays in scope).
TREE_EXCLUDED_DIRECTORIES = frozenset((
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache",
))
TREE_EXCLUDED_TOP_LEVEL = frozenset(("data", "databases", "logs"))
TREE_MAX_DEPTH = 8
TREE_MAX_ENTRIES = 20000
TREE_MAX_FILES = 3000
TREE_NAME = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.-]{0,127}")
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


def in_tree_scope(path):
    """True when R7 would have walked to this path (no excluded directory on the way)."""
    parts = path.split("/")
    return not (
        (len(parts) > 1 and parts[0] in TREE_EXCLUDED_TOP_LEVEL)
        or any(part in TREE_EXCLUDED_DIRECTORIES for part in parts[:-1])
    )


def inventory_tree(anchor):
    """R7: hash every regular .py below the anchor directory; never follow a link.

    Only relative paths, sizes and digests are returned. Every excluded directory,
    skipped link, unlisted name, error and reached limit is declared. The tree is
    COMPLETE only when no limit was reached, no error occurred, every .py was read,
    and no link or invalid name could hide code.
    """
    report = {
        "excluded_directories": [], "skipped_symlinks": [], "skipped_invalid_names": 0,
        "unverified": {"symlinks": [], "invalid_names": 0},
        "errors": [], "limits_reached": [], "conflicts": [], "directories_scanned": 0, "entries_scanned": 0,
        "limits": {"max_depth": TREE_MAX_DEPTH, "max_entries": TREE_MAX_ENTRIES, "max_files": TREE_MAX_FILES},
    }
    files = {}
    stopped = []

    def limit(name, path):
        if not any(item["limit"] == name for item in report["limits_reached"]):
            report["limits_reached"].append({"limit": name, "at": path or "."})

    def excluded(name, depth):
        return name in TREE_EXCLUDED_DIRECTORIES or (depth == 0 and name in TREE_EXCLUDED_TOP_LEVEL)

    def walk(fd, prefix, depth):
        report["directories_scanned"] += 1
        before = os.fstat(fd)
        subdirs = []
        with os.scandir(fd) as entries:
            listed = []
            # The global entry cap is checked while the iterator is consumed, before
            # anything is kept or sorted; once exceeded the whole traversal stops.
            for entry in entries:
                if report["entries_scanned"] >= TREE_MAX_ENTRIES:
                    limit("max_entries", prefix)
                    stopped.append(True)
                    return
                report["entries_scanned"] += 1
                listed.append(entry)
            for entry in sorted(listed, key=lambda item: item.name):
                if not TREE_NAME.fullmatch(entry.name):
                    report["skipped_invalid_names"] += 1
                    # A link, a directory or a .py file behind an unprintable name may hide code.
                    if entry.is_symlink() or entry.is_dir(follow_symlinks=False) or (
                        entry.name.endswith(".py") and entry.is_file(follow_symlinks=False)
                    ):
                        report["unverified"]["invalid_names"] += 1
                    continue
                path = f"{prefix}{entry.name}"
                if entry.is_symlink():
                    report["skipped_symlinks"].append(path)
                    # Its target is never read, so it may be a directory or a module,
                    # unless its name is one of the declared exclusions.
                    if not excluded(entry.name, depth):
                        report["unverified"]["symlinks"].append(path)
                elif entry.is_dir(follow_symlinks=False):
                    if excluded(entry.name, depth):
                        report["excluded_directories"].append(path)
                    else:
                        subdirs.append(entry.name)
                elif entry.name.endswith(".py") and entry.is_file(follow_symlinks=False):
                    if len(files) >= TREE_MAX_FILES:
                        limit("max_files", prefix)
                        continue
                    files[path] = {"observation": fingerprint(f"/proc/self/fd/{fd}", entry.name)}
        for name in subdirs:
            if stopped:
                return
            path = f"{prefix}{name}"
            if depth >= TREE_MAX_DEPTH:
                limit("max_depth", path)
                continue
            try:
                child = os.open(name, DIR_FLAGS, dir_fd=fd)
            except OSError as error:
                report["errors"].append({"path": path, "reason": "DIRECTORY_UNAVAILABLE", "errno": error.errno})
                continue
            try:
                walk(child, path + "/", depth + 1)
            except OSError as error:
                report["errors"].append({"path": path, "reason": "DIRECTORY_UNREADABLE", "errno": error.errno})
            finally:
                os.close(child)
        if not stopped and file_stamp(before) != file_stamp(os.fstat(fd)):
            report["errors"].append({"path": prefix.rstrip("/") or ".", "reason": "DIRECTORY_CHANGED"})

    try:
        root = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return {}, {**report, **unknown("TREE_UNAVAILABLE")}
    try:
        walk(root, "", 0)
    except OSError as error:
        report["errors"].append({"path": ".", "reason": "DIRECTORY_UNREADABLE", "errno": error.errno})
    finally:
        os.close(root)
    unreadable = sorted(path for path, row in files.items() if row["observation"]["state"] != "OBSERVED")
    report["files_observed"] = len(files) - len(unreadable)
    report["files_unknown"] = unreadable
    complete = not (
        report["errors"] or report["limits_reached"] or unreadable
        or report["unverified"]["symlinks"] or report["unverified"]["invalid_names"]
    )
    report["state"] = "COMPLETE" if complete else "INCOMPLETE"
    return files, report


def merge_tree(files, tree_files, tree):
    """Give each API path one current fingerprint from R6 (named files) and R7 (tree).

    Matching observations are exported once. A divergence, an R7 read failure, or an
    in-scope R6 file that R7 did not see makes the path UNKNOWN, is declared in
    tree["conflicts"], and makes the tree INCOMPLETE: R6 alone is never exported then.
    files_observed and files_unknown are recomputed on the reconciled R7 scope.
    """
    digest = ("size", "git_blob_sha1", "sha256")
    for path in sorted(set(files) | set(tree_files)):
        if path not in files:
            files[path] = tree_files[path]
            continue
        r6 = files[path]["observation"]
        r7 = tree_files.get(path, {}).get("observation")
        if r7 is None:
            if r6["state"] != "OBSERVED" or not in_tree_scope(path):
                continue
            reason = "R7_NOT_SEEN"
        elif r6["state"] == r7["state"] == "OBSERVED":
            if all(r6.get(key) == r7.get(key) for key in digest):
                continue
            reason = "R6_R7_MISMATCH"
        elif r7["state"] != "OBSERVED":
            if r6["state"] != "OBSERVED":
                continue
            reason = "R7_UNREADABLE"
        else:
            reason = "R6_R7_MISMATCH"
        files[path] = {"observation": unknown(reason)}
        tree.setdefault("conflicts", []).append({"path": path, "reason": reason})
    if "files_observed" in tree:
        # Counters describe the reconciled observations of the R7 scope, not R7's raw reads.
        scope = set(tree_files) | {item["path"] for item in tree.get("conflicts", [])}
        unreadable = sorted(path for path in scope if files[path]["observation"]["state"] != "OBSERVED")
        tree["files_observed"] = len(scope) - len(unreadable)
        tree["files_unknown"] = unreadable
    if tree.get("conflicts") and tree.get("state") == "COMPLETE":
        tree["state"] = "INCOMPLETE"


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
    tree_files, tree = (
        inventory_tree(f"/proc/{api_process[0]}/cwd")
        if api_process else ({}, unknown("PROCESS_UNAVAILABLE"))
    )
    if api_process:
        merge_tree(files, tree_files, tree)
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
                tree = unknown("PROCESS_CHANGED")

    return {
        "inventory_schema": "cat-prod-inventory/3.0.0",
        "host": HOST,
        "observed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "units": units,
        "files": files,
        "directories": directories,
        "api_tree": tree,
        "routes": {"GET /healthz": health},
    }


if __name__ == "__main__":
    report = inventory()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("state") == "UNKNOWN":
        raise SystemExit(1)
PY
