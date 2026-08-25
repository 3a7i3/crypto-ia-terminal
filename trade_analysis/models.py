"""
trade_analysis/models.py — Modeles de donnees du Live Market Interaction (LMI).

Couche d'observation strictement passive (ADR-0007).
Ces structures decrivent l'etat du marche tel qu'il est observe,
sans jamais influencer une decision de trading.

Quatre dimensions d'observation :
  1. AggressiveFlow   : ce qui s'execute (pression, acceleration, taille)
  2. LiquidityDynamics: ce qui change dans le book (retire vs consomme)
  3. MarketResistance  : reponse du prix a la pression appliquee
  4. PressureField     : synthese des 3 dimensions + classification d'etat
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MarketStateLabel(Enum):
    """Classification de l'etat structurel du marche."""

    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    ABSORPTION_BUY = "absorption_buy"
    ABSORPTION_SELL = "absorption_sell"
    FRAGILITY_UP = "fragility_up"
    FRAGILITY_DOWN = "fragility_down"
    COMPRESSION = "compression"
    EXPANSION = "expansion"
    EXHAUSTION_BUY = "exhaustion_buy"
    EXHAUSTION_SELL = "exhaustion_sell"
    VACUUM_UP = "vacuum_up"
    VACUUM_DOWN = "vacuum_down"
    CONFLICT = "conflict"
    QUIET = "quiet"


@dataclass
class AggressiveFlow:
    """Flux d'ordres agressifs sur une fenetre temporelle."""

    timestamp_ms: int
    window_ms: int

    buy_volume_usd: float
    sell_volume_usd: float
    buy_count: int
    sell_count: int

    buy_avg_size_usd: float
    sell_avg_size_usd: float
    large_buy_count: int
    large_sell_count: int

    buy_acceleration: float
    sell_acceleration: float

    dominant_side: str
    pressure_ratio: float

    @property
    def total_volume_usd(self) -> float:
        return self.buy_volume_usd + self.sell_volume_usd

    @property
    def net_flow_usd(self) -> float:
        return self.buy_volume_usd - self.sell_volume_usd

    def as_dict(self) -> dict:
        return {
            "timestamp_ms": self.timestamp_ms,
            "window_ms": self.window_ms,
            "buy_volume_usd": round(self.buy_volume_usd, 2),
            "sell_volume_usd": round(self.sell_volume_usd, 2),
            "buy_count": self.buy_count,
            "sell_count": self.sell_count,
            "buy_avg_size_usd": round(self.buy_avg_size_usd, 2),
            "sell_avg_size_usd": round(self.sell_avg_size_usd, 2),
            "large_buy_count": self.large_buy_count,
            "large_sell_count": self.large_sell_count,
            "buy_acceleration": round(self.buy_acceleration, 4),
            "sell_acceleration": round(self.sell_acceleration, 4),
            "dominant_side": self.dominant_side,
            "pressure_ratio": round(self.pressure_ratio, 4),
        }


@dataclass
class LiquidityDynamics:
    """Dynamique de la liquidite entre deux snapshots du book."""

    timestamp_ms: int

    bid_added_usd: float
    bid_removed_usd: float
    ask_added_usd: float
    ask_removed_usd: float

    bid_consumed_usd: float
    ask_consumed_usd: float

    cancellation_rate_bid: float
    cancellation_rate_ask: float

    net_liquidity_change_usd: float

    def as_dict(self) -> dict:
        return {
            "timestamp_ms": self.timestamp_ms,
            "bid_added_usd": round(self.bid_added_usd, 2),
            "bid_removed_usd": round(self.bid_removed_usd, 2),
            "ask_added_usd": round(self.ask_added_usd, 2),
            "ask_removed_usd": round(self.ask_removed_usd, 2),
            "bid_consumed_usd": round(self.bid_consumed_usd, 2),
            "ask_consumed_usd": round(self.ask_consumed_usd, 2),
            "cancellation_rate_bid": round(self.cancellation_rate_bid, 4),
            "cancellation_rate_ask": round(self.cancellation_rate_ask, 4),
            "net_liquidity_change_usd": round(self.net_liquidity_change_usd, 2),
        }


@dataclass
class MarketResistance:
    """Mesure de la resistance du marche a la pression."""

    timestamp_ms: int

    volume_applied_usd: float
    price_displacement_bps: float

    resistance_score: float
    fragility_score: float
    absorption_ratio: float

    def as_dict(self) -> dict:
        return {
            "timestamp_ms": self.timestamp_ms,
            "volume_applied_usd": round(self.volume_applied_usd, 2),
            "price_displacement_bps": round(self.price_displacement_bps, 4),
            "resistance_score": round(self.resistance_score, 2),
            "fragility_score": round(self.fragility_score, 4),
            "absorption_ratio": round(self.absorption_ratio, 4),
        }


@dataclass
class PressureField:
    """Champ de pression du marche — synthese complete du LMI."""

    timestamp_ms: int
    symbol: str
    price: float
    price_change_bps: float

    flow: AggressiveFlow
    liquidity: LiquidityDynamics
    resistance: MarketResistance

    state: MarketStateLabel
    state_confidence: float
    state_components: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "timestamp_ms": self.timestamp_ms,
            "symbol": self.symbol,
            "price": self.price,
            "price_change_bps": round(self.price_change_bps, 4),
            "flow": self.flow.as_dict(),
            "liquidity": self.liquidity.as_dict(),
            "resistance": self.resistance.as_dict(),
            "state": self.state.value,
            "state_confidence": round(self.state_confidence, 4),
            "state_components": self.state_components,
        }
