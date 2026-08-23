from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from market_data.liquidity_engine.adapters.binance import BinanceWebSocketClient


def _load_fixture(name: str) -> str:
    base = Path(__file__).parent / "fixtures"
    return (base / name).read_text(encoding="utf-8")


def test_parse_binance_trade_message():
    client = BinanceWebSocketClient(
        symbols=["BTCUSDT"],
        ws_timeout_s=10,
        base_backoff_s=1,
        max_backoff_s=5,
    )
    received = datetime.fromtimestamp(1724392800.223, tz=timezone.utc)
    events = client.parse_message(_load_fixture("binance_trade.json"), received)
    assert len(events) == 1
    event = events[0]
    assert event.exchange == "binance"
    assert event.symbol == "BTCUSDT"
    assert event.event_type == "trade"
    assert event.price == 65000.10
    assert event.quantity == 0.5
    assert event.notional_usd == 32500.05
    assert event.side == "BUY"
    assert event.timestamp_exchange.tzinfo is not None
    assert event.timestamp_received == received
    assert event.latency_ms >= 0


def test_parse_binance_invalid_json_rejected():
    client = BinanceWebSocketClient(
        symbols=["BTCUSDT"], ws_timeout_s=10, base_backoff_s=1, max_backoff_s=5
    )
    events = client.parse_message("{broken", datetime.now(timezone.utc))
    assert events == []


def test_parse_binance_orderbook_message():
    client = BinanceWebSocketClient(
        symbols=["BTCUSDT"], ws_timeout_s=10, base_backoff_s=1, max_backoff_s=5
    )
    payload = {
        "stream": "btcusdt@depth@100ms",
        "data": {
            "e": "depthUpdate",
            "E": 1724392800123,
            "s": "BTCUSDT",
            "b": [["65000.0", "1.5"]],
            "a": [["65000.5", "2.5"]],
        },
    }
    events = client.parse_message(
        json.dumps(payload), datetime.fromtimestamp(1724392800.5, tz=timezone.utc)
    )
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "orderbook"
    assert event.raw_payload["bids"][0] == [65000.0, 1.5]
    assert event.raw_payload["asks"][0] == [65000.5, 2.5]
