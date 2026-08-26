"""Logs API — no arbitrary path, no secret egress, bounded output."""

from __future__ import annotations

import pytest

from visualization.api.logs_api import (
    ALLOWED_LOGS,
    MAX_LINES,
    load_log_tail,
    redact,
)


@pytest.fixture
def logs_dir(tmp_path):
    def _write(lines: list[str], name: str = "advisor_loop.log"):
        (tmp_path / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return tmp_path

    return _write


# ── Redaction ─────────────────────────────────────────────────────────────────


def test_redacts_telegram_bot_token():
    """The shape that actually reaches the logs: a token inside a URL path."""
    secret = "AAEwv7Xq2mKpLsTn8bQzRcYd3FgHjKlMnOp"
    line = (
        "2026-08-06 [INFO] calling "
        f"https://api.telegram.org/bot123456789:{secret}/sendMessage"
    )
    clean, was_redacted = redact(line)

    assert was_redacted is True
    assert secret not in clean
    assert "123456789" not in clean  # the bot id goes with it
    assert "<redacted:tg_token>" in clean


@pytest.mark.parametrize(
    "line,secret",
    [
        ("[INFO] api_key=sk-abcdef123456789", "sk-abcdef123456789"),
        ("[INFO] SECRET: hunter2hunter2", "hunter2hunter2"),
        ('[INFO] password="p@ssw0rd!"', "p@ssw0rd!"),
        ("[INFO] Authorization: Bearer eyJhbGciOiJIUzI1", "eyJhbGciOiJIUzI1"),
        ("[INFO] private_key = MIIEvQIBADANB", "MIIEvQIBADANB"),
    ],
)
def test_redacts_credential_shapes(line, secret):
    clean, was_redacted = redact(line)

    assert was_redacted is True
    assert secret not in clean


def test_keeps_useful_hashes_and_ids():
    """Conservative on purpose: SHA digests and packet ids are the payload."""
    line = "[INFO] deploy sha256=a3f5c1d9 packet_id=7bd21a04 symbol=BTC/USDT"
    clean, was_redacted = redact(line)

    assert was_redacted is False
    assert clean == line


def test_redaction_counted_in_snapshot(logs_dir):
    directory = logs_dir(
        [
            "2026-08-06 10:00:00 [INFO] token=supersecretvalue",
            "2026-08-06 10:00:01 [INFO] normal line",
        ]
    )
    snap = load_log_tail(logs_dir=directory)

    assert snap.n_redacted == 1
    assert all("supersecretvalue" not in line.raw for line in snap.lines)


# ── Path safety ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "evil",
    ["../../.env", "/etc/passwd", "..%2F.env", "advisor_loop.log", ".env"],
)
def test_unknown_key_never_opens_a_path(evil, logs_dir):
    """Only short keys from ALLOWED_LOGS resolve — a path is never honored."""
    directory = logs_dir(["[INFO] hello"])
    snap = load_log_tail(log_key=evil, logs_dir=directory)

    assert snap.exists is False
    assert snap.lines == []
    assert "unknown log" in (snap.error or "")


def test_allowed_keys_are_bare_filenames():
    """No key may encode traversal, even if a future edit adds one carelessly."""
    for key, filename in ALLOWED_LOGS.items():
        assert "/" not in filename and "\\" not in filename
        assert ".." not in filename
        assert key == key.lower()


def test_missing_file_reports_error_without_raising(tmp_path):
    snap = load_log_tail(logs_dir=tmp_path)

    assert snap.exists is False
    assert snap.error == "log file not found"


# ── Filtering and bounds ──────────────────────────────────────────────────────


def test_level_filter_warning_includes_errors(logs_dir):
    directory = logs_dir(
        [
            "2026-08-06 [INFO] routine",
            "2026-08-06 [WARNING] watch out",
            "2026-08-06 [ERROR] broke",
        ]
    )
    snap = load_log_tail(logs_dir=directory, level_filter="WARNING")

    levels = {line.level for line in snap.lines}
    assert levels == {"WARNING", "ERROR"}
    assert snap.level_filter == "WARNING"


def test_error_filter_selects_only_errors(logs_dir):
    directory = logs_dir(
        [
            "2026-08-06 [INFO] routine",
            "2026-08-06 [WARNING] watch out",
            "2026-08-06 [ERROR] broke",
        ]
    )
    snap = load_log_tail(logs_dir=directory, level_filter="ERROR")

    assert [line.level for line in snap.lines] == ["ERROR"]


def test_returns_newest_lines_in_chronological_order(logs_dir):
    directory = logs_dir([f"2026-08-06 [INFO] line {i}" for i in range(10)])
    snap = load_log_tail(logs_dir=directory, n_lines=3)

    assert [line.raw.split()[-1] for line in snap.lines] == ["7", "8", "9"]


def test_n_lines_is_clamped(logs_dir):
    directory = logs_dir([f"[INFO] line {i}" for i in range(MAX_LINES + 50)])
    snap = load_log_tail(logs_dir=directory, n_lines=10_000)

    assert snap.n_returned <= MAX_LINES


def test_invalid_level_falls_back_to_all(logs_dir):
    directory = logs_dir(["[INFO] a", "[ERROR] b"])
    snap = load_log_tail(logs_dir=directory, level_filter="NONSENSE")

    assert snap.level_filter == "ALL"
    assert snap.n_returned == 2


def test_traceback_lines_classified_as_error(logs_dir):
    directory = logs_dir(["Traceback (most recent call last):"])
    snap = load_log_tail(logs_dir=directory, level_filter="ERROR")

    assert snap.n_returned == 1
