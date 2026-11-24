"""R1-B — safe resolution of batch references under one evidence root (CLI only).

The pure core never reads a file: the CLI resolves every reference here and hands
the bytes to ``batch.verify_batch``. Rules (contract § 5, operator decision D1):

- one root, an existing real directory (not a symbolic link);
- a reference is a relative POSIX path (``batch.valid_ref``): no ``.``, ``..``,
  absolute path, empty component, control character or backslash;
- every component is checked with ``lstat`` (no symbolic link, directories then
  one regular file), the final file is opened with ``O_NOFOLLOW`` and must be the
  same inode as the one checked, stay under the root, and fit its ceiling;
- each file is read once; its fingerprint is checked by the caller.
"""
from __future__ import annotations

import os
import stat

from .batch import valid_ref
from .fixture import RadarRefusal


def evidence_root(path) -> str:
    """Real path of the evidence root, refused when it is a link or not a directory."""
    p = os.fspath(path)
    try:
        st = os.lstat(p)
    except OSError:
        raise RadarRefusal("EVIDENCE_ROOT_MISSING") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise RadarRefusal("EVIDENCE_ROOT_NOT_A_DIRECTORY")
    return os.path.realpath(p)


def read_ref(root: str, ref: str, max_bytes: int) -> bytes:
    """Bytes of one reference under ``root`` (already returned by ``evidence_root``)."""
    if not valid_ref(ref):
        raise RadarRefusal("REF_SYNTAX:" + repr(ref)[:80])
    parts = ref.split("/")
    current = root
    for i, part in enumerate(parts):
        current = os.path.join(current, part)
        try:
            st = os.lstat(current)
        except OSError:
            raise RadarRefusal("REF_MISSING:" + ref) from None
        if stat.S_ISLNK(st.st_mode):
            raise RadarRefusal("REF_SYMLINK:" + ref)
        last = i == len(parts) - 1
        if not last and not stat.S_ISDIR(st.st_mode):
            raise RadarRefusal("REF_MISSING:" + ref)
        if last and not stat.S_ISREG(st.st_mode):
            raise RadarRefusal("REF_NOT_REGULAR:" + ref)
    if os.path.realpath(current) != current or not current.startswith(root + os.sep):
        raise RadarRefusal("REF_OUTSIDE_ROOT:" + ref)
    if st.st_size > max_bytes:
        raise RadarRefusal("REF_TOO_LARGE:" + ref)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(current, flags)
    except OSError:
        raise RadarRefusal("REF_SYMLINK:" + ref) from None
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
            raise RadarRefusal("REF_CHANGED_DURING_READ:" + ref)
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
        os.close(fd)


def read_all(root: str, wanted: dict) -> dict:
    """{ref: ceiling} -> {ref: bytes}. A missing reference is left out (the verifier reports it)."""
    out = {}
    for ref in sorted(wanted):
        try:
            out[ref] = read_ref(root, ref, wanted[ref])
        except RadarRefusal as exc:
            if exc.code != "REF_MISSING":
                raise
    return out
