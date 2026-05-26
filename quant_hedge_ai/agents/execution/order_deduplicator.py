"""
OrderDeduplicator — prevents sending the same order twice within a time window.

A duplicate is: same symbol + same action + size within the same 10%-bucket,
placed within `window_seconds` of a previous accepted order.

This guards against:
- Network timeout retries that silently succeeded on the first attempt
- Bot loops firing on the same signal before the position is confirmed
"""

from __future__ import annotations

import time

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.execution.order_deduplicator")


class OrderDeduplicator:
    """Thread-safe in-memory deduplication window."""

    def __init__(self, window_seconds: float = 30.0) -> None:
        self._window = window_seconds
        # key -> timestamp of last accepted order
        self._recent: dict[str, float] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def is_duplicate(self, symbol: str, action: str, size: float) -> bool:
        """Return True if an identical order was accepted within the window."""
        self._evict_stale()
        key = self._key(symbol, action, size)
        last = self._recent.get(key, 0.0)
        duplicate = (time.time() - last) < self._window
        if duplicate:
            _log.warning(
                "[Dedup] Duplicate order blocked: %s %s %.4f (last accepted %.1fs ago)",
                action,
                symbol,
                size,
                time.time() - last,
            )
        return duplicate

    def register(self, symbol: str, action: str, size: float) -> None:
        """Mark this order as accepted; future identical orders are blocked for `window` seconds."""
        self._recent[self._key(symbol, action, size)] = time.time()

    def reset(self) -> None:
        self._recent.clear()

    # ── Internals ──────────────────────────────────────────────────────────────

    @staticmethod
    def _key(symbol: str, action: str, size: float) -> str:
        # Bucket size to nearest 10 % to catch near-identical retries
        bucket = round(size, 1)
        return f"{symbol}|{action.upper()}|{bucket}"

    def _evict_stale(self) -> None:
        cutoff = time.time() - self._window
        self._recent = {k: v for k, v in self._recent.items() if v > cutoff}
