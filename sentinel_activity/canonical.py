"""Bounded strict JSON, compatible with the A1 canonical byte convention.

Validation precedes hashing; invalid text and numeric ambiguity are rejected,
not normalized. Errors deliberately contain no submitted values.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from typing import Any

from sentinel_activity.redaction_v1 import contains_secret

ERROR_CODES = frozenset({
    "INVALID_JSON", "DUPLICATE_KEY", "SCHEMA_VIOLATION", "NUMERIC_AMBIGUITY",
    "TEXT_NOT_CANONICAL", "SECRET_REJECTED", "BUDGET_EXCEEDED", "INVALID_TIME",
    "UNKNOWN_VERSION", "PROVENANCE_DENIED", "ACTOR_DENIED", "POLICY_MISMATCH",
    "EVENT_ID_COLLISION", "CAUSATION_INVALID", "ILLEGAL_TRANSITION",
    "REVISION_CONFLICT", "ALREADY_ASSIGNED", "SELF_REVIEW_DENIED",
    "EVIDENCE_INVALID", "CORRUPTED", "UNAVAILABLE", "BUSY", "PATH_DENIED",
    "ALREADY_EXISTS", "CURSOR_INVALID", "CLOCK_REGRESSION",
})


_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cs", "Cf"})


class LedgerError(ValueError):
    """Closed, non-sensitive failure code (never echo the rejected input)."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise AssertionError("unknown ledger error code")
        self.code = code
        super().__init__(code)


def require(condition: bool, code: str = "SCHEMA_VIOLATION") -> None:
    if not condition:
        raise LedgerError(code)


def pure_int(value: Any, minimum: int = 0, maximum: int = 2**63 - 1) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _text_failure(value: str) -> str | None:
    """First failing text rule, in the original order; a pure function."""
    if not unicodedata.is_normalized("NFC", value):
        return "TEXT_NOT_CANONICAL"
    # str.isprintable() is False for every Cc/Cs/Cf code point, so the
    # per-character scan only runs on text that may contain one.
    if not value.isprintable() and any(unicodedata.category(c) in _FORBIDDEN_CATEGORIES for c in value):
        return "TEXT_NOT_CANONICAL"
    if contains_secret(value):
        return "SECRET_REJECTED"
    return None


# Memo of accepted short strings under immutable rules (frozen v1 profile,
# fixed Unicode tables of this interpreter). It holds no journal state, so it
# cannot carry a verification result from one read to another. Rejected text
# (possibly a secret) is never retained. Bounded: <=256 chars, <=8192 entries.
_ACCEPTED_TEXT: set[str] = set()


def _short_text_failure(value: str) -> str | None:
    if value in _ACCEPTED_TEXT:
        return None
    code = _text_failure(value)
    if code is None:
        if len(_ACCEPTED_TEXT) >= 8192:
            _ACCEPTED_TEXT.clear()
        _ACCEPTED_TEXT.add(value)
    return code


def _walk(value: Any, depth: int = 0) -> None:
    require(depth <= 8, "BUDGET_EXCEEDED")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        require(-(2**63) < value < 2**63, "NUMERIC_AMBIGUITY")
        return
    if type(value) is str:
        require(len(value) <= 16_384, "BUDGET_EXCEEDED")
        code = _short_text_failure(value) if len(value) <= 256 else _text_failure(value)
        if code is not None:
            raise LedgerError(code)
        return
    if type(value) is list:
        require(len(value) <= 100, "BUDGET_EXCEEDED")
        for item in value:
            _walk(item, depth + 1)
        return
    if type(value) is dict:
        require(len(value) <= 64, "BUDGET_EXCEEDED")
        for key, item in value.items():
            require(type(key) is str)
            _walk(key, depth + 1)
            _walk(item, depth + 1)
        return
    raise LedgerError("NUMERIC_AMBIGUITY" if isinstance(value, float) else "SCHEMA_VIOLATION")


def canonical_bytes(value: Any, limit: int = 32_768) -> bytes:
    _walk(value)
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise LedgerError("INVALID_JSON") from exc
    require(len(raw) <= limit, "BUDGET_EXCEEDED")
    return raw


def strict_loads(raw: bytes | str, limit: int = 32_768) -> Any:
    require(type(raw) in {bytes, str}, "INVALID_JSON")
    try:
        data = raw.encode("utf-8") if type(raw) is str else raw
        require(len(data) <= limit, "BUDGET_EXCEEDED")

        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, "DUPLICATE_KEY")
                result[key] = value
            return result

        def constant(_):
            raise LedgerError("NUMERIC_AMBIGUITY")

        result = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        canonical_bytes(result, limit)
        return result
    except LedgerError:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise LedgerError("INVALID_JSON") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_utc(value: Any) -> datetime:
    import re

    require(type(value) is str and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", value
    ) is not None, "INVALID_TIME")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LedgerError("INVALID_TIME") from exc


def format_utc(value: datetime) -> str:
    require(isinstance(value, datetime) and value.tzinfo is not None, "INVALID_TIME")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
