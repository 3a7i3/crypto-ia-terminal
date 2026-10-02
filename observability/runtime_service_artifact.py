"""Bounded strict JSON reads shared by producer and transport-only reader."""

from __future__ import annotations

import json
import os
from pathlib import Path

from observability.runtime_service_contract import MAX_BYTES


def read_document(path: Path) -> tuple[dict, bytes]:
    """Bounded non-symlink JSON read; duplicate keys and constants rejected."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    import stat

    with os.fdopen(os.open(path, flags), "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("INVALID_PATH")
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("OUTPUT_LIMIT")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_KEY")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("INVALID_CONSTANT")

    doc = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(doc, dict):
        raise TypeError("INVALID_DOCUMENT")
    return doc, raw
