"""
tests/test_orderbook_live_viewer.py — Tests offline du viewer.

Ne tape pas le reseau : construit un book synthetique et verifie que le
rendu textuel produit contient les elements attendus (score, tier, prix).
"""

from __future__ import annotations

import re
import time

from market_data.metrics.liquidity import LiquidityConfig, liquidity_score
from market_data.models import NormalizedOrderBook
from tools.orderbook_live_viewer import Stats, _render


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip(text: str) -> str:
    return _ANSI.sub("", text)


def _synthetic_book() -> NormalizedOrderBook:
    bids = [(100.0 - i * 0.02, 500.0) for i in range(15)]
    asks = [(100.05 + i * 0.02, 500.0) for i in range(15)]
    return NormalizedOrderBook(
        exchange="test",
        symbol="ABCUSDT",
        timestamp_ms=int(time.time() * 1000),
        bids=bids,
        asks=asks,
    )


def test_render_contains_score_and_book():
    book = _synthetic_book()
    snap = liquidity_score(book)
    stats = Stats(started_at=time.time())
    stats.observe(snap)

    text = _strip(_render(book, snap, stats, depth_display=5))
    assert "ABCUSDT" in text
    assert "Liquidity Score" in text
    assert snap.tier in text
    # Presence des colonnes du book
    assert "PRICE (bid)" in text and "PRICE (ask)" in text
    # Le premier bid et le premier ask apparaissent
    assert "100.0000" in text  # meilleur bid
    assert "100.05" in text[:] or "100.0500" in text  # meilleur ask


def test_render_empty_book_shows_empty_tier():
    book = NormalizedOrderBook(
        exchange="test",
        symbol="EMPTY",
        timestamp_ms=1,
        bids=[],
        asks=[],
    )
    snap = liquidity_score(book)
    stats = Stats(started_at=time.time())
    stats.observe(snap)
    text = _strip(_render(book, snap, stats, depth_display=5))
    assert "empty" in text
    assert "Book vide" in text
