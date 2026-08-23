from __future__ import annotations

from datetime import datetime, timezone

from market_data.liquidity_engine.config import LiquidityEngineConfig
from market_data.liquidity_engine.filters.trade_filter import TradeFilter
from market_data.liquidity_engine.models import MarketEvent, TradeSizeLevel


def _trade(notional: float) -> MarketEvent:
    now = datetime.now(timezone.utc)
    price = 65000.0
    qty = notional / price
    return MarketEvent(
        exchange="binance",
        symbol="BTCUSDT",
        event_type="trade",
        timestamp_exchange=now,
        timestamp_received=now,
        price=price,
        quantity=qty,
        notional_usd=notional,
        side="BUY",
    )


def test_threshold_classification_normal_large_whale():
    cfg = LiquidityEngineConfig(
        large_trade_threshold_usd=10_000,
        whale_trade_threshold_usd=100_000,
    )
    f = TradeFilter(cfg)
    assert f.classify_trade(_trade(9_999)).level == TradeSizeLevel.NORMAL
    assert f.classify_trade(_trade(10_000)).level == TradeSizeLevel.LARGE
    assert f.classify_trade(_trade(100_000)).level == TradeSizeLevel.WHALE


def test_exchange_symbol_specific_threshold_override():
    cfg = LiquidityEngineConfig(
        threshold_by_exchange_symbol={
            "binance": {"BTCUSDT": {"large": 20_000, "whale": 50_000}}
        }
    )
    f = TradeFilter(cfg)
    assert f.classify_trade(_trade(15_000)).level == TradeSizeLevel.NORMAL
    assert f.classify_trade(_trade(25_000)).level == TradeSizeLevel.LARGE


def test_dynamic_percentile_threshold():
    cfg = LiquidityEngineConfig(
        large_trade_threshold_usd=100,
        whale_trade_threshold_usd=1000,
        dynamic_percentile=90,
        dynamic_min_samples=10,
    )
    f = TradeFilter(cfg)
    for i in range(1, 21):
        f.classify_trade(_trade(float(i * 1000)))
    out = f.classify_trade(_trade(15000.0))
    assert out.threshold_large >= 100
