#!/usr/bin/env python3
"""Emit a bounded, content-free snapshot of runtime disk allocation.

The pack accepts no arguments, scans two fixed runtime roots without following
symlinks or crossing filesystems, and reads metadata only.  Growth is derived
later by comparing two immutable GitHub evidence envelopes; this program never
writes a baseline on the VPS.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA_VERSION = 1
PACK_NAME = "disk_growth"
FILESYSTEM_PATH = "/"
SCAN_TIMEOUT_SECONDS = 8
MAX_ENTRIES_PER_ROOT = 50_000
MAX_DEPTH = 12
MAX_BUCKETS_PER_ROOT = 24
MAX_LARGEST_FILES = 20
MAX_RELATIVE_PATH_LENGTH = 160
MAX_OUTPUT_BYTES = 24_000


@dataclass(frozen=True)
class RootSpec:
    """One immutable runtime root and its stable evidence label."""

    label: str
    path: str


ROOT_CATALOG = (
    RootSpec("databases", "/home/mathieu/crypto_ai_terminal/databases"),
    RootSpec("logs", "/home/mathieu/crypto_ai_terminal/logs"),
)

Monotonic = Callable[[], float]


def utc_now() -> str:
    """Return a second-resolution UTC timestamp for the observation."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def catalog_sha256(catalog: Sequence[RootSpec] = ROOT_CATALOG) -> str:
    """Hash the ordered fixed-root catalog for cross-run comparability."""

    canonical = json.dumps(
        [[item.label, item.path] for item in catalog],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def safe_relative_path(relative_path: str) -> str:
    """Bound path metadata and hash names containing unsafe characters."""

    valid = (
        0 < len(relative_path) <= MAX_RELATIVE_PATH_LENGTH
        and not relative_path.startswith("/")
        and all(character.isprintable() for character in relative_path)
    )
    if valid:
        return relative_path
    digest = hashlib.sha256(os.fsencode(relative_path)).hexdigest()
    return f"path_sha256:{digest}"


def timestamp_utc(timestamp: float) -> str:
    """Convert one filesystem timestamp to bounded UTC or return unknown."""

    try:
        return (
            datetime.fromtimestamp(timestamp, timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError):
        return "unknown"


def filesystem_observation(path: str = FILESYSTEM_PATH) -> dict[str, Any]:
    """Read fixed-filesystem capacity and inode metadata through statvfs."""

    try:
        value = os.statvfs(path)
    except FileNotFoundError:
        return {"path": path, "query_status": "not_found"}
    except PermissionError:
        return {"path": path, "query_status": "permission_denied"}
    except OSError:
        return {"path": path, "query_status": "query_error"}

    fragment_size = value.f_frsize or value.f_bsize
    total_bytes = fragment_size * value.f_blocks
    free_bytes = fragment_size * value.f_bfree
    available_bytes = fragment_size * value.f_bavail
    used_bytes = max(0, total_bytes - free_bytes)
    used_basis_points = (
        round(used_bytes * 10_000 / total_bytes) if total_bytes else None
    )
    used_inodes = max(0, value.f_files - value.f_ffree)
    inode_used_basis_points = (
        round(used_inodes * 10_000 / value.f_files) if value.f_files else None
    )
    return {
        "path": path,
        "query_status": "ok",
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "available_bytes_unprivileged": available_bytes,
        "used_basis_points": used_basis_points,
        "total_inodes": value.f_files,
        "used_inodes": used_inodes,
        "free_inodes": value.f_ffree,
        "inode_used_basis_points": inode_used_basis_points,
    }


def _empty_bucket() -> dict[str, int]:
    """Create counters for one stable first-level runtime bucket."""

    return {
        "allocated_bytes": 0,
        "logical_bytes": 0,
        "regular_file_count": 0,
    }


def _add_file(bucket: dict[str, int], file_stat: os.stat_result) -> None:
    """Accumulate one regular file using metadata, never file content."""

    bucket["allocated_bytes"] += max(0, file_stat.st_blocks * 512)
    bucket["logical_bytes"] += max(0, file_stat.st_size)
    bucket["regular_file_count"] += 1


def _offer_largest(
    largest: list[dict[str, Any]],
    candidate: dict[str, Any],
) -> None:
    """Retain only the fixed number of largest allocated regular files."""

    largest.append(candidate)
    largest.sort(
        key=lambda item: (
            -item["allocated_bytes"],
            -item["logical_bytes"],
            item["root_label"],
            item["relative_path"],
        )
    )
    del largest[MAX_LARGEST_FILES:]


def _render_buckets(buckets: dict[str, dict[str, int]]) -> tuple[list[dict[str, Any]], int]:
    """Return the largest fixed number of buckets and aggregate the remainder."""

    ordered = sorted(
        buckets.items(),
        key=lambda item: (
            -item[1]["allocated_bytes"],
            -item[1]["logical_bytes"],
            item[0],
        ),
    )
    kept = ordered[:MAX_BUCKETS_PER_ROOT]
    omitted = ordered[MAX_BUCKETS_PER_ROOT:]
    rendered = [{"name": name, **values} for name, values in kept]
    if omitted:
        aggregate = _empty_bucket()
        for _, values in omitted:
            for key in aggregate:
                aggregate[key] += values[key]
        rendered.append(
            {
                "name": "[other_buckets]",
                "omitted_bucket_count": len(omitted),
                **aggregate,
            }
        )
    return rendered, len(ordered)


def scan_root(
    spec: RootSpec,
    monotonic: Monotonic = time.monotonic,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Scan one fixed root under entry, depth, time and mount boundaries."""

    started = monotonic()
    root = Path(spec.path)
    try:
        root_stat = root.stat(follow_symlinks=False)
    except FileNotFoundError:
        return _absent_root(spec, "not_found", started, monotonic), []
    except PermissionError:
        return _absent_root(spec, "permission_denied", started, monotonic), []
    except OSError:
        return _absent_root(spec, "query_error", started, monotonic), []

    if not stat.S_ISDIR(root_stat.st_mode):
        return _absent_root(spec, "not_directory", started, monotonic), []

    root_device = root_stat.st_dev
    deadline = started + SCAN_TIMEOUT_SECONDS
    stack: list[tuple[Path, int, str | None]] = [(root, 0, None)]
    seen_inodes: set[tuple[int, int]] = set()
    buckets: dict[str, dict[str, int]] = {}
    totals = _empty_bucket()
    largest: list[dict[str, Any]] = []
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
    newest_mtime = root_stat.st_mtime

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
                if counters["entries_examined"] >= MAX_ENTRIES_PER_ROOT:
                    limit_reason = "entry_limit"
                    stack.clear()
                    break
                if monotonic() > deadline:
                    limit_reason = "timeout"
                    stack.clear()
                    break
                counters["entries_examined"] += 1
                try:
                    entry_stat = entry.stat(follow_symlinks=False)
                except PermissionError:
                    counters["permission_denied_count"] += 1
                    continue
                except OSError:
                    counters["metadata_error_count"] += 1
                    continue

                newest_mtime = max(newest_mtime, entry_stat.st_mtime)
                relative = os.path.relpath(entry.path, spec.path)
                first_component = relative.split(os.sep, 1)[0]
                bucket_name = inherited_bucket or (
                    "[root_files]"
                    if stat.S_ISREG(entry_stat.st_mode)
                    else safe_relative_path(first_component)
                )

                if stat.S_ISLNK(entry_stat.st_mode):
                    counters["symlink_count"] += 1
                    continue
                if stat.S_ISDIR(entry_stat.st_mode):
                    counters["directory_count"] += 1
                    if entry_stat.st_dev != root_device:
                        counters["cross_filesystem_skipped_count"] += 1
                    elif depth >= MAX_DEPTH:
                        counters["depth_limit_skipped_count"] += 1
                    else:
                        stack.append((Path(entry.path), depth + 1, bucket_name))
                    continue
                if not stat.S_ISREG(entry_stat.st_mode):
                    counters["special_entry_count"] += 1
                    continue

                inode_key = (entry_stat.st_dev, entry_stat.st_ino)
                if inode_key in seen_inodes:
                    counters["hardlink_duplicate_count"] += 1
                    continue
                seen_inodes.add(inode_key)
                bucket = buckets.setdefault(bucket_name, _empty_bucket())
                _add_file(bucket, entry_stat)
                _add_file(totals, entry_stat)
                _offer_largest(
                    largest,
                    {
                        "root_label": spec.label,
                        "relative_path": safe_relative_path(relative),
                        "allocated_bytes": max(0, entry_stat.st_blocks * 512),
                        "logical_bytes": max(0, entry_stat.st_size),
                        "mtime_utc": timestamp_utc(entry_stat.st_mtime),
                    },
                )

    rendered_buckets, bucket_count = _render_buckets(buckets)
    has_errors = counters["permission_denied_count"] or counters["metadata_error_count"]
    scan_status = "complete"
    if limit_reason != "none":
        scan_status = "limited"
    elif counters["depth_limit_skipped_count"]:
        limit_reason = "depth_limit"
        scan_status = "limited"
    elif has_errors:
        scan_status = "partial"
    record = {
        "label": spec.label,
        "path": spec.path,
        "query_status": "ok",
        "scan_status": scan_status,
        "limit_reason": limit_reason,
        "scan_duration_milliseconds": max(0, round((monotonic() - started) * 1000)),
        "newest_metadata_mtime_utc": timestamp_utc(newest_mtime),
        "bucket_count": bucket_count,
        **totals,
        **counters,
        "buckets": rendered_buckets,
    }
    return record, largest


def _absent_root(
    spec: RootSpec,
    query_status: str,
    started: float,
    monotonic: Monotonic,
) -> dict[str, Any]:
    """Build a content-free record when a fixed root cannot be scanned."""

    return {
        "label": spec.label,
        "path": spec.path,
        "query_status": query_status,
        "scan_status": "not_scanned",
        "limit_reason": "none",
        "scan_duration_milliseconds": max(0, round((monotonic() - started) * 1000)),
        "bucket_count": 0,
        "allocated_bytes": 0,
        "logical_bytes": 0,
        "regular_file_count": 0,
        "buckets": [],
    }


def collect_snapshot(
    catalog: Sequence[RootSpec] = ROOT_CATALOG,
    observed_at_utc: str | None = None,
    monotonic: Monotonic = time.monotonic,
) -> tuple[dict[str, Any], int]:
    """Collect filesystem and fixed-root metadata and derive completeness."""

    filesystem = filesystem_observation()
    roots: list[dict[str, Any]] = []
    largest_files: list[dict[str, Any]] = []
    for spec in catalog:
        record, root_largest = scan_root(spec, monotonic=monotonic)
        roots.append(record)
        for candidate in root_largest:
            _offer_largest(largest_files, candidate)

    root_complete_statuses = {"not_found", "not_directory", "ok"}
    collection_complete = filesystem.get("query_status") == "ok" and all(
        root["query_status"] in root_complete_statuses
        and root["scan_status"] in {"complete", "not_scanned"}
        for root in roots
    )
    summary = {
        "root_count": len(roots),
        "complete_root_count": sum(root["scan_status"] == "complete" for root in roots),
        "missing_root_count": sum(root["query_status"] == "not_found" for root in roots),
        "partial_root_count": sum(root["scan_status"] == "partial" for root in roots),
        "limited_root_count": sum(root["scan_status"] == "limited" for root in roots),
        "allocated_bytes": sum(root["allocated_bytes"] for root in roots),
        "logical_bytes": sum(root["logical_bytes"] for root in roots),
        "regular_file_count": sum(root["regular_file_count"] for root in roots),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pack": PACK_NAME,
        "observed_at_utc": observed_at_utc or utc_now(),
        "collection_status": "complete" if collection_complete else "partial",
        "catalog_sha256": catalog_sha256(catalog),
        "growth_computed": False,
        "growth_method": "compare_two_complete_envelopes_with_matching_catalog_sha256",
        "contract": {
            "fixed_root_count": len(catalog),
            "scan_timeout_seconds_per_root": SCAN_TIMEOUT_SECONDS,
            "max_entries_per_root": MAX_ENTRIES_PER_ROOT,
            "max_depth": MAX_DEPTH,
            "max_buckets_per_root": MAX_BUCKETS_PER_ROOT,
            "max_largest_files": MAX_LARGEST_FILES,
            "max_output_bytes": MAX_OUTPUT_BYTES,
            "file_content_read": False,
            "symlinks_followed": False,
            "cross_filesystems": False,
            "local_baseline_written": False,
            "raw_errors_emitted": False,
        },
        "filesystem": filesystem,
        "summary": summary,
        "roots": roots,
        "largest_files": largest_files,
    }
    return payload, 0 if collection_complete else 69


def render_snapshot(payload: dict[str, Any]) -> str:
    """Render deterministic JSON and fail closed above the output ceiling."""

    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if len(rendered.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError("disk growth snapshot exceeds output limit")
    return rendered


def main(argv: Sequence[str] | None = None) -> int:
    """Reject caller input, emit one snapshot and return collection status."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("DISK_GROWTH_REJECTED: arguments are not accepted", file=sys.stderr)
        return 64
    payload, exit_code = collect_snapshot()
    try:
        sys.stdout.write(render_snapshot(payload))
    except ValueError:
        print("DISK_GROWTH_OUTPUT_LIMIT_EXCEEDED", file=sys.stderr)
        return 70
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
