"""Bounded, one-shot observation; stdout only, no runtime imports or writes.

Run as an existing authorized account. This tool grants no permissions and
never opens secret files, environment files, journals or process environments.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import selectors
import stat
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

VERSION = "machine-observatory/0.1"
MAX_BYTES = 4 * 1024 * 1024
UNITS = (
    "crypto-advisor.service", "paper-arena.service",
    "crypto-quant-observer.service", "crypto-radar-bot.service",
    "crypto-dashboard.service", "crypto-operator-api.service",
    "crypto-operator-web.service", "crypto-market-snapshot.service",
    "crypto-publish-runtime-service.service", "crypto-publish-storage.service",
)
PROPERTIES = ("Id", "LoadState", "ActiveState", "SubState", "MainPID", "NRestarts")
COMMAND = ("/usr/bin/systemctl", "show", "--no-pager",
           "--property=" + ",".join(PROPERTIES), "--", *UNITS)
ENDPOINTS = ("snapshot", "ppl-comparison", "burn-in", "events",
             "financial-reconciliation", "ppl-accounting-history",
             "runtime-service", "storage", "market", "research-lab")
ARTIFACTS = {
    "operator": "databases/operator_snapshot.json",
    "burn_in": "databases/burn_in_status_snapshot.json",
    "events": "databases/event_center_snapshot.json",
    "financial": "databases/financial_reconciliation_snapshot.json",
    "paper_trades": "databases/paper_trades.jsonl",
}
SECRET_FILES = (".env", ".env.secret", ".env.secrets")
EVENT_TYPES = {"EPOCH_CREATED", "POSITION_OPENED", "POSITION_CLOSED",
               "POSITION_UNRESOLVED", "RECOVERY_COMPLETED"}


class CaptureError(ValueError):
    """Closed error code, never contains a source value."""


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def open_parent(path):
    """Anchor every component with dir_fd; refuse symlinks including parents."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
        raise CaptureError("INVALID_PATH")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        return fd, path.name
    except BaseException:
        os.close(fd)
        raise


def error_code(error):
    if isinstance(error, CaptureError):
        return str(error)
    if isinstance(error, PermissionError):
        return "DENIED"
    if isinstance(error, FileNotFoundError):
        return "MISSING"
    if isinstance(error, OSError) and error.errno in (errno.ELOOP, errno.ENOTDIR):
        return "INVALID_PATH"
    return "UNAVAILABLE"


def file_metadata(path):
    """No file content reads, including for secret files; readability unknown."""
    parent = None
    try:
        parent, name = open_parent(path)
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise CaptureError("INVALID_PATH")
        return {"status": "PRESENT", "bytes": info.st_size,
                "mtime_ns": info.st_mtime_ns, "mode": oct(stat.S_IMODE(info.st_mode)),
                "uid": info.st_uid, "gid": info.st_gid,
                "content_read": False, "content_readability": "NOT_TESTED"}
    except (OSError, CaptureError) as error:
        return {"status": error_code(error), "content_read": False}
    finally:
        if parent is not None:
            os.close(parent)


