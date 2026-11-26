"""R1-B — safe resolution of batch references under one evidence root (CLI only).

The pure core never reads a file: the CLI resolves every reference here and hands
the bytes to ``batch.verify_batch``. Rules (contract § 5, operator decision D1):

- one root, an existing real directory (not a symbolic link), whose identity
  (device, inode) is recorded when it is resolved and checked at every read;
- a reference is a relative POSIX path (``batch.valid_ref``): no ``.``, ``..``,
  absolute path, empty component, control character or backslash;
- the reference is walked with directory descriptors: each component is opened
  relative to the descriptor of its parent with ``O_NOFOLLOW`` (and
  ``O_DIRECTORY`` for directories), so a parent swapped for a symbolic link
  during the read can never lead outside the root. Each opened component must be
  the same inode as the one checked with ``lstat``; the final file must be a
  regular file that fits its ceiling;
- each file is read once; its fingerprint is checked by the caller.

Path-based checking (``lstat`` on joined paths, then ``open``) was refused by the
R1-B security review: a parent directory swapped between the check and the open
let the reader return a file from outside the root.
"""
from __future__ import annotations

import errno
import os
import stat

from .batch import valid_ref
from .fixture import RadarRefusal

_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_DIR_FLAGS = os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | _O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | _O_CLOEXEC
_ROOTS: dict = {}   # real root path -> (st_dev, st_ino) recorded by evidence_root
# Absolute path of the directory being walked, read by the offline guard
# (terminal._hook) to place the relative names opened with dir_fd. It never
# decides what is read: the descriptors do.
WALK: list = []


_SUPPORTED = bool(_O_NOFOLLOW and _O_DIRECTORY) and os.open in os.supports_dir_fd \
    and os.stat in os.supports_dir_fd and os.stat in os.supports_follow_symlinks


def supported() -> bool:
    """Descriptor-relative, no-follow opening is available (Linux, macOS, BSD)."""
    return _SUPPORTED


def evidence_root(path) -> str:
    """Real path of the evidence root, refused when it is a link or not a directory."""
    p = os.fspath(path)
    try:
        st = os.lstat(p)
    except OSError:
        raise RadarRefusal("EVIDENCE_ROOT_MISSING") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise RadarRefusal("EVIDENCE_ROOT_NOT_A_DIRECTORY")
    if not supported():
        raise RadarRefusal("REF_PLATFORM_UNSUPPORTED")
    real = os.path.realpath(p)
    _ROOTS[real] = (st.st_dev, st.st_ino)
    return real


def _open_checked(name: str, parent_fd: int, flags: int, ref: str, last: bool):
    """Open ``name`` relative to ``parent_fd`` after an ``lstat``; same inode or refusal."""
    try:
        st = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        raise RadarRefusal("REF_MISSING:" + ref) from None
    if stat.S_ISLNK(st.st_mode):
        raise RadarRefusal("REF_SYMLINK:" + ref)
    if not last and not stat.S_ISDIR(st.st_mode):
        raise RadarRefusal("REF_MISSING:" + ref)
    if last and not stat.S_ISREG(st.st_mode):
        raise RadarRefusal("REF_NOT_REGULAR:" + ref)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EMLINK):
            raise RadarRefusal("REF_SYMLINK:" + ref) from None
        raise RadarRefusal("REF_CHANGED_DURING_READ:" + ref) from None
    fst = os.fstat(fd)
    if (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino) \
            or (stat.S_ISREG(fst.st_mode) if last else stat.S_ISDIR(fst.st_mode)) is False:
        os.close(fd)
        raise RadarRefusal("REF_CHANGED_DURING_READ:" + ref)
    return fd, fst


def _under_root(fd: int, root: str) -> bool:
    """Defence in depth (Linux): the opened file's real path is under the root."""
    try:
        real = os.readlink(f"/proc/self/fd/{fd}")
    except OSError:
        return True   # no /proc: the descriptor walk is the guarantee
    return real.startswith(root + os.sep)


def read_ref(root: str, ref: str, max_bytes: int) -> bytes:
    """Bytes of one reference under ``root`` (already returned by ``evidence_root``)."""
    if not valid_ref(ref):
        raise RadarRefusal("REF_SYNTAX:" + repr(ref)[:80])
    if not supported():
        raise RadarRefusal("REF_PLATFORM_UNSUPPORTED")
    parts = ref.split("/")
    try:
        root_fd = os.open(root, _DIR_FLAGS)
    except OSError:
        raise RadarRefusal("EVIDENCE_ROOT_NOT_A_DIRECTORY") from None
    fds = [root_fd]
    WALK.append(root)
    try:
        rst = os.fstat(root_fd)
        if root in _ROOTS and _ROOTS[root] != (rst.st_dev, rst.st_ino):
            raise RadarRefusal("REF_CHANGED_DURING_READ:" + ref)
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            fd, fst = _open_checked(part, fds[-1], _FILE_FLAGS if last else _DIR_FLAGS, ref, last)
            fds.append(fd)
            if not last:
                WALK[-1] = os.path.join(WALK[-1], part)
        if not _under_root(fd, root):
            raise RadarRefusal("REF_OUTSIDE_ROOT:" + ref)
        if fst.st_size > max_bytes:
            raise RadarRefusal("REF_TOO_LARGE:" + ref)
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise RadarRefusal("REF_TOO_LARGE:" + ref)
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        WALK.pop()
        for f in reversed(fds):
            os.close(f)


def read_all(root: str, wanted: dict, total: int | None = None) -> dict:
    """{ref: ceiling} -> {ref: bytes}. A missing reference is left out (the verifier reports it).

    With ``total``, the bytes read together may not exceed it: each reference is
    read with the smaller of its own ceiling and what remains, and going over the
    total refuses the whole batch (``REFS_BYTES_BOUND``) before anything is parsed.
    """
    out, used = {}, 0
    for ref in sorted(wanted):
        ceiling = wanted[ref]
        if total is not None:
            remaining = total - used
            if remaining < ceiling:
                ceiling = remaining
        try:
            out[ref] = read_ref(root, ref, max(ceiling, 0))
        except RadarRefusal as exc:
            if exc.code == "REF_TOO_LARGE" and total is not None and ceiling < wanted[ref]:
                raise RadarRefusal("REFS_BYTES_BOUND:" + ref) from None
            if exc.code != "REF_MISSING":
                raise
            continue
        used += len(out[ref])
    return out
