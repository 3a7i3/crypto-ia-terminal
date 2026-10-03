"""Strict bounded passive reads shared by Events producer and GET reader."""

from __future__ import annotations

import json
import math
import os
import stat

from observability.event_center_contract import MAX_BYTES


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_KEY")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("NONFINITE_JSON")

    def floating(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("NONFINITE_JSON")
        return result

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)


def read_bytes(path):
    """Bounded regular non-symlink read, rejecting a concurrent source change."""
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("INVALID_PATH")
        raw = source.read(MAX_BYTES + 1)
        after = os.fstat(source.fileno())
    if len(raw) > MAX_BYTES:
        raise OverflowError("OUTPUT_LIMIT")
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(raw) != after.st_size:
        raise ValueError("SOURCE_CHANGED")
    return raw
