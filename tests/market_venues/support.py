"""Invented prices and mapping claims, structurally based on official response docs."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from observability.market_venues.decoders import decode_snapshot
from observability.market_venues.models import Binding
from observability.venue_quote_comparison import InstrumentKey

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
MS = 1793448000000
CLOCK = "SYNTHETIC_CLOCK"
SPOT = InstrumentKey("BTC", "USDT", "SPOT", "USDT", "SPOT")


def binding(venue, symbol=None, instrument=None):
    symbols = {
        "bybit": "BTCUSDT",
        "okx": "BTC-USDT",
        "mexc": "BTCUSDT",
        "kucoin": "BTC-USDT",
        "kraken": "XXBTZUSD",
        "bitfinex": "tBTCUSD",
        "coinbase_exchange": "BTC-USD",
        "hyperliquid": "@107",
    }
    if instrument is None:
        instrument = (
            InstrumentKey("BTC", "USD", "SPOT", "USD", "SPOT")
            if venue in ("kraken", "bitfinex", "coinbase_exchange")
            else InstrumentKey("UBTC", "USDC", "SPOT", "USDC", "SPOT")
            if venue == "hyperliquid"
            else SPOT
        )
    native = symbol or symbols[venue]
    mapping_id = (
        "SYNTHETIC-"
        + venue
        + "-"
        + instrument.market_kind
        + "-"
        + native.replace("@", "spot-")
    )
    return Binding(
        venue,
        native,
        instrument,
        mapping_id,
        hashlib.sha256(mapping_id.encode()).hexdigest(),
    )


def native(venue, *, symbol=None, time_ms=None):
    t = MS - 100 if time_ms is None else time_ms
    data = {
        "bybit": {
            "retCode": 0,
            "result": {
                "s": symbol or "BTCUSDT",
                "b": [["100", "2"]],
                "a": [["100.2", "3"]],
                "ts": t,
                "u": 1,
                "cts": t - 5,
            },
        },
        "okx": {
            "code": "0",
            "data": [
                {
                    "bids": [["100.3", "2", "0", "1"]],
                    "asks": [["100.5", "4", "0", "1"]],
                    "ts": str(t - 20),
                    "seqId": 2,
                }
            ],
        },
        "mexc": {"lastUpdateId": 3, "bids": [["100.1", "2"]], "asks": [["100.4", "3"]]},
        "kraken": {
            "error": [],
            "result": {
                symbol or "XXBTZUSD": {
                    "bids": [["100.2", "2", 1793447999]],
                    "asks": [["100.4", "3", 1793447999]],
                }
            },
        },
        "bitfinex": [[100, 2, 2], [101, 1, -3]],
        "kucoin": {
            "code": "200000",
            "data": {
                "time": t,
                "sequence": "3",
                "price": "999999",
                "size": "90",
                "bestBid": "100",
                "bestAsk": "100.3",
                "bestBidSize": "2",
                "bestAskSize": "3",
            },
        },
        "coinbase_exchange": {
            "sequence": 4,
            "bids": [["100.1", "2", 1]],
            "asks": [["100.4", "3", 1]],
            "time": (NOW - timedelta(milliseconds=100))
            .isoformat()
            .replace("+00:00", "Z"),
        },
        "hyperliquid": {
            "coin": symbol or "@107",
            "time": t,
            "levels": [
                [{"px": "100.1", "sz": "2", "n": 2}],
                [{"px": "100.4", "sz": "3", "n": 3}],
            ],
        },
    }
    return data[venue]


def raw(venue, **kwargs):
    return json.dumps(native(venue, **kwargs), separators=(",", ":")).encode()


def decode(b, payload=None, **kwargs):
    return decode_snapshot(
        b,
        raw(b.venue, symbol=b.native_symbol) if payload is None else payload,
        requested_symbol=b.native_symbol,
        requested_market_kind=b.instrument.market_kind,
        received_at=NOW,
        clock_id=CLOCK,
        requested_category="spot" if b.instrument.market_kind == "SPOT" else "linear",
        **kwargs,
    )


def pilot():
    bindings = [
        binding(v)
        for v in (
            "bybit",
            "okx",
            "mexc",
            "kucoin",
            "kraken",
            "bitfinex",
            "coinbase_exchange",
            "hyperliquid",
        )
    ]
    perp = InstrumentKey(
        "BTC", "USDT", "PERPETUAL_LINEAR", "USDT", "BTC-USDT-PERP-LINEAR"
    )
    bindings += [
        binding("bybit", instrument=perp),
        binding("okx", "BTC-USDT-SWAP", perp),
    ]
    eth = InstrumentKey("ETH", "USDT", "SPOT", "USDT", "SPOT")
    bindings += [binding("bybit", "ETHUSDT", eth), binding("okx", "ETH-USDT", eth)]
    return bindings, [decode(b) for b in bindings]
