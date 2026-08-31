"""Unit tests for src/common/time_display.py.

All timestamps are fixed — no test depends on the current wall clock.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from src.common.time_display import (
    VANCOUVER_TZ,
    format_vancouver_time,
    to_vancouver,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ── Test: summer (PDT = UTC-7) ────────────────────────────────────────────────

def test_summer_utc_to_pdt() -> None:
    """2026-08-30 22:00 UTC → 2026-08-30 15:00 PDT."""
    utc_dt = _utc(2026, 8, 30, 22, 0)
    local = to_vancouver(utc_dt)
    assert local.year == 2026
    assert local.month == 8
    assert local.day == 30
    assert local.hour == 15
    assert local.minute == 0


# ── Test: winter (PST = UTC-8) ────────────────────────────────────────────────

def test_winter_utc_to_pst() -> None:
    """2026-01-15 20:00 UTC → 2026-01-15 12:00 PST (not PDT offset!)."""
    utc_dt = _utc(2026, 1, 15, 20, 0)
    local = to_vancouver(utc_dt)
    assert local.hour == 12
    assert local.minute == 0


def test_summer_and_winter_differ() -> None:
    """The UTC offset must differ between summer and winter — no fixed offset."""
    summer = to_vancouver(_utc(2026, 8, 30, 22, 0))
    winter = to_vancouver(_utc(2026, 1, 15, 22, 0))
    summer_offset = summer.utcoffset()
    winter_offset = winter.utcoffset()
    assert summer_offset != winter_offset, (
        "PDT and PST should produce different offsets; got the same — "
        "a fixed offset was probably used."
    )


# ── Test: DST boundary ────────────────────────────────────────────────────────

def test_dst_spring_forward() -> None:
    """On 2024-03-10 clocks spring forward at 02:00 AM PST (= 10:00 UTC).

    09:59 UTC  →  01:59 PST  (UTC-8, before transition)
    10:01 UTC  →  03:01 PDT  (UTC-7, after transition)
    """
    pre = _utc(2024, 3, 10, 9, 59)
    post = _utc(2024, 3, 10, 10, 1)
    pre_local = to_vancouver(pre)
    post_local = to_vancouver(post)
    assert pre_local.utcoffset() != post_local.utcoffset(), (
        "Expected UTC-8 before spring-forward and UTC-7 after, but got the same offset."
    )


def test_dst_fall_back() -> None:
    """On 2024-11-03 clocks fall back at 02:00 AM PDT (= 09:00 UTC).

    08:59 UTC  →  01:59 PDT  (UTC-7, before fall-back)
    09:01 UTC  →  01:01 PST  (UTC-8, after fall-back)
    """
    pdt_side = _utc(2024, 11, 3, 8, 59)
    pst_side = _utc(2024, 11, 3, 9, 1)
    pdt_local = to_vancouver(pdt_side)
    pst_local = to_vancouver(pst_side)
    assert pdt_local.utcoffset() != pst_local.utcoffset(), (
        "Expected UTC-7 before fall-back and UTC-8 after, but got the same offset."
    )


# ── Test: result is timezone-aware ────────────────────────────────────────────

def test_result_is_timezone_aware() -> None:
    result = to_vancouver(_utc(2026, 8, 30, 22, 0))
    assert result.tzinfo is not None
    assert result.utcoffset() is not None


# ── Test: naive datetime raises ValueError ────────────────────────────────────

def test_naive_datetime_raises() -> None:
    naive = datetime(2026, 8, 30, 22, 0)  # no tzinfo
    with pytest.raises(ValueError, match="timezone-aware"):
        to_vancouver(naive)


# ── Test: non-datetime raises TypeError ──────────────────────────────────────

def test_non_datetime_raises() -> None:
    with pytest.raises(TypeError):
        to_vancouver("2026-08-30T22:00:00Z")  # type: ignore[arg-type]


# ── Test: instant is conserved ────────────────────────────────────────────────

def test_instant_conserved() -> None:
    """Converting to Vancouver must not shift the underlying instant."""
    utc_dt = _utc(2026, 8, 30, 22, 0)
    local = to_vancouver(utc_dt)
    # Both datetimes represent the same point in time.
    assert utc_dt == local


def test_original_not_mutated() -> None:
    utc_dt = _utc(2026, 8, 30, 22, 0)
    _ = to_vancouver(utc_dt)
    assert utc_dt.tzinfo == timezone.utc


# ── Test: format_vancouver_time ───────────────────────────────────────────────

def test_format_default_includes_tz_abbrev() -> None:
    """Default format "%H:%M %Z" should include timezone abbreviation."""
    utc_dt = _utc(2026, 8, 30, 22, 0)
    result = format_vancouver_time(utc_dt)
    assert "15:00" in result
    # Must contain some timezone abbreviation (PDT in summer, PST in winter).
    assert "PDT" in result or "PST" in result


def test_format_custom_fmt() -> None:
    utc_dt = _utc(2026, 8, 30, 22, 0)
    result = format_vancouver_time(utc_dt, "%H:%M")
    assert result == "15:00"


def test_format_winter() -> None:
    utc_dt = _utc(2026, 1, 15, 20, 0)
    result = format_vancouver_time(utc_dt)
    assert "12:00" in result
    assert "PST" in result


def test_format_naive_raises() -> None:
    naive = datetime(2026, 8, 30, 22, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        format_vancouver_time(naive)
