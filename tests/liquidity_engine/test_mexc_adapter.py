from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from market_data.liquidity_engine.adapters.mexc import MexcWebSocketClient


def _load_fixture(name: str) -> str:
    base = Path(__file__).parent / "fixtures"
    return (base / name).read_text(encoding="utf-8")


def test_parse_mexc_trade_message():
    client = MexcWebSocketClient(
        symbols=["BTCUSDT"], ws_timeout_s=10, base_backoff_s=1, max_backoff_s=5
    )
    received = datetime.fromtimestamp(1724392800.400, tz=timezone.utc)
    events = client.parse_message(_load_fixture("mexc_deal.json"), received)
    assert len(events) == 1
    event = events[0]
    assert event.exchange == "mexc"
    assert event.symbol == "BTCUSDT"
    assert event.event_type == "trade"
    assert event.side == "BUY"
    assert event.price == 65000.1
    assert event.quantity == 0.25
    assert event.notional_usd == 16250.025


def test_parse_mexc_depth_message():
    client = MexcWebSocketClient(
        symbols=["BTCUSDT"], ws_timeout_s=10, base_backoff_s=1, max_backoff_s=5
    )
    payload = {
        "channel": "push.depth",
        "symbol": "BTC_USDT",
        "data": {
            "timestamp": 1724392800123,
            "bids": ["65000.0", "64999.5"],
            "bidVols": ["1.0", "2.0"],
            "asks": ["65000.5", "65001.0"],
            "askVols": ["1.5", "2.5"],
        },
    }
    events = client.parse_message(
        json.dumps(payload), datetime.fromtimestamp(1724392800.5, tz=timezone.utc)
    )
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "orderbook"
    assert ev.raw_payload["bids"][0] == [65000.0, 1.0]
    assert ev.raw_payload["asks"][1] == [65001.0, 2.5]


def test_parse_mexc_invalid_message_rejected():
    client = MexcWebSocketClient(
        symbols=["BTCUSDT"], ws_timeout_s=10, base_backoff_s=1, max_backoff_s=5
    )
    events = client.parse_message("{}", datetime.now(timezone.utc))
    assert events == []
