"""Logs API — bounded, redacted tails of runtime log files (observability only).

Two properties matter here and are enforced in this module, not in its callers:

1. **No arbitrary path.** Clients select a log by *short key* against
   `ALLOWED_LOGS`; a path never crosses the API boundary. A chat command that
   forwarded user text into `open()` would be an arbitrary-file-read primitive.
2. **No secret egress.** Tails are forwarded to chat clients, so a token that
   was accidentally logged would leave the host. `redact()` strips the known
   shapes before the lines are returned.

Strictly passive (ADR-0007): reads log files, never writes, never decides.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from visualization.api.models import LogLine, LogTailSnapshot

_ROOT = Path(__file__).resolve().parents[2]
_LOGS_DIR = _ROOT / "logs"

# Short key → filename. The only log files this API will ever open.
ALLOWED_LOGS: dict[str, str] = {
    "advisor": "advisor_loop.log",
    "stdout": "advisor_loop_stdout.log",
    "stderr": "advisor_loop_stderr.log",
    "watchdog": "watchdog_vps.log",
    "deploy": "deploy_vps.log",
    "verifier": "data_verifier.log",
}

DEFAULT_LOG = "advisor"
DEFAULT_LINES = 30
MAX_LINES = 100

# Only the file tail is read — advisor_loop.log grows unbounded on the VPS.
_TAIL_BYTES = 256 * 1024

_LEVELS = ("ERROR", "WARNING", "INFO")

# ── Redaction ─────────────────────────────────────────────────────────────────

_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Telegram bot token: <bot_id>:<secret>. No leading \b — the shape that
    # actually reaches the logs is a URL path, `.../bot123456789:AAE...`, where
    # the digits are preceded by a letter and a word boundary never matches.
    (re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}"), "<redacted:tg_token>"),
    # key=value / key: value for anything named like a credential
    (
        re.compile(
            r"(?i)\b(token|secret|password|passwd|pwd|api[_-]?key|apikey"
            r"|access[_-]?key|secret[_-]?key|private[_-]?key|auth)\b"
            r"(\s*[:=]\s*[\"']?)([^\s\"',;}]+)"
        ),
        r"\1\2<redacted>",
    ),
    # Authorization: Bearer <...>
    (re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9._\-]{8,})"), r"\1 <redacted>"),
)


def redact(line: str) -> tuple[str, bool]:
    """Strip known secret shapes from a log line.

    Returns `(clean_line, was_redacted)`. Deliberately conservative: it does
    not blanket-redact long hex strings, because SHA256 deploy digests and
    packet ids are the useful content of these logs.
    """
    out = line
    for pattern, replacement in _REDACTIONS:
        out = pattern.sub(replacement, out)
    return out, out != line


# ── Level parsing ─────────────────────────────────────────────────────────────


def _level_of(line: str) -> str:
    """Extract the level from `%(asctime)s [%(levelname)s] ...` or bare text."""
    for level in _LEVELS:
        if f"[{level}]" in line:
            return level
    upper = line.upper()
    if "CRITICAL" in upper or "TRACEBACK" in upper:
        return "ERROR"
    for level in _LEVELS:
        if level in upper:
            return level
    return "OTHER"


def _passes(level: str, level_filter: str) -> bool:
    if level_filter == "ALL":
        return True
    if level_filter == "ERROR":
        return level == "ERROR"
    if level_filter == "WARNING":
        return level in ("ERROR", "WARNING")
    return level == level_filter


def _read_tail_lines(path: Path) -> list[str]:
    """Read at most `_TAIL_BYTES` from the end of the file, whole lines only."""
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > _TAIL_BYTES:
            fh.seek(size - _TAIL_BYTES)
            fh.readline()  # discard the partial first line
        raw = fh.read()
    return raw.decode("utf-8", errors="replace").splitlines()


# ── Loader ────────────────────────────────────────────────────────────────────


def load_log_tail(
    log_key: str = DEFAULT_LOG,
    n_lines: int = DEFAULT_LINES,
    level_filter: str = "ALL",
    logs_dir: Optional[Path] = None,
) -> LogTailSnapshot:
    """Return the last `n_lines` matching lines of an allowlisted log file.

    Unknown `log_key`, absent file, or unreadable file all yield a snapshot
    carrying `error` — never an exception, so a read-only client stays up.
    """
    ts = datetime.now(timezone.utc)
    level_filter = (level_filter or "ALL").upper()
    if level_filter not in ("ALL", *_LEVELS):
        level_filter = "ALL"

    n_lines = max(1, min(int(n_lines or DEFAULT_LINES), MAX_LINES))

    filename = ALLOWED_LOGS.get(log_key)
    if filename is None:
        return LogTailSnapshot(
            ts=ts,
            source_path="",
            exists=False,
            n_returned=0,
            n_scanned=0,
            level_filter=level_filter,
            error=(
                f"unknown log '{log_key}' — available: "
                f"{', '.join(sorted(ALLOWED_LOGS))}"
            ),
        )

    path = (logs_dir or _LOGS_DIR) / filename

    if not path.exists():
        return LogTailSnapshot(
            ts=ts,
            source_path=str(path),
            exists=False,
            n_returned=0,
            n_scanned=0,
            level_filter=level_filter,
            error="log file not found",
        )

    try:
        scanned = _read_tail_lines(path)
    except Exception as exc:
        return LogTailSnapshot(
            ts=ts,
            source_path=str(path),
            exists=True,
            n_returned=0,
            n_scanned=0,
            level_filter=level_filter,
            error=f"unreadable: {exc}",
        )

    selected: list[LogLine] = []
    n_redacted = 0
    # Walk backwards so the newest matching lines win, then restore order.
    for raw in reversed(scanned):
        if not raw.strip():
            continue
        level = _level_of(raw)
        if not _passes(level, level_filter):
            continue
        clean, was_redacted = redact(raw)
        if was_redacted:
            n_redacted += 1
        selected.append(LogLine(raw=clean, level=level))
        if len(selected) >= n_lines:
            break
    selected.reverse()

    return LogTailSnapshot(
        ts=ts,
        source_path=str(path),
        exists=True,
        n_returned=len(selected),
        n_scanned=len(scanned),
        level_filter=level_filter,
        lines=selected,
        n_redacted=n_redacted,
    )
