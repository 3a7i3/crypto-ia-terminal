"""Bounded, race-checked read of ONE explicitly configured regular file.

Same rules as the existing GET-only readers of this package (Market Flux,
Scanner universe, BBO history): no symlink anywhere on the
path, regular file only, size bounded before and after the read, the file
must not change while it is read. Returns the raw bytes and the file's
modification instant; never parses, never writes, never follows a link.

Introduced by S4-b for the Radar projection reader. The older readers keep
their own copy of this logic and are deliberately not modified here
(CAT-DATA-01 inventory, item "lecture bornée dupliquée").
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BoundedRead:
    raw: bytes | None = None
    mtime_ms: int | None = None
    error: str | None = None  # MISSING, INVALID_PATH, UNREADABLE, TOO_LARGE, CHANGED_DURING_READ


def read_regular_file(path: Path, max_bytes: int) -> BoundedRead:
    path = Path(path)
    try:
        if any(p.is_symlink() for p in (path, *path.parents)):
            return BoundedRead(error="INVALID_PATH")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return BoundedRead(error="MISSING")
    except OSError:
        return BoundedRead(error="UNREADABLE")
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            os.close(fd)
            return BoundedRead(error="INVALID_PATH")
        if before.st_size > max_bytes:
            os.close(fd)
            return BoundedRead(error="TOO_LARGE")
        with os.fdopen(fd, "rb") as stream:
            raw = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
    except OSError:
        return BoundedRead(error="UNREADABLE")
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, k) != getattr(after, k) for k in fields):
        return BoundedRead(error="CHANGED_DURING_READ")
    if len(raw) > max_bytes:
        return BoundedRead(error="TOO_LARGE")
    return BoundedRead(raw=raw, mtime_ms=before.st_mtime_ns // 1_000_000)
