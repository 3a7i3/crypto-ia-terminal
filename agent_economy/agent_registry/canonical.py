"""Canonical serialization, strict text rules and the closed error-code set.

Contract: A1 section 3 (canonical algorithm, rejection rules) and AW-03
(publication serialization). Nothing here normalizes an invalid input: every
violation raises :class:`AgentRegistryError` with a closed ``code``.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

# Closed set of failure codes: AS-* / AE-* / AC-* of the certified A1 contract,
# AW-03 publication codes, plus one implementation-level code
# (CANONICALIZATION_FAILED) for values that cannot be serialized at all.
ERROR_CODES = frozenset(
    {
        # AS-*
        "SPEC_SCHEMA_VIOLATION",
        "SPEC_NUMERIC_AMBIGUITY",
        "SPEC_TEXT_NOT_CANONICAL",
        "SPEC_ARRAY_NOT_CANONICAL",
        "FORBIDDEN_AUTHORITY_REQUESTED",
        "RESERVED_CAPABILITY",
        "UNKNOWN_CAPABILITY",
        "CAPABILITY_ABOVE_CEILING",
        "CLASS_LEVEL_INADMISSIBLE",
        "AUTHORITY_POLICY_VIOLATION",
        "BINDING_NOT_UNBOUND",
        "INDEPENDENCE_POLICY_VIOLATION",
        "IDENTITY_MISMATCH",
        "SUPERSESSION_BREAK",
        "SCOPE_CAPABILITY_INCOHERENT",
        # AE-*
        "EVENT_SCHEMA_VIOLATION",
        "EVENT_NUMERIC_AMBIGUITY",
        "EVENT_ID_MISMATCH",
        "EVENT_HASH_MISMATCH",
        "ILLEGAL_TRANSITION",
        "REASON_CODE_MISMATCH",
        "EVIDENCE_INVALID",
        "SPEC_REFERENCE_INVALID",
        "SOURCE_ANCHOR_MISSING",
        "REVISION_CLASS_MISMATCH",
        "SPEC_ARTIFACT_HASH_MISMATCH",
        # AC-*
        "SEQUENCE_GAP_OR_DUPLICATE",
        "CHAIN_BREAK",
        "ORDINAL_GAP",
        "EVENT_ID_COLLISION",
        "EVENT_AFTER_TERMINAL",
        # AW-03
        "AGENT_SPEC_PROVENANCE_CONFLICT",
        "AGENT_SPEC_ID_COLLISION_OR_CORRUPTION",
        # implementation-level (no contract code exists for it)
        "CANONICALIZATION_FAILED",
        "PUBLICATION_IO_ERROR",
    }
)


class AgentRegistryError(ValueError):
    """A contract rule was violated. ``code`` is a member of ERROR_CODES."""

    def __init__(
        self,
        code: str,
        detail: str = "",
        *,
        classification: str | None = None,
        cause: str | None = None,
    ) -> None:
        if code not in ERROR_CODES:  # programming error, never a data error
            raise AssertionError(f"unknown agent registry error code: {code}")
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.classification = classification
        self.cause = cause


def _assert_strict_json(value: Any, *, path: str = "$") -> None:
    """Allow only dict[str, ...], list, str, int, bool and None."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise AgentRegistryError(
            "CANONICALIZATION_FAILED", f"float is not canonical at {path}"
        )
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_strict_json(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AgentRegistryError(
                    "CANONICALIZATION_FAILED", f"non-string key at {path}"
                )
            _assert_strict_json(item, path=f"{path}.{key}")
        return
    raise AgentRegistryError(
        "CANONICALIZATION_FAILED", f"unsupported type {type(value).__name__} at {path}"
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Certified canonical form (A1 section 3.1), UTF-8 encoded."""
    try:
        _assert_strict_json(value)
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except AgentRegistryError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise AgentRegistryError(
            "CANONICALIZATION_FAILED", f"canonical serialization failed: {exc}"
        ) from exc


def sha256_hex_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex(value: Any) -> str:
    """Lowercase SHA-256 of the canonical bytes of ``value``."""
    return sha256_hex_of_bytes(canonical_json_bytes(value))


def publication_json_bytes(value: Any) -> bytes:
    """AW-03 serialization: indent=2, sorted keys, trailing newline, UTF-8."""
    try:
        _assert_strict_json(value)
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except AgentRegistryError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise AgentRegistryError(
            "CANONICALIZATION_FAILED", f"publication serialization failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Strict text / numeric / timestamp helpers (rejection, never correction)
# ---------------------------------------------------------------------------

_UTC_TS = re.compile(
    r"([0-9]{4})-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])"
    r"T([01][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])(?:\.([0-9]{1,6}))?Z"
)


def parse_utc_timestamp(value: str) -> datetime | None:
    """Return an aware UTC datetime, or None if not a real ISO-8601 UTC time."""
    match = _UTC_TS.fullmatch(value)
    if match is None:
        return None
    year, month, day, hour, minute, second, fraction = match.groups()
    try:
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            int((fraction or "0").ljust(6, "0")),
            tzinfo=timezone.utc,
        )
    except ValueError:  # e.g. 2026-02-31
        return None


def text_violation(value: str, *, allow_newline: bool = False) -> str | None:
    """Describe why ``value`` is not canonical text, or None if it is."""
    if not unicodedata.is_normalized("NFC", value):
        return "text is not NFC"
    for char in value:
        category = unicodedata.category(char)
        if category == "Cs":
            return "surrogate code point"
        if category == "Cc" and not (allow_newline and char == "\n"):
            return f"forbidden control character U+{ord(char):04X}"
    if value != value.strip():
        return "leading or trailing whitespace"
    return None


def is_pure_int(value: Any) -> bool:
    """True only for a real int (``bool`` and floats are ambiguous)."""
    return isinstance(value, int) and not isinstance(value, bool)


def find_float(value: Any, *, path: str = "$") -> str | None:
    """Path of the first float found anywhere in ``value`` (1.0 included)."""
    if isinstance(value, float):
        return path
    if isinstance(value, list):
        for index, item in enumerate(value):
            found = find_float(item, path=f"{path}[{index}]")
            if found:
                return found
    elif isinstance(value, dict):
        for key, item in value.items():
            found = find_float(item, path=f"{path}.{key}")
            if found:
                return found
    return None


def iter_strings(value: Any, *, path: str = "$"):
    """Yield (path, str) for every string value and every string key."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_strings(item, path=f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                yield f"{path}.<key:{key!r}>", key
            yield from iter_strings(item, path=f"{path}.{key}")


def compile_schema_pattern(schema_pattern: str) -> re.Pattern[str]:
    """Compile a JSON-Schema ``^...$`` pattern for ``fullmatch`` use.

    The anchors are stripped because Python's ``$`` also matches before a
    trailing newline; ``fullmatch`` has no such leniency.
    """
    if not (schema_pattern.startswith("^") and schema_pattern.endswith("$")):
        raise AssertionError("schema pattern must be anchored")
    return re.compile(schema_pattern[1:-1])
