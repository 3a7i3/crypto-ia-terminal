"""Explicit caller-supplied identity; never infer instruments from a ticker label."""

from dataclasses import dataclass
from typing import Optional
from observability.venue_quote_comparison import InstrumentKey, Quote

ENDPOINTS = {
    "mexc": "spot.v3.depth",
    "bybit": "v5.market.orderbook",
    "okx": "v5.market.books",
    "kraken": "spot.rest.Depth",
    "bitfinex": "v2.book.P0",
    "kucoin": "spot.v1.market.orderbook.level1",
    "coinbase_exchange": "exchange.products.book.level2",
    "hyperliquid": "info.l2Book",
}


@dataclass(frozen=True)
class Binding:
    venue: str
    native_symbol: str
    instrument: InstrumentKey
    mapping_id: str
    mapping_sha256: str


@dataclass(frozen=True)
class Decoded:
    binding: Binding
    quote: Quote
    payload_sha256: Optional[str]
    identity_evidence: str
    native_sequence: Optional[str]
    timestamp_note: str
    decode_error: Optional[str] = None


def iso(value):
    if value is None:
        return None
    from datetime import timezone

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
