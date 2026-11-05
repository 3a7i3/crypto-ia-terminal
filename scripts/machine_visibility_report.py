"""One-shot filtered diagnostics; no service mutation or raw log export."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import pwd
import selectors
import shlex
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path

if __package__:
    from .machine_observatory import file_metadata, service_probe, utc_now
else:
    from machine_observatory import file_metadata, service_probe, utc_now

LOG_UNITS = ("crypto-advisor.service", "paper-arena.service",
             "crypto-operator-api.service", "crypto-operator-web.service",
             "crypto-quant-observer.service", "crypto-radar-bot.service",
             "crypto-narrator.service", "crypto-burnin-chronicle.service")
UNIT_FILES = (
    "/etc/systemd/system/crypto-operator-api.service",
    "/etc/systemd/system/crypto-operator-api.service.d/20-canonical-runtime.conf",
    "/etc/systemd/system/crypto-operator-api.service.d/30-presentation-paths.conf",
    "/etc/systemd/system/crypto-publish-runtime-service.service",
    "/etc/systemd/system/crypto-publish-storage.service",
    "/etc/systemd/system/crypto-burnin-chronicle.timer",
)
PATH_KEYS = {"BURN_IN_STATUS_SNAPSHOT_PATH", "EVENT_CENTER_SNAPSHOT_PATH",
             "OPERATOR_SNAPSHOT_PATH", "RUNTIME_SERVICE_SNAPSHOT_PATH",
             "STORAGE_SNAPSHOT_PATH", "RADAR_MARKET_SNAPSHOT_PATH"}
ALLOWED_PREFIXES = ("/home/mathieu/crypto_ai_terminal/", "/home/mathieu/operator_presentation/",
                    "/opt/crypto-ai-terminal/operator/")


def journal_command(unit):
    if unit not in LOG_UNITS:
        raise ValueError("INVALID_UNIT")
    return ("/usr/bin/journalctl", "--no-pager", "--quiet", "--output=json",
            "--since=-24h", "--lines=200", "--unit=" + unit)


def bounded_journal(unit):
    """Bounded child and clean environment; stderr is never collected."""
    try:
        with subprocess.Popen(journal_command(unit), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"}, shell=False) as process:
            try:
                data = bytearray()
                deadline = time.monotonic() + 3
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(remaining):
                            return {"status": "TIMEOUT"}
                        chunk = os.read(process.stdout.fileno(), 1048577 - len(data))
                        if not chunk:
                            break
                        data.extend(chunk)
                        if len(data) > 1048576:
                            return {"status": "OUTPUT_LIMIT"}
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
                if process.returncode != 0:
                    return {"status": "UNAVAILABLE"}
                return summarize_journal(bytes(data))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    except (OSError, subprocess.SubprocessError):
        return {"status": "UNAVAILABLE"}


def summarize_journal(raw):
    """Only numeric priority counts leave this boundary. No MESSAGE/fields."""
    if len(raw) > 1048576:
        return {"status": "OUTPUT_LIMIT"}
    if not raw.strip():
        return {"status": "NO_VISIBLE_RECORDS", "permission": "NOT_PROVEN"}
    counts = Counter()
    lines = raw.splitlines()
    if len(lines) > 200:
        return {"status": "OUTPUT_LIMIT"}
    try:
        for line in lines:
            record = json.loads(line)
            if not isinstance(record, dict):
                return {"status": "INVALID_DOCUMENT"}
            priority = record.get("PRIORITY")
            key = str(priority) if type(priority) in (str, int) and str(priority) in tuple(str(i) for i in range(8)) else "UNKNOWN"
            counts[key] += 1
    except (ValueError, UnicodeError, RecursionError):
        return {"status": "INVALID_DOCUMENT"}
    return {"status": "VISIBLE_WINDOW", "records": len(lines),
            "priority_counts": dict(sorted(counts.items())),
            "coverage": "LAST_200_IN_24H_NOT_COMPLETE", "messages_exported": False,
            "delivery_success": "NOT_VERIFIED"}


def safe_path(value):
    return (isinstance(value, str) and len(value) < 512 and
            value.startswith(ALLOWED_PREFIXES) and ".." not in Path(value).parts and
            all(c in "/abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in value))


def summarize_unit(text):
    """Drop raw commands and all environment values except fixed path keys."""
    paths = {}
    for line in text.splitlines():
        if line.startswith("Environment="):
            for item in shlex.split(line.split("=", 1)[1]):
                key, _, value = item.partition("=")
                if key in PATH_KEYS:
                    paths[key] = value if safe_path(value) else "REJECTED_VALUE"
        elif line.startswith("WorkingDirectory="):
            value = line.split("=", 1)[1]
            paths["WorkingDirectory"] = value if safe_path(value + "/") else "REJECTED_VALUE"
    return {"declared_path_settings": paths, "raw_content_exported": False,
            "effective_configuration": "NOT_ATTESTED_NO_SYSTEMD_EXPANSION"}


def unit_reports():
    reports = {}
    for name in UNIT_FILES:
        path = Path(name)
        metadata = file_metadata(path)
        row = {"metadata": metadata}
        if metadata["status"] == "PRESENT":
            try:
                # System-owned fixed files only; refuse oversized and final links.
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as stream:
                    raw = stream.read(65537)
                if len(raw) > 65536:
                    row["settings"] = {"status": "OUTPUT_LIMIT"}
                else:
                    row["settings"] = summarize_unit(raw.decode())
            except (OSError, ValueError, UnicodeError):
                row["settings"] = {"status": "UNAVAILABLE"}
        reports[name] = row
    return reports


def capture():
    return {"schema": "machine-visibility/0.1", "captured_at_utc": utc_now(),
            "mode": "READ_ONLY_ONE_SHOT", "services": service_probe(),
            "unit_files": unit_reports(),
            "journals": {unit: bounded_journal(unit) for unit in LOG_UNITS},
            "limits": ["Fixed allowlist, not full VPS access", "No raw log messages or secret files exported",
                       "Journal messages processed locally for priority counts only",
                       "No live refresh, no service control, no delivery certification",
                       "No-visible-records does not prove no activity or journal access",
                       "Unit file settings are declarations, not effective merged configuration"]}


def share(doc):
    uid = pwd.getpwnam("chatgpt-ro").pw_uid
    if uid == os.geteuid():
        raise ValueError("USE_OPERATOR_ACCOUNT")
    lib = ctypes.CDLL("libacl.so.1", use_errno=True)
    lib.acl_from_text.argtypes, lib.acl_from_text.restype = [ctypes.c_char_p], ctypes.c_void_p
    lib.acl_set_file.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]
    lib.acl_set_file.restype = ctypes.c_int
    lib.acl_free.argtypes, lib.acl_free.restype = [ctypes.c_void_p], ctypes.c_int
    root = Path(tempfile.mkdtemp(prefix="sentinel-visibility-", dir="/var/tmp"))
    path = root / "visibility.json"
    raw = json.dumps(doc, sort_keys=True, allow_nan=False).encode()
    if len(raw) > 262144:
        raise ValueError("REPORT_LIMIT")
    try:
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(raw)
        for target, owner, reader in ((path, "r--", "r--"), (root, "rwx", "r-x")):
            acl = lib.acl_from_text(f"u::{owner},u:{uid}:{reader},g::---,m::{reader},o::---".encode())
            if not acl:
                raise ValueError("ACL_FAILED")
            try:
                if lib.acl_set_file(os.fsencode(target), 0x8000, acl):
                    raise ValueError("ACL_FAILED")
            finally:
                lib.acl_free(acl)
    except BaseException:
        os.chmod(root, 0o700)
        raise
    return root, hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()
    if args.share and pwd.getpwuid(os.geteuid()).pw_name != "mathieu":
        raise SystemExit("EXECUTER_COMME_MATHIEU_SANS_SUDO")
    try:
        doc = capture()
        if args.share:
            root, digest = share(doc)
            print("OBSERVATION=" + str(root))
            print("SHA256=" + digest)
            print("REVOQUER : chmod 700 " + str(root))
        else:
            print(json.dumps(doc, sort_keys=True, allow_nan=False))
    except (OSError, ValueError, TypeError):
        raise SystemExit("CAPTURE_FAILED_NO_SERVICE_MODIFIED") from None


if __name__ == "__main__":
    main()
