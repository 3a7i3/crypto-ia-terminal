from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from market_data.liquidity_engine.config import LiquidityEngineConfig
from market_data.liquidity_engine.models import MarketEvent
from market_data.liquidity_engine.publishing.publisher import InMemoryPublisher
from market_data.liquidity_engine.runtime.supervisor import LiquidityEngineSupervisor


@pytest.mark.asyncio
async def test_supervisor_processes_trade_event_without_ws():
    cfg = LiquidityEngineConfig(binance_enabled=False, mexc_enabled=False)
    publisher = InMemoryPublisher()
    sup = LiquidityEngineSupervisor(cfg, publisher=publisher)
    await sup.start()

    now = datetime.now(timezone.utc)
    ev = MarketEvent(
        exchange="binance",
        symbol="BTCUSDT",
        event_type="trade",
        timestamp_exchange=now,
        timestamp_received=now,
        price=10000,
        quantity=2,
        notional_usd=20000,
        side="BUY",
        priority=1,
    )
    await sup._on_market_event(ev)
    await asyncio.sleep(0.2)
    await sup.stop()

    assert publisher.events
    types = [e["type"] for e in publisher.events]
    assert "MARKET_EVENT" in types
    assert "BIG_TRADE_EVENT" in types
    assert sup.metrics.messages_processed >= 1


@pytest.mark.asyncio
async def test_exchange_outage_does_not_block_pipeline():
    cfg = LiquidityEngineConfig(binance_enabled=False, mexc_enabled=False)
    publisher = InMemoryPublisher()
    sup = LiquidityEngineSupervisor(cfg, publisher=publisher)
    await sup.start()

    # Simule un exchange down via aucun producer actif, le supervisor continue.
    await asyncio.sleep(0.05)
    now = datetime.now(timezone.utc)
    ev = MarketEvent(
        exchange="mexc",
        symbol="BTCUSDT",
        event_type="trade",
        timestamp_exchange=now,
        timestamp_received=now,
        price=50000,
        quantity=1,
        notional_usd=50000,
        side="SELL",
        priority=1,
    )
    await sup._on_market_event(ev)
    await asyncio.sleep(0.2)
    await sup.stop()

    assert len(publisher.events) >= 1
