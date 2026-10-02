"""Bounded non-symlink JSON transport for U3b; no source authority imports."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from observability.market_microstructure_contract import MAX_BYTES


def read_document(path: Path, *, limit=MAX_BYTES):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("INVALID_PATH")
        raw = source.read(limit + 1)
    if len(raw) > limit:
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
        raise ValueError("INVALID_DOCUMENT")
    return doc, raw
