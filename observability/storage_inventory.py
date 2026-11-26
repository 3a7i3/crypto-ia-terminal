"""Bounded metadata snapshot for the scanner and VPS disk."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import stat
import tempfile

GROUPS = ("raw", "candles", "generations", "root")
MAX_ENTRIES = 50_000
MAX_INT = 2**53 - 1


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def scan(root):
    summaries = {key: {"files": 0, "bytes": 0, "modified_at": None} for key in GROUPS}
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    entries = 0

    def visit(fd, device, group=None, depth=0):
        nonlocal entries
        if depth > 32:
            raise ValueError("depth limit")
        with os.scandir(fd) as children:
            for entry in children:
                entries += 1
                if entries > MAX_ENTRIES:
                    raise ValueError("entry limit")
                info = entry.stat(follow_symlinks=False)
                if info.st_dev != device or stat.S_ISLNK(info.st_mode):
                    continue
                if stat.S_ISDIR(info.st_mode):
                    category = group if group is not None else entry.name
                    if category not in GROUPS or category == "root":
                        raise ValueError("unknown directory")
                    child = os.open(entry.name, flags, dir_fd=fd)
                    try:
                        if os.fstat(child).st_dev != device:
                            raise ValueError("mount changed")
                        visit(child, device, category, depth + 1)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    row = summaries[group or "root"]
                    row["files"] += 1
                    row["bytes"] += info.st_size
                    modified = utc(info.st_mtime)
                    if row["modified_at"] is None or modified > row["modified_at"]:
                        row["modified_at"] = modified

    fd = os.open(root, flags)
    try:
        visit(fd, os.fstat(fd).st_dev)
    finally:
        os.close(fd)
    return summaries


def snapshot(root):
    try:
        groups = scan(root)
    except (OSError, ValueError, OverflowError):
        groups = None
    disk = os.statvfs("/")
    return {
        "version": 1, "observed_at": utc(datetime.now(timezone.utc).timestamp()),
        "scanner": groups,
        "disk": {
            "total_bytes": disk.f_blocks * disk.f_frsize,
            "used_bytes": (disk.f_blocks - disk.f_bfree) * disk.f_frsize,
            "available_bytes": disk.f_bavail * disk.f_frsize,
        },
    }


def valid(doc):
    def uint(value):
        return type(value) is int and 0 <= value <= MAX_INT

    def stamp(value):
        return isinstance(value, str) and value.endswith("Z") and utc(
            datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        ) == value

    if set(doc) != {"version", "observed_at", "scanner", "disk"} or type(doc["version"]) is not int or doc["version"] != 1 or not stamp(doc["observed_at"]):
        return False
    disk = doc["disk"]
    if set(disk) != {"total_bytes", "used_bytes", "available_bytes"} or not all(map(uint, disk.values())):
        return False
    if not disk["total_bytes"] or disk["used_bytes"] + disk["available_bytes"] > disk["total_bytes"]:
        return False
    scanner = doc["scanner"]
    if scanner is None:
        return True
    if set(scanner) != set(GROUPS):
        return False
    for row in scanner.values():
        if set(row) != {"files", "bytes", "modified_at"} or not uint(row["files"]) or not uint(row["bytes"]):
            return False
        if row["files"]:
            if not stamp(row["modified_at"]) or row["modified_at"] > doc["observed_at"]:
                return False
        elif row["bytes"] or row["modified_at"] is not None:
            return False
    return sum(r["files"] for r in scanner.values()) <= MAX_ENTRIES and sum(r["bytes"] for r in scanner.values()) <= MAX_INT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-store", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.live_store.resolve(), args.out.absolute()
    if out.parent.resolve().is_relative_to(root):
        parser.error("output must be outside live-store")

    def deadline(*_):
        raise TimeoutError("inventory deadline")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(15)
    try:
        doc = snapshot(args.live_store)
    finally:
        signal.alarm(0)
    if not valid(doc):
        doc["scanner"] = None
    if not valid(doc):
        parser.error("invalid disk metadata")
    with tempfile.NamedTemporaryFile(mode="w", dir=out.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            # The output directory must be dedicated to this publisher.
            os.fchmod(stream.fileno(), 0o644)
            json.dump(doc, stream, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, out)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
