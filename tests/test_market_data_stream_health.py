from __future__ import annotations

import asyncio

import pytest

from market_data.connectors.base import BaseConnector
from market_data.models import NormalizedOrderBook, NormalizedTrade
from market_data.stream import MultiExchangeStream, StreamPipelineError


class _ScriptedConnector(BaseConnector):
    exchange_name = "scripted"

    def __init__(self, trade_script=None, orderbook_script=None):
        super().__init__()
        self._trade_script = trade_script or []
        self._orderbook_script = orderbook_script or []

    def fetch_trades(self, symbol: str, limit: int = 100):
        return []

    def fetch_orderbook(self, symbol: str, depth: int = 20):
        return NormalizedOrderBook("scripted", symbol, 0, [], [])

    def fetch_candles(self, symbol: str, timeframe: str = "1m", limit: int = 100, start_ms=None, end_ms=None):
        return []

    async def _run_script(self, script, expect: str):
        for action, payload in script:
            if action == "sleep":
                await asyncio.sleep(float(payload))
                continue
            if action == "raise":
                raise payload
            if action == "end":
                return
            if action == expect:
                yield payload

    async def stream_trades(self, symbol: str):
        async for item in self._run_script(self._trade_script, "trade"):
            yield item

    async def stream_orderbook(self, symbol: str, depth: int = 20):
        async for item in self._run_script(self._orderbook_script, "orderbook"):
            yield item


def _trade(ts: int = 1_000_000) -> NormalizedTrade:
    return NormalizedTrade(
        exchange="scripted",
        symbol="BTCUSDT",
        timestamp_ms=ts,
        price=100.0,
        size=1.0,
        side="buy",
    )


def _book(ts: int = 1_000_000) -> NormalizedOrderBook:
    return NormalizedOrderBook(
        exchange="scripted",
        symbol="BTCUSDT",
        timestamp_ms=ts,
        bids=[(99.0, 1.0)],
        asks=[(101.0, 1.0)],
    )


@pytest.mark.asyncio
async def test_stream_live_healthy_event_flow():
    stream = MultiExchangeStream()
    conn = _ScriptedConnector(trade_script=[("trade", _trade()), ("sleep", 1.0)])
    stream.add_connector(conn)

    gen = stream.stream_live("BTCUSDT", ["trade"], health_check_interval_s=0.2)
    ev = await asyncio.wait_for(anext(gen), timeout=1.0)
    assert ev.event_type == "trade"
    assert stream.last_stream_health["pipeline_state"] == "healthy"
    await gen.aclose()


@pytest.mark.asyncio
async def test_stream_live_feeder_exception_sets_health_and_fails():
    stream = MultiExchangeStream()
    conn = _ScriptedConnector(trade_script=[("raise", RuntimeError("boom"))])
    stream.add_connector(conn)

    gen = stream.stream_live("BTCUSDT", ["trade"], health_check_interval_s=0.2)
    with pytest.raises(StreamPipelineError):
        await asyncio.wait_for(anext(gen), timeout=1.5)

    health = stream.last_stream_health
    feeder = health["feeders"]["scripted:trade"]
    assert health["pipeline_state"] in {"degraded", "stopped"}
    assert feeder["error_count"] >= 1
    assert "RuntimeError" in feeder["last_error"]


@pytest.mark.asyncio
async def test_stream_live_timeout_while_feeder_alive_does_not_fail():
    stream = MultiExchangeStream()
    conn = _ScriptedConnector(trade_script=[("sleep", 0.35), ("trade", _trade(1_000_123)), ("sleep", 1.0)])
    stream.add_connector(conn)

    gen = stream.stream_live(
        "BTCUSDT",
        ["trade"],
        health_check_interval_s=0.2,
        stall_threshold_s=2.0,
    )
    ev = await asyncio.wait_for(anext(gen), timeout=2.0)
    assert ev.timestamp_ms == 1_000_123
    assert stream.last_stream_health["pipeline_state"] == "healthy"
    await gen.aclose()


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_stream_live_timeout_with_one_dead_feeder_raises_pipeline_error():
    """
    Comportement après correctif BLOCKING-1 :
    Si le feeder trade se termine (erreur) mais que le feeder orderbook continue
    de produire des événements, _check_required_feeders() doit détecter la mort
    du trade et lever StreamPipelineError — même si queue.get() ne timeout pas.

    Ce test documente la correction du zombie partiel observé en production :
    process alive + orderbook alive ≠ pipeline scientifiquement opérationnel.
    """
    stream = MultiExchangeStream()
    conn = _ScriptedConnector(
        trade_script=[("raise", RuntimeError("trade feed down"))],
        orderbook_script=[("sleep", 0.35), ("orderbook", _book(1_000_321))],
    )
    stream.add_connector(conn)

    gen = stream.stream_live(
        "BTCUSDT",
        ["trade", "orderbook"],
        health_check_interval_s=0.2,
        stall_threshold_s=2.0,
    )
    with pytest.raises(StreamPipelineError, match="trade"):
        await asyncio.wait_for(anext(gen), timeout=2.0)
    await gen.aclose()


