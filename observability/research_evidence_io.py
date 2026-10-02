"""Bounded, strict JSON reads shared by offline Research adapter and API reader."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

MAX_EVIDENCE_BYTES = 4 * 1024 * 1024


class EvidenceReadError(ValueError):
    """Evidence fails the bounded regular-file/JSON contract."""


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise EvidenceReadError(reason)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _check(key not in result, "Duplicate JSON member")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise EvidenceReadError("Non-finite JSON constant")


def read_evidence(path: Path, *, limit: int = MAX_EVIDENCE_BYTES) -> tuple[dict, str]:
    """Bounded regular-file read; refuse links and nonstandard JSON."""
    path = Path(path).absolute()
    _check(
        not any(p.is_symlink() for p in (path, *path.parents)),
        "Symlink evidence refused",
    )
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        _check(stat.S_ISREG(info.st_mode), "Evidence is not a regular file")
        _check(info.st_size <= limit, "Evidence exceeds byte limit")
        raw = handle.read(limit + 1)
    _check(len(raw) <= limit, "Evidence exceeds byte limit")
    doc = json.loads(
        raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant
    )
    _check(isinstance(doc, dict), "Evidence must be a JSON object")
    return doc, hashlib.sha256(raw).hexdigest()
