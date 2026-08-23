from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class TradeSizeLevel(str, Enum):
    NORMAL = "NORMAL"
    LARGE = "LARGE"
    WHALE = "WHALE"


@dataclass
class MarketEvent:
    exchange: str
    symbol: str
    event_type: str
    timestamp_exchange: datetime
    timestamp_received: datetime
    price: float = 0.0
    quantity: float = 0.0
    notional_usd: float = 0.0
    side: str = "unknown"
    trade_id: str = ""
    timestamp_processed: datetime | None = None
    latency_ms: float = 0.0
    priority: int = 0
    raw_payload: dict = field(default_factory=dict, repr=False)

    def mark_processed(self, when: datetime | None = None) -> None:
        self.timestamp_processed = when or datetime.now(timezone.utc)

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)


@dataclass
class LiquidityPocket:
    exchange: str
    symbol: str
    price_level: float
    volume: float
    notional: float
    side: str
    first_seen: datetime
    last_seen: datetime
    event_count: int


@dataclass
class WindowAggregation:
    exchange: str
    symbol: str
    window_s: int
    timestamp: datetime
    total_volume: float
    total_notional: float
    buy_volume: float
    sell_volume: float
    buy_notional: float
    sell_notional: float
    large_trade_count: int
    whale_trade_count: int
    largest_trade: float
    average_trade_size: float
    volume_delta: float
    buy_sell_ratio: float
    bid_liquidity: float = 0.0
    ask_liquidity: float = 0.0
    bid_ask_imbalance: float = 0.0
    spread: float = 0.0
    depth_by_level: dict[str, float] = field(default_factory=dict)
