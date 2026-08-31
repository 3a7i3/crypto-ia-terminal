"""Presentation-layer helpers for local time display.

All business logic MUST use UTC datetimes.  This module's sole
responsibility is converting an aware UTC ``datetime`` to
``America/Vancouver`` for display purposes only.

PDT/PST transitions are handled automatically by ``zoneinfo``.
No fixed offset (+7 / +8) is ever applied.

Usage::

    from src.common.time_display import to_vancouver, format_vancouver_time

    local_dt = to_vancouver(utc_dt)
    label    = format_vancouver_time(utc_dt)          # "15:30 PDT"
    label    = format_vancouver_time(utc_dt, "%H:%M") # "15:30"
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

VANCOUVER_TZ = ZoneInfo("America/Vancouver")


def to_vancouver(dt: datetime) -> datetime:
    """Convert a timezone-aware *dt* to America/Vancouver.

    The returned ``datetime`` is timezone-aware and represents the same
    instant as *dt* — only the local representation changes.

    Args:
        dt: A timezone-aware ``datetime``.  Passing a naive ``datetime``
            raises ``ValueError`` because the source timezone is unknown
            and an arbitrary assumption would silently corrupt the result.

    Returns:
        A timezone-aware ``datetime`` in America/Vancouver.

    Raises:
        ValueError: If *dt* is naive (has no ``tzinfo``).
        TypeError:  If *dt* is not a ``datetime`` instance.
    """
    if not isinstance(dt, datetime):
        raise TypeError(f"Expected datetime, got {type(dt).__name__!r}")
    if dt.tzinfo is None:
        raise ValueError(
            "to_vancouver() requires a timezone-aware datetime. "
            "Attach timezone information (e.g. timezone.utc) before calling."
        )
    return dt.astimezone(VANCOUVER_TZ)


def format_vancouver_time(dt: datetime, fmt: str = "%H:%M %Z") -> str:
    """Return a formatted string of *dt* converted to America/Vancouver.

    The default format ``"%H:%M %Z"`` produces e.g. ``"15:30 PDT"`` in
    summer or ``"12:00 PST"`` in winter — the abbreviation is always
    consistent with the actual offset at that instant.

    Args:
        dt:  A timezone-aware ``datetime``.
        fmt: ``strftime`` format string (default ``"%H:%M %Z"``).

    Returns:
        Formatted local-time string in America/Vancouver.

    Raises:
        ValueError: If *dt* is naive.
        TypeError:  If *dt* is not a ``datetime`` instance.
    """
    return to_vancouver(dt).strftime(fmt)
