"""Strict bounded passive reads shared by Events producer and GET reader."""

from __future__ import annotations

import json
import math
import os
import stat

from observability.event_center_contract import MAX_BYTES, MAX_RECORDS, TAIL_WINDOW_BYTES


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


def _last_records(raw):
    """Keep the last MAX_RECORDS complete lines; raw is returned unchanged if it fits."""
    if not raw.endswith(b"\n"):
        return raw  # the parser rejects an unterminated record explicitly
    lines = raw.splitlines(keepends=True)
    return raw if len(lines) <= MAX_RECORDS else b"".join(lines[-MAX_RECORDS:])


def read_jsonl_window(path):
    """Bounded read of an append-only JSONL source -> (raw, source_bytes, coverage).

    "FULL": the whole file (<= MAX_BYTES and <= MAX_RECORDS lines), as read_bytes.
    "TAIL_WINDOW": the file is larger than MAX_BYTES (only the last TAIL_WINDOW_BYTES,
    cut at the first line start inside the window) or holds more than MAX_RECORDS
    lines (only the last MAX_RECORDS). The caller must publish that coverage; records
    before the window stay unknown, never counted or guessed. A concurrent change
    (append, rotation) is rejected as SOURCE_CHANGED, as for a full read.
    """
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW), "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("INVALID_PATH")
        size = before.st_size
        windowed = size > MAX_BYTES
        if windowed:
            source.seek(size - TAIL_WINDOW_BYTES - 1)  # one byte before the window
            raw = source.read(TAIL_WINDOW_BYTES + 1)
        else:
            raw = source.read(MAX_BYTES + 1)
        after = os.fstat(source.fileno())
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("SOURCE_CHANGED")
    if len(raw) != (TAIL_WINDOW_BYTES + 1 if windowed else size):
        raise ValueError("SOURCE_CHANGED")
    if windowed:
        newline = raw.find(b"\n")  # first line boundary: raw[0] lies outside the window
        if newline < 0 or newline + 1 >= len(raw):
            raise ValueError("INVALID_RECORD")  # no complete line inside the window
        raw = raw[newline + 1:]
    trimmed = _last_records(raw)
    return trimmed, size, ("FULL" if len(trimmed) == size else "TAIL_WINDOW")