@pytest.mark.asyncio
async def test_stream_live_all_feeders_dead_raises_controlled_failure():
    stream = MultiExchangeStream()
    conn = _ScriptedConnector(
        trade_script=[("raise", RuntimeError("trade dead"))],
        orderbook_script=[("raise", RuntimeError("book dead"))],
    )
    stream.add_connector(conn)

    gen = stream.stream_live(
        "BTCUSDT",
        ["trade", "orderbook"],
        health_check_interval_s=0.2,
        stall_threshold_s=1.0,
    )
    with pytest.raises(StreamPipelineError):
        await asyncio.wait_for(anext(gen), timeout=1.5)


@pytest.mark.asyncio
async def test_stream_live_orderbook_only_can_be_healthy():
    stream = MultiExchangeStream()
    conn = _ScriptedConnector(orderbook_script=[("orderbook", _book(1_100_000)), ("sleep", 1.0)])
    stream.add_connector(conn)

    gen = stream.stream_live(
        "BTCUSDT",
        ["orderbook"],
        health_check_interval_s=0.2,
        stall_threshold_s=2.0,
    )
    ev = await asyncio.wait_for(anext(gen), timeout=1.0)
    assert ev.event_type == "orderbook"
    assert stream.last_stream_health["pipeline_state"] == "healthy"
    await gen.aclose()


@pytest.mark.asyncio
async def test_stream_live_empty_event_types_fails_fast():
    stream = MultiExchangeStream()
    stream.add_connector(_ScriptedConnector())
    gen = stream.stream_live("BTCUSDT", [], health_check_interval_s=0.2)
    with pytest.raises(StreamPipelineError, match="No feeder tasks created"):
        await asyncio.wait_for(anext(gen), timeout=1.0)


@pytest.mark.asyncio
async def test_stream_live_unsupported_event_type_fails_fast():
    stream = MultiExchangeStream()
    stream.add_connector(_ScriptedConnector())
    gen = stream.stream_live("BTCUSDT", ["candle"], health_check_interval_s=0.2)
    with pytest.raises(StreamPipelineError, match="No feeder tasks created"):
        await asyncio.wait_for(anext(gen), timeout=1.0)


@pytest.mark.asyncio
async def test_stream_live_missing_env_uses_default_stall(monkeypatch):
    monkeypatch.delenv("LMI_STREAM_STALL_S", raising=False)
    stream = MultiExchangeStream()
    stream.add_connector(_ScriptedConnector(trade_script=[("trade", _trade()), ("sleep", 1.0)]))

    gen = stream.stream_live("BTCUSDT", ["trade"], health_check_interval_s=0.2)
    await asyncio.wait_for(anext(gen), timeout=1.0)
    health = stream.last_stream_health
    await gen.aclose()

    assert health["stall_threshold_s"] == 30.0


@pytest.mark.asyncio
async def test_stream_live_valid_env_stall(monkeypatch):
    monkeypatch.setenv("LMI_STREAM_STALL_S", "42.5")
    stream = MultiExchangeStream()
    stream.add_connector(_ScriptedConnector(trade_script=[("trade", _trade()), ("sleep", 1.0)]))

    gen = stream.stream_live("BTCUSDT", ["trade"], health_check_interval_s=0.2)
    await asyncio.wait_for(anext(gen), timeout=1.0)
    health = stream.last_stream_health
    await gen.aclose()

    assert health["stall_threshold_s"] == 42.5


@pytest.mark.asyncio
async def test_stream_live_invalid_env_stall_fallback(monkeypatch):
    monkeypatch.setenv("LMI_STREAM_STALL_S", "abc")
    stream = MultiExchangeStream()
    stream.add_connector(_ScriptedConnector(trade_script=[("trade", _trade()), ("sleep", 1.0)]))

    gen = stream.stream_live("BTCUSDT", ["trade"], health_check_interval_s=0.2)
    await asyncio.wait_for(anext(gen), timeout=1.0)
    health = stream.last_stream_health
    await gen.aclose()

    assert health["stall_threshold_s"] == 30.0


@pytest.mark.asyncio
async def test_stream_live_non_positive_env_stall_fallback(monkeypatch):
    monkeypatch.setenv("LMI_STREAM_STALL_S", "0")
    stream = MultiExchangeStream()
    stream.add_connector(_ScriptedConnector(trade_script=[("trade", _trade()), ("sleep", 1.0)]))

    gen = stream.stream_live("BTCUSDT", ["trade"], health_check_interval_s=0.2)
    await asyncio.wait_for(anext(gen), timeout=1.0)
    health = stream.last_stream_health
    await gen.aclose()

    assert health["stall_threshold_s"] == 30.0
