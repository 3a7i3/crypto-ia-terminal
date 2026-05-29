"""Runtime State — état centralisé du système.

INTERDICTION : self.position_cache, self.last_signal, self.internal_state
dans 14 modules différents. Tout passe par RuntimeState.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class MarketRegime(Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    NEUTRAL = "NEUTRAL"


@dataclass
class Position:
    symbol: str
    quantity: float
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timestamp: str = ""


@dataclass
class RuntimeState:
    """État central du système. Singleton."""

    mode: str = "BOOTING"
    regime: MarketRegime = MarketRegime.NEUTRAL
    positions: dict[str, Position] = field(default_factory=dict)
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    last_decision_id: Optional[str] = None
    is_kill_switch_active: bool = False
    active_exchanges: list[str] = field(default_factory=lambda: ["binance"])
    warnings: list[str] = field(default_factory=list)

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    @property
    def position_count(self) -> int:
        return len(self.positions)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        if len(self.warnings) > 100:
            self.warnings.pop(0)
