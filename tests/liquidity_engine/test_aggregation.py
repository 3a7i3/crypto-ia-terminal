from __future__ import annotations

from datetime import datetime, timedelta, timezone

from market_data.liquidity_engine.aggregation.liquidity import LiquidityAggregator
from market_data.liquidity_engine.config import LiquidityEngineConfig
from market_data.liquidity_engine.filters.trade_filter import ClassifiedTrade
from market_data.liquidity_engine.models import MarketEvent, TradeSizeLevel


def _event(ts: datetime, price: float, qty: float, side: str = "BUY") -> MarketEvent:
    return MarketEvent(
        exchange="binance",
        symbol="BTCUSDT",
        event_type="trade",
        timestamp_exchange=ts,
        timestamp_received=ts,
        price=price,
        quantity=qty,
        notional_usd=price * qty,
        side=side,
    )


def _classified(event: MarketEvent, level: TradeSizeLevel = TradeSizeLevel.NORMAL):
    return ClassifiedTrade(event=event, level=level, threshold_large=10_000, threshold_whale=100_000)


def test_window_aggregation_fields():
    cfg = LiquidityEngineConfig(aggregation_windows=[1, 5], price_bucket_size=10)
    ag = LiquidityAggregator(cfg)
    now = datetime.now(timezone.utc)
    ag.ingest_trade(_classified(_event(now - timedelta(seconds=1), 100.0, 2.0, "BUY")))
    ag.ingest_trade(_classified(_event(now - timedelta(seconds=1), 100.0, 1.0, "SELL"), TradeSizeLevel.LARGE))

    book_event = MarketEvent(
        exchange="binance",
        symbol="BTCUSDT",
        event_type="orderbook",
        timestamp_exchange=now,
        timestamp_received=now,
    )
    ag.ingest_orderbook(book_event, bids=[[99.5, 3.0]], asks=[[100.5, 4.0]])

    snap = ag.snapshot(now)
    assert snap["windows"]
    row = snap["windows"][0]
    assert row["total_volume"] > 0
    assert row["total_notional"] > 0
    assert "buy_sell_ratio" in row
    assert "depth_by_level" in row


def test_liquidity_pocket_detection():
    cfg = LiquidityEngineConfig(
        aggregation_windows=[5],
        price_bucket_size=1.0,
        pocket_time_window_s=30,
        min_cluster_notional=200.0,
        min_cluster_events=2,
    )
    ag = LiquidityAggregator(cfg)
    now = datetime.now(timezone.utc)

    ev1 = _event(now - timedelta(seconds=2), 100.2, 1.0, "BUY")
    ev2 = _event(now - timedelta(seconds=1), 100.3, 1.5, "BUY")
    ag.ingest_trade(_classified(ev1))
    ag.ingest_trade(_classified(ev2))

    snap = ag.snapshot(now)
    assert len(snap["pockets"]) >= 1
    pocket = snap["pockets"][0]
    assert pocket["event_count"] >= 2
