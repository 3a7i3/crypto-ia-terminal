from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Position:
    symbol: str
    size: float
    entry_price: float
    side: str  # "long" or "short"
    unrealized_pnl: float = 0.0
    opened_at: Optional[datetime] = None  # UTC, set by VirtualExchange.place_order
