"""Immutable secret-pattern profile for legacy J01 storage/event contracts.

Do not change these patterns in place. New detection rules require a versioned
profile and an explicit admission/migration policy, never reclassification of
historical event bytes. This detector does not cover unknown secret formats.
"""

from __future__ import annotations

import re

PROFILE_VERSION = "j01-secret-patterns/1"
REDACTED = "[REDACTED]"

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)"
    ),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,255}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,255}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),  # jeton bot Telegram
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)\bauthorization\s*:\s*\S+(?:\s+\S+)?"),
    re.compile(
        r"(?i)\b([A-Z0-9_]*(?:api[_-]?key|secret|token|passw(?:or)?d|private[_-]?key|access[_-]?key)[A-Z0-9_]*)"
        r"\s*[:=]\s*(['\"]?)[^\s'\"]{4,}\2"
    ),
)


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pattern in _SECRET_PATTERNS:
        text, replacements = pattern.subn(REDACTED, text)
        count += replacements
    return text, count


def contains_secret(text: str) -> bool:
    """Same verdict as ``redact(text)[1] > 0``: no pattern matches the empty
    string, and the first matching pattern sees the unchanged input."""
    return any(pattern.search(text) is not None for pattern in _SECRET_PATTERNS)
