"""Rédaction des secrets, chemins interdits et citation de contenu non fiable.

Tout texte provenant de GitHub (README, issues, PR, commentaires), de journaux
ou de snapshots est une **donnée**. Il est borné, débarrassé des caractères de
contrôle, expurgé des motifs de secrets, puis cité ; il ne devient jamais une
instruction pour Sentinel.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

REDACTED = "[REDACTED]"

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)"),
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

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")

#: Chemins jamais lus, jamais cités, jamais envoyés à un modèle.
_FORBIDDEN_NAME_RE = re.compile(
    r"(?i)(^|/)(\.env(\..*)?|.*\.pem|.*\.key|.*\.p12|.*\.pfx|id_(rsa|ecdsa|ed25519)(\.pub)?|"
    r"\.netrc|\.pgpass|\.npmrc|\.pypirc|credentials(\.json)?|secrets?(\.ya?ml|\.json|\.toml)?|"
    r"known_hosts|authorized_keys|.*token.*\.(txt|json))$"
)
_FORBIDDEN_DIR_RE = re.compile(r"(?i)(^|/)(\.git|\.ssh|\.gnupg|\.aws|secrets?|private)(/|$)")


@dataclass(frozen=True)
class Redacted:
    text: str
    redactions: int
    truncated: bool


def redact(text: str) -> tuple[str, int]:
    """Remplace les motifs de secrets ; retourne (texte, nombre de remplacements)."""
    count = 0
    for pattern in _SECRET_PATTERNS:
        text, n = pattern.subn(REDACTED, text)
        count += n
    return text, count


def sanitize_untrusted(text: object, limit: int = 600) -> Redacted:
    """Prépare un contenu externe pour citation : texte, borné, sans contrôle, expurgé."""
    raw = text if isinstance(text, str) else ""
    raw = _CONTROL_RE.sub(" ", raw)
    truncated = len(raw) > limit
    cleaned, n = redact(raw)
    return Redacted(cleaned[:limit], n, truncated)


def normalize_repo_path(path: str) -> str | None:
    """Chemin relatif POSIX normalisé, ou None si traversée/absolu/caractère suspect."""
    if not isinstance(path, str) or not path or len(path) > 400:
        return None
    if "\\" in path or "\x00" in path or path.startswith("/") or path.startswith("~"):
        return None
    norm = posixpath.normpath(path)
    if norm.startswith("..") or norm == "." or "/../" in f"/{norm}/":
        return None
    return norm


def is_forbidden_path(path: str) -> bool:
    """True si le chemin désigne un secret, une clé, un .env ou un répertoire privé."""
    norm = normalize_repo_path(path)
    if norm is None:
        return True
    return bool(_FORBIDDEN_NAME_RE.search(norm) or _FORBIDDEN_DIR_RE.search(norm))
