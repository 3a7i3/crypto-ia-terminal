"""
market_data — Ingestion multi-exchange, modeles normalises, metriques microstructure.

Sources : Hyperliquid Perps, MEXC Futures.
"""

from market_data.connectors import HyperliquidConnector, MEXCFuturesConnector
from market_data.models import (
    MarketEvent,
    NormalizedCandle,
    NormalizedLiquidityEvent,
    NormalizedOrderBook,
    NormalizedTrade,
)
from market_data.replay_engine import FlowSnapshot, ReplayEngine, ReplayStats
from market_data.stream import MultiExchangeStream
from market_data.liquidity_engine import LiquidityEngineConfig, LiquidityEngineSupervisor

__all__ = [
    "NormalizedTrade",
    "NormalizedOrderBook",
    "NormalizedLiquidityEvent",
    "NormalizedCandle",
    "MarketEvent",
    "MultiExchangeStream",
    "ReplayEngine",
    "FlowSnapshot",
    "ReplayStats",
    "HyperliquidConnector",
    "MEXCFuturesConnector",
    "LiquidityEngineConfig",
    "LiquidityEngineSupervisor",
]
