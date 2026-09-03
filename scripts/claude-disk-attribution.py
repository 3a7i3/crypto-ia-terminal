#!/usr/bin/env python3
"""Emit a bounded, content-free allocation map for the root filesystem."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA_VERSION = 1
PACK_NAME = "disk_attribution"
ROOT_PATH = "/"
SCAN_TIMEOUT_SECONDS = 45
MAX_ENTRIES = 500_000
MAX_DEPTH = 32
MAX_BUCKETS = 64
MAX_OUTPUT_BYTES = 16_000
Monotonic = Callable[[], float]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def catalog_sha256() -> str:
    canonical = json.dumps(
        {"root": ROOT_PATH, "bucket_rule": "first_path_component"},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def filesystem_observation() -> dict[str, Any]:
    try:
        value = os.statvfs(ROOT_PATH)
    except OSError:
        return {"path": ROOT_PATH, "query_status": "query_error"}
    size = value.f_frsize or value.f_bsize
    total = size * value.f_blocks
    free = size * value.f_bfree
    used = max(0, total - free)
    return {
        "path": ROOT_PATH,
        "query_status": "ok",
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "available_bytes_unprivileged": size * value.f_bavail,
        "used_basis_points": round(used * 10_000 / total) if total else None,
    }


def _empty() -> dict[str, int]:
    return {"allocated_bytes": 0, "logical_bytes": 0, "regular_file_count": 0}


def _add(target: dict[str, int], value: os.stat_result) -> None:
    target["allocated_bytes"] += max(0, value.st_blocks * 512)
    target["logical_bytes"] += max(0, value.st_size)
    target["regular_file_count"] += 1


def scan_root(monotonic: Monotonic = time.monotonic) -> dict[str, Any]:
    """Aggregate regular-file metadata by first component without reading data."""

    started = monotonic()
    try:
        root_stat = Path(ROOT_PATH).stat(follow_symlinks=False)
    except OSError:
        return {"query_status": "query_error", "scan_status": "not_scanned"}

    device = root_stat.st_dev
    deadline = started + SCAN_TIMEOUT_SECONDS
    stack: list[tuple[Path, int, str | None]] = [(Path(ROOT_PATH), 0, None)]
    seen: set[tuple[int, int]] = set()
    buckets: dict[str, dict[str, int]] = {}
    totals = _empty()
    counters = {
        "entries_examined": 0,
        "directory_count": 1,
        "symlink_count": 0,
        "special_entry_count": 0,
        "hardlink_duplicate_count": 0,
        "permission_denied_count": 0,
        "metadata_error_count": 0,
        "cross_filesystem_skipped_count": 0,
        "depth_limit_skipped_count": 0,
    }
    limit_reason = "none"

    while stack:
        if monotonic() > deadline:
            limit_reason = "timeout"
            break
        directory, depth, inherited_bucket = stack.pop()
        try:
            iterator = os.scandir(directory)
        except PermissionError:
            counters["permission_denied_count"] += 1
            continue
        except OSError:
            counters["metadata_error_count"] += 1
            continue
        with iterator:
            for entry in iterator:
                if counters["entries_examined"] >= MAX_ENTRIES:
                    limit_reason = "entry_limit"
                    break
                counters["entries_examined"] += 1
                try:
                    value = entry.stat(follow_symlinks=False)
                except PermissionError:
                    counters["permission_denied_count"] += 1
                    continue
                except OSError:
                    counters["metadata_error_count"] += 1
                    continue
                bucket_name = inherited_bucket or entry.name
                if value.st_dev != device:
                    counters["cross_filesystem_skipped_count"] += 1
                elif stat.S_ISLNK(value.st_mode):
                    counters["symlink_count"] += 1
                elif stat.S_ISDIR(value.st_mode):
                    counters["directory_count"] += 1
                    if depth >= MAX_DEPTH:
                        counters["depth_limit_skipped_count"] += 1
                    else:
                        stack.append((Path(entry.path), depth + 1, bucket_name))
                elif stat.S_ISREG(value.st_mode):
                    inode = (value.st_dev, value.st_ino)
                    if inode in seen:
                        counters["hardlink_duplicate_count"] += 1
                        continue
                    seen.add(inode)
                    bucket = buckets.setdefault(bucket_name, _empty())
                    _add(bucket, value)
                    _add(totals, value)
                else:
                    counters["special_entry_count"] += 1
            if limit_reason == "entry_limit":
                break

    ordered = sorted(
        buckets.items(),
        key=lambda item: (-item[1]["allocated_bytes"], item[0]),
    )
    rendered = [{"name": name, **values} for name, values in ordered[:MAX_BUCKETS]]
    if len(ordered) > MAX_BUCKETS:
        other = _empty()
        for _, values in ordered[MAX_BUCKETS:]:
            for key in other:
                other[key] += values[key]
        rendered.append(
            {"name": "[other_buckets]", "omitted_bucket_count": len(ordered) - MAX_BUCKETS, **other}
        )

    has_errors = counters["permission_denied_count"] or counters["metadata_error_count"]
    if limit_reason != "none" or counters["depth_limit_skipped_count"]:
        scan_status = "limited"
        if limit_reason == "none":
            limit_reason = "depth_limit"
    elif has_errors:
        scan_status = "partial"
    else:
        scan_status = "complete"
    return {
        "query_status": "ok",
        "scan_status": scan_status,
        "limit_reason": limit_reason,
        "scan_duration_milliseconds": max(0, round((monotonic() - started) * 1000)),
        "bucket_count": len(ordered),
        **totals,
        **counters,
        "buckets": rendered,
    }


def collect_snapshot(observed_at_utc: str | None = None) -> tuple[dict[str, Any], int]:
    filesystem = filesystem_observation()
    allocation = scan_root()
    complete = filesystem.get("query_status") == "ok" and allocation.get("scan_status") == "complete"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pack": PACK_NAME,
        "observed_at_utc": observed_at_utc or utc_now(),
        "collection_status": "complete" if complete else "partial",
        "catalog_sha256": catalog_sha256(),
        "contract": {
            "fixed_root": ROOT_PATH,
            "bucket_rule": "first_path_component",
            "scan_timeout_seconds": SCAN_TIMEOUT_SECONDS,
            "max_entries": MAX_ENTRIES,
            "max_depth": MAX_DEPTH,
            "max_buckets": MAX_BUCKETS,
            "max_output_bytes": MAX_OUTPUT_BYTES,
            "file_content_read": False,
            "file_paths_emitted": False,
            "symlinks_followed": False,
            "cross_filesystems": False,
            "local_baseline_written": False,
            "raw_errors_emitted": False,
        },
        "filesystem": filesystem,
        "allocation": allocation,
    }
    return payload, 0 if complete else 69


def render_snapshot(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if len(rendered.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError("disk attribution snapshot exceeds output limit")
    return rendered


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("DISK_ATTRIBUTION_REJECTED: arguments are not accepted", file=sys.stderr)
        return 64
    payload, exit_code = collect_snapshot()
    try:
        sys.stdout.write(render_snapshot(payload))
    except ValueError:
        print("DISK_ATTRIBUTION_OUTPUT_LIMIT_EXCEEDED", file=sys.stderr)
        return 70
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