def read_epoch(path):
    """Count a stable bounded JSONL boundary; never export payloads or errors."""
    parent = descriptor = None
    try:
        parent, name = open_parent(path)
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=parent)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise CaptureError("INVALID_PATH")
        if before.st_size > MAX_BYTES:
            raise CaptureError("LIMIT_EXCEEDED")
        data = bytearray()
        while len(data) <= MAX_BYTES:
            chunk = os.read(descriptor, min(65536, MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        def signature(info):
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if signature(before) != signature(after) or signature(after) != signature(current):
            raise CaptureError("SOURCE_CHANGED")
        if len(data) > MAX_BYTES:
            raise CaptureError("LIMIT_EXCEEDED")
        if not data or not data.endswith(b"\n"):
            raise CaptureError("EMPTY_OR_INCOMPLETE")
        lines = data.splitlines()
        if len(lines) > 20000:
            raise CaptureError("LIMIT_EXCEEDED")
        events = [strict_json(line) for line in lines]
        summary = event_summary(events)
        return {"status": "CAPTURED", "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(), **summary,
                "validation": "STRUCTURAL_SUMMARY_ONLY_NOT_PPL_REPLAY"}
    except (OSError, CaptureError) as error:
        return {"status": error_code(error)}
    except (ValueError, TypeError, RecursionError, UnicodeError):
        return {"status": "INVALID_DOCUMENT"}
    finally:
        for fd in (descriptor, parent):
            if fd is not None:
                os.close(fd)


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CaptureError("INVALID_DOCUMENT")
            result[key] = value
        return result

    def constant(_value):
        raise CaptureError("INVALID_DOCUMENT")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def event_summary(events):
    if not isinstance(events, list) or len(events) > 20000:
        raise CaptureError("INVALID_DOCUMENT")
    counts = Counter()
    sequences = []
    for event in events:
        if not isinstance(event, dict):
            raise CaptureError("INVALID_DOCUMENT")
        kind = event.get("event_type")
        sequence = event.get("sequence")
        if not isinstance(kind, str) or kind not in EVENT_TYPES:
            raise CaptureError("UNKNOWN_EVENT_TYPE")
        if type(sequence) is not int or sequence < 1:
            raise CaptureError("INVALID_SEQUENCE")
        counts[kind] += 1
        sequences.append(sequence)
    return {"events": len(events), "event_counts": dict(sorted(counts.items())),
            "first_sequence": sequences[0] if sequences else None,
            "last_sequence": sequences[-1] if sequences else None,
            "contiguous_from_one": sequences == list(range(1, len(events) + 1))}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_probe(endpoint, *, opener=None):
    if endpoint not in ENDPOINTS:
        raise CaptureError("INVALID_ENDPOINT")
    # Ignore proxy environment and refuse redirects, including to external hosts.
    try:
        opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open("http://127.0.0.1:8090/api/operator/v1/" + endpoint,
                         timeout=3) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise CaptureError("LIMIT_EXCEEDED")
        doc = strict_json(raw)
        if not isinstance(doc, dict):
            raise CaptureError("INVALID_DOCUMENT")
        result = {"status": "RESPONDED", "http_status": 200,
                  "contract_validation": "NOT_PERFORMED",
                  "observed_at_utc": utc_now()}
        age = doc.get("snapshot_age_s")
        if type(age) in (int, float) and 0 <= age < 10**12:
            result["snapshot_age_s"] = age
        freshness = doc.get("freshness_classification")
        result["freshness"] = freshness if freshness in ("FRESH", "STALE", "UNKNOWN") else "UNKNOWN"
        if endpoint == "ppl-comparison":
            result.update(event_summary(doc.get("ppl_events")))
        return result
    except urllib.error.HTTPError as error:
        try:
            return {"status": "HTTP_ERROR", "http_status": error.code}
        finally:
            error.close()
    except CaptureError as error:
        return {"status": str(error)}
    except (OSError, ValueError, TypeError, RecursionError, UnicodeError):
        return {"status": "UNAVAILABLE"}


def service_probe():
    """Fixed command, clean environment, no stderr, bounded output and deadline."""
    try:
        with subprocess.Popen(COMMAND, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              stdin=subprocess.DEVNULL, env={"LC_ALL": "C"},
                              shell=False) as process:
            try:
                data = bytearray()
                deadline = time.monotonic() + 3
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(remaining):
                            raise CaptureError("TIMEOUT")
                        chunk = os.read(process.stdout.fileno(), 32769 - len(data))
                        if not chunk:
                            break
                        data.extend(chunk)
                        if len(data) > 32768:
                            raise CaptureError("LIMIT_EXCEEDED")
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
                if process.returncode != 0:
                    raise CaptureError("UNAVAILABLE")
            finally:
                if process.poll() is None:
                    process.kill()  # Only this collector's child, never a service.
                    process.wait()
        rows = []
        for block in data.decode().strip().split("\n\n"):
            values = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
            unit = values.get("Id")
            if unit not in UNITS:
                raise CaptureError("INVALID_DOCUMENT")
            row = {"unit": unit}
            for key in ("LoadState", "ActiveState", "SubState"):
                value = values.get(key)
                # Do not echo arbitrary values from a compromised subprocess.
                row[key] = value if value in {"loaded", "not-found", "masked", "error",
                    "active", "inactive", "failed", "activating", "deactivating",
                    "running", "dead", "exited", "waiting", "start", "stop"} else "UNKNOWN"
            rows.append(row)
        if {row["unit"] for row in rows} != set(UNITS) or len(rows) != len(UNITS):
            raise CaptureError("INVALID_DOCUMENT")
        return {"status": "CAPTURED", "services": rows,
                "egress_delivery": "NOT_VERIFIED"}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {"status": str(error) if isinstance(error, CaptureError) else "UNAVAILABLE"}


def capture(*, source_root, epoch, include_api=False, include_services=False):
    root = Path(source_root)
    if not root.is_absolute() or ".." in root.parts:
        raise CaptureError("INVALID_ROOT")
    if not epoch or len(epoch) > 128 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in epoch):
        raise CaptureError("INVALID_EPOCH")
    paths = {**ARTIFACTS,
             "epoch_config": f"databases/ppl_authority/{epoch}.burn-in-experiment-config.json"}
    digest = hashlib.sha256(epoch.encode()).hexdigest()
    epoch_path = root / "databases/ppl_authority/epochs" / (digest + ".jsonl")
    return {"schema": VERSION, "generated_at_utc": utc_now(),
            "mode": "READ_ONLY_ONE_SHOT", "runtime_deployed": "NOT_ATTESTED",
            "coverage": "FIXED_ALLOWLIST_NOT_GLOBAL_MACHINE_ACCESS",
            "artifacts": {key: file_metadata(root / path) for key, path in paths.items()},
            "secrets": {name: file_metadata(root / name) for name in SECRET_FILES},
            "secret_values": "NEVER_READ", "secret_variable_names": "NOT_COLLECTED",
            "ppl_boundary": read_epoch(epoch_path),
            "api": {ep: api_probe(ep) for ep in ENDPOINTS} if include_api else {"status": "NOT_REQUESTED"},
            "systemd": service_probe() if include_services else {"status": "NOT_REQUESTED"},
            "limitations": ["No cross-source atomicity", "No PPL replay or FIN reconciliation",
                            "No secret content or environment inspection",
                            "No complete network egress or Telegram delivery inventory",
                            "No access grants, scheduling, deployment or repair"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--epoch", required=True)
    parser.add_argument("--api", action="store_true", help="Fixed loopback GET probes")
    parser.add_argument("--services", action="store_true", help="Fixed systemctl show")
    args = parser.parse_args(argv)
    try:
        doc = capture(source_root=args.source_root, epoch=args.epoch,
                      include_api=args.api, include_services=args.services)
    except CaptureError as error:
        print(json.dumps({"schema": VERSION, "error_code": str(error)}))
        return 2
    print(json.dumps(doc, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
