"""Helpers for MEO-04 tests (SYNTHETIC inputs unless a real-corpus fixture is requested)."""

import hashlib
import io
import os
import tarfile
from pathlib import Path

from observability.meo_memory import canon as c
from observability.meo_memory.reads import Reader
from observability.meo_memory.store import Store, init_root


def new_root(tmp_path, partition="SYNTHETIC", name="root", **kw):
    root = Path(tmp_path).resolve() / name
    init_root(root, partition, **kw)
    return root


def tree(root):
    """Path -> (sha256, mode) for every file under ``root`` (directories by name)."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for d in dirs:
            out[os.path.relpath(os.path.join(dirpath, d), root) + "/"] = None
        for f in files:
            p = os.path.join(dirpath, f)
            out[os.path.relpath(p, root)] = (hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                                            os.lstat(p).st_mode)
    return out


def reads(root):
    r = Reader(root)
    return {"now": r.now(), "events": r.events(include_excluded=True), "summary": r.summary()}


def canonical_reads(root):
    return c.canonical(reads(root))


def make_archive(capture_dir, path, *, extra=None, sums=True):
    """A flat .tar.gz of a capture directory with a SHA256SUMS seal (like the L3 export)."""
    members = {p.name: p.read_bytes() for p in sorted(Path(capture_dir).iterdir())}
    members.update(extra or {})
    if sums:
        members["SHA256SUMS"] = "".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n"
                                        for n, b in sorted(members.items()) if n != "SHA256SUMS").encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    Path(path).write_bytes(buf.getvalue())
    return Path(path)


def store(root, **kw):
    return Store(root, **kw)
