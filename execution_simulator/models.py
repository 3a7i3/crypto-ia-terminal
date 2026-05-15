"""
execution_simulator/models.py — Dataclasses partagees entre tous les composants.

OrderIntent    : ce que la strategie veut faire
MarketSnapshot : etat du marche au moment de l'execution
SimulatedFill  : resultat d'une execution simulee (audit complet)
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass
class OrderIntent:
    """Ce que la strategie demande a executer."""

    symbol: str
    side: str  # "buy" | "sell"
    size: float  # en devise de base (ex: BTC)
    order_type: str  # "market" | "limit"
    signal_price: float  # prix au moment ou le signal a ete genere
    limit_price: Optional[float] = None
    timestamp: float = 0.0
    strategy_id: str = ""

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got '{self.side}'")
        if self.order_type not in ("market", "limit"):
            raise ValueError(
                f"order_type must be 'market' or 'limit', got '{self.order_type}'"
            )
        if self.size <= 0:
            raise ValueError(f"size must be > 0, got {self.size}")
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit_price required for limit orders")

    @property
    def direction(self) -> int:
        """+1 pour buy (paie le ask), -1 pour sell (recoit le bid)."""
        return 1 if self.side == "buy" else -1


@dataclass
class MarketSnapshot:
    """Etat du marche disponible lors de la simulation d'execution."""

    symbol: str
    price: float  # prix mid (utiliser le close OHLCV)
    volume_24h: float  # volume 24h en devise de base
    volatility_pct: float  # volatilite journaliere realisee en %
    bid: Optional[float] = None
    ask: Optional[float] = None
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError(f"price must be > 0, got {self.price}")
        if self.volume_24h < 0:
            raise ValueError(f"volume_24h must be >= 0, got {self.volume_24h}")
        if self.volatility_pct < 0:
            raise ValueError(f"volatility_pct must be >= 0, got {self.volatility_pct}")

    @property
    def spread_bps(self) -> Optional[float]:
        """Spread observe en bps si bid/ask disponibles."""
        if self.bid and self.ask and self.bid > 0:
            return (self.ask - self.bid) / self.bid * 10_000
        return None

    @property
    def adv_estimate(self) -> float:
        """Average daily volume estime en devise de base."""
        return max(self.volume_24h, 1.0)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


@dataclass
class SimulatedFill:
    """Resultat complet d'une execution simulee. Audit trail complet."""

    order_id: str
    symbol: str
    side: str
    requested_size: float
    filled_size: float
    fill_price: float
    signal_price: float
    slippage_bps: float  # impact de marche
    spread_cost_bps: float  # cout du spread (0 pour limit dans le book)
    latency_ms: float
    fee_usd: float
    fee_rate_bps: float
    is_partial: bool
    is_rejected: bool
    rejection_reason: Optional[str]
    fill_timestamp: float

    # Audit de decomposition des couts
    price_at_execution: float = 0.0  # prix apres latence (avant slippage)
    latency_price_drift_bps: float = 0.0

    @property
    def total_cost_bps(self) -> float:
        """Cout total en bps: slippage + spread + fees."""
        return round(self.slippage_bps + self.spread_cost_bps + self.fee_rate_bps, 4)

    @property
    def fill_value_usd(self) -> float:
        return self.filled_size * self.fill_price

    @property
    def slippage_usd(self) -> float:
        """Cout en USD du slippage seul."""
        return abs(self.fill_price - self.signal_price) * self.filled_size

    @property
    def fill_ratio(self) -> float:
        if self.requested_size <= 0:
            return 0.0
        return self.filled_size / self.requested_size

    def as_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "requested_size": self.requested_size,
            "filled_size": self.filled_size,
            "fill_price": self.fill_price,
            "signal_price": self.signal_price,
            "slippage_bps": round(self.slippage_bps, 4),
            "spread_cost_bps": round(self.spread_cost_bps, 4),
            "latency_ms": round(self.latency_ms, 2),
            "fee_usd": round(self.fee_usd, 6),
            "fee_rate_bps": round(self.fee_rate_bps, 4),
            "total_cost_bps": round(self.total_cost_bps, 4),
            "is_partial": self.is_partial,
            "is_rejected": self.is_rejected,
            "rejection_reason": self.rejection_reason,
            "fill_ratio": round(self.fill_ratio, 4),
        }

    @classmethod
    def rejected(
        cls, intent: OrderIntent, reason: str, timestamp: float = 0.0
    ) -> "SimulatedFill":
        return cls(
            order_id=str(uuid.uuid4())[:8],
            symbol=intent.symbol,
            side=intent.side,
            requested_size=intent.size,
            filled_size=0.0,
            fill_price=0.0,
            signal_price=intent.signal_price,
            slippage_bps=0.0,
            spread_cost_bps=0.0,
            latency_ms=0.0,
            fee_usd=0.0,
            fee_rate_bps=0.0,
            is_partial=False,
            is_rejected=True,
            rejection_reason=reason,
            fill_timestamp=timestamp,
        )
