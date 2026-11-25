"""Bounded, race-checked read of ONE explicitly configured regular file.

Same rules as the existing GET-only readers of this package (Market Flux,
Scanner universe, BBO history): no symlink anywhere on the path, regular file
only, size bounded before and after the read, the file must not change while
it is read. Returns the raw bytes and the file's modification instant; never
parses, never writes, never follows a link.

Path resolution (S4-B-RV1). A check-then-open sequence (``is_symlink`` on
each parent, then ``open(path)``) leaves a window in which a parent directory
can be swapped for a symlink between the check and the open. This reader
therefore never resolves the path by name in one call: it walks it one
component at a time from a directory descriptor, opening every parent with
``O_DIRECTORY | O_NOFOLLOW`` and the last component with ``O_NOFOLLOW``, each
relative to the descriptor of the directory opened just before. A component
that is a symlink at the instant it is opened is refused by the kernel
(``ELOOP``/``ENOTDIR``), so a substitution at any moment either is refused or
has no effect on the descriptors already held. ``..`` components are refused,
``.`` and empty components are ignored. The starting point is ``/`` for an
absolute path and the working directory for a relative one (the working
directory itself is trusted, as for any process).

Introduced by S4-b for the Radar projection reader. The older readers keep
their own copy of this logic and are deliberately not modified here
(CAT-DATA-01 inventory, item "lecture bornée dupliquée").
"""

from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
_LINK_ERRNOS = {errno.ELOOP, errno.ENOTDIR, getattr(errno, "EMLINK", errno.ELOOP)}


@dataclass(frozen=True)
class BoundedRead:
    raw: bytes | None = None
    mtime_ms: int | None = None
    error: str | None = None  # MISSING, INVALID_PATH, UNREADABLE, TOO_LARGE, CHANGED_DURING_READ


class _InvalidPath(Exception):
    pass


def _open_without_following(path: Path) -> int:
    """Open ``path`` read-only, one component at a time, never following a link."""
    parts = [p for p in path.parts if p not in ("", ".")]
    if path.is_absolute():
        start, parts = "/", parts[1:]
    else:
        start = "."
    if not parts or any(p == ".." for p in parts):
        raise _InvalidPath
    dirfd = os.open(start, _DIR_FLAGS)
    try:
        for name in parts[:-1]:
            try:
                nxt = os.open(name, _DIR_FLAGS, dir_fd=dirfd)
            except OSError as exc:
                if exc.errno in _LINK_ERRNOS:
                    raise _InvalidPath from None
                raise
            os.close(dirfd)
            dirfd = nxt
        try:
            return os.open(parts[-1], _FILE_FLAGS, dir_fd=dirfd)
        except OSError as exc:
            if exc.errno in _LINK_ERRNOS:
                raise _InvalidPath from None
            raise
    finally:
        os.close(dirfd)


def read_regular_file(path: Path, max_bytes: int) -> BoundedRead:
    path = Path(path)
    try:
        fd = _open_without_following(path)
    except _InvalidPath:
        return BoundedRead(error="INVALID_PATH")
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
