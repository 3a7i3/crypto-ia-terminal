"""Tests for the Vancouver-time display integration in @QuantCrypto_bot.

These tests verify that:
- The bot module imports and uses format_vancouver_time (not raw strftime+UTC).
- The conversion from UTC → Vancouver is correct for the display sites.

All timestamps are fixed — no test depends on the current wall clock.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.common.time_display import format_vancouver_time, to_vancouver


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ── Source-code static checks ─────────────────────────────────────────────────

BOT_SRC = Path(__file__).parent.parent.parent / "src/telegram/quant_observer/bot.py"
NOTIFIER_SRC = Path(__file__).parent.parent.parent / "src/telegram/notifier.py"


def test_bot_imports_format_vancouver_time() -> None:
    """bot.py must import format_vancouver_time from src.common.time_display."""
    source = BOT_SRC.read_text(encoding="utf-8")
    assert "from src.common.time_display import" in source
    assert "format_vancouver_time" in source


def test_bot_no_raw_utc_strftime_on_ts() -> None:
    """bot.py must NOT use h.ts.strftime(…) UTC pattern directly."""
    source = BOT_SRC.read_text(encoding="utf-8")
    assert "h.ts.strftime" not in source, (
        "h.ts.strftime() found in bot.py — the UTC datetime must be converted "
        "via format_vancouver_time() before displaying."
    )


def test_bot_header_no_hardcoded_utc_label() -> None:
    """bot.py must not have a hardcoded 'UTC' label next to the time display."""
    source = BOT_SRC.read_text(encoding="utf-8")
    # The old pattern was: h.ts.strftime('%H:%M')} UTC
    assert "strftime('%H:%M')} UTC" not in source
    assert 'strftime("%H:%M")} UTC' not in source


def test_notifier_imports_format_vancouver_time() -> None:
    """notifier.py must import format_vancouver_time from src.common.time_display."""
    source = NOTIFIER_SRC.read_text(encoding="utf-8")
    assert "from src.common.time_display import" in source
    assert "format_vancouver_time" in source


def test_notifier_no_raw_utc_strftime() -> None:
    """notifier.py must NOT use datetime.now(…).strftime(…) for the timestamp."""
    source = NOTIFIER_SRC.read_text(encoding="utf-8")
    assert '.strftime("%H:%M")' not in source
    assert ".strftime('%H:%M')" not in source


# ── Functional display tests ──────────────────────────────────────────────────

def test_summer_utc_displayed_as_pdt() -> None:
    """2026-08-30 22:00 UTC → format_vancouver_time → '15:00 PDT'."""
    utc_dt = _utc(2026, 8, 30, 22, 0)
    result = format_vancouver_time(utc_dt)
    assert "15:00" in result
    assert "PDT" in result
    assert "22:00" not in result


def test_summer_display_not_suffixed_utc() -> None:
    """The formatted Vancouver time must not carry a 'UTC' suffix."""
    utc_dt = _utc(2026, 8, 30, 22, 0)
    result = format_vancouver_time(utc_dt)
    assert "UTC" not in result


def test_winter_utc_displayed_as_pst() -> None:
    """2026-01-15 20:00 UTC → format_vancouver_time → '12:00 PST'."""
    utc_dt = _utc(2026, 1, 15, 20, 0)
    result = format_vancouver_time(utc_dt)
    assert "12:00" in result
    assert "PST" in result


def test_source_utc_ts_not_mutated() -> None:
    """format_vancouver_time must never mutate the original UTC datetime."""
    utc_dt = _utc(2026, 8, 30, 22, 0)
    _ = format_vancouver_time(utc_dt)
    assert utc_dt.tzinfo == timezone.utc
    assert utc_dt.hour == 22

