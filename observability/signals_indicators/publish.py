"""Écriture atomique d'une publication (0644, fsync, os.replace)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def dumps(pub: dict) -> bytes:
    return (json.dumps(pub, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")


def write_atomic(path: Path, data: bytes, mode: int = 0o644) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        # mkstemp crée en 0600 : on fixe explicitement le mode publié.
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
