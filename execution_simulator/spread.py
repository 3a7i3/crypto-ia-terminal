"""
execution_simulator/spread.py — Modeles de spread bid/ask.

Le spread est le cout paye pour traverser le book en tant que market-taker.
Un limit order dans le book paie 0 de spread (maker).

FixedSpread   : spread constant en bps
DynamicSpread : spread volatilite-dependant (s'elargit en stress)

Toutes les classes exposent :
  compute(intent, snapshot, rng) -> spread_cost_bps: float
  (toujours >= 0 ; 0 pour un limit order maker)
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from execution_simulator.models import MarketSnapshot, OrderIntent


class BaseSpread(ABC):
    @abstractmethod
    def compute(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> float:
        """Retourne le cout du spread en bps pour cet ordre."""


class FixedSpread(BaseSpread):
    """
    Spread constant.
    Les limit orders dans le book (maker) paient 0.
    """

    def __init__(self, bps: float = 1.0) -> None:
        if bps < 0:
            raise ValueError(f"bps must be >= 0, got {bps}")
        self.bps = bps

    def compute(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> float:
        if intent.order_type == "limit":
            return 0.0
        return self.bps


class DynamicSpread(BaseSpread):
    """
    Spread dynamique : s'elargit avec la volatilite et peut varier avec le volume.

    Formule :
      half_spread = base_bps + vol_multiplier * volatility_pct
      spread_cost = half_spread + noise (gaussien tronque >= 0)

    En pratique : BTC perp spread ~0.5-1 bps normal, ~3-5 bps en stress.
    Si bid/ask disponibles dans snapshot, on utilise le spread observe.
    """

    def __init__(
        self,
        base_bps: float = 0.5,
        vol_multiplier: float = 0.1,
        noise_bps: float = 0.2,
    ) -> None:
        if base_bps < 0:
            raise ValueError(f"base_bps must be >= 0")
        if vol_multiplier < 0:
            raise ValueError(f"vol_multiplier must be >= 0")
        if noise_bps < 0:
            raise ValueError(f"noise_bps must be >= 0")
        self.base_bps = base_bps
        self.vol_multiplier = vol_multiplier
        self.noise_bps = noise_bps

    def compute(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> float:
        if intent.order_type == "limit":
            return 0.0

        # Priorite : spread observe dans le snapshot
        observed = snapshot.spread_bps
        if observed is not None and observed > 0:
            half_spread = observed / 2.0
        else:
            half_spread = self.base_bps + self.vol_multiplier * snapshot.volatility_pct

        noise = rng.gauss(0.0, self.noise_bps) if self.noise_bps > 0 else 0.0
        return max(0.0, half_spread + noise)
