"""
execution_simulator/slippage.py — Modeles de slippage parametrables.

Trois niveaux de realisme :
  FixedSlippage  : slippage constant en bps (baseline simple)
  LinearSlippage : slippage proportionnel a la participation (linear impact)
  SqrtSlippage   : Almgren-Chriss sqrt model (market impact realiste)

Toutes les classes exposent :
  compute(intent, snapshot, rng) -> slippage_bps: float
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod

from execution_simulator.models import MarketSnapshot, OrderIntent


class BaseSlippage(ABC):
    @abstractmethod
    def compute(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> float:
        """Retourne le slippage en bps (toujours >= 0)."""


class FixedSlippage(BaseSlippage):
    """
    Slippage constant independant du size.
    Utile comme baseline ou pour petits ordres.
    """

    def __init__(self, bps: float = 2.0) -> None:
        if bps < 0:
            raise ValueError(f"bps must be >= 0, got {bps}")
        self.bps = bps

    def compute(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> float:
        return self.bps


class LinearSlippage(BaseSlippage):
    """
    Slippage lineaire en fonction de la participation (size / ADV).

    slippage_bps = base_bps + impact_factor * participation_pct * 100

    participation_pct : fraction du volume journalier (0..1)
    impact_factor     : bps par point de % de participation (ex: 0.5 = 0.5 bps par %)
    """

    def __init__(self, base_bps: float = 1.0, impact_factor: float = 0.5) -> None:
        if base_bps < 0:
            raise ValueError(f"base_bps must be >= 0")
        if impact_factor < 0:
            raise ValueError(f"impact_factor must be >= 0")
        self.base_bps = base_bps
        self.impact_factor = impact_factor

    def compute(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> float:
        participation = intent.size / snapshot.adv_estimate
        impact = self.impact_factor * participation * 100.0
        return self.base_bps + impact


class SqrtSlippage(BaseSlippage):
    """
    Modele Almgren-Chriss simplifie : impact = sigma * eta * sqrt(participation).

    sigma      : volatilite journaliere realisee (fraction, ex 0.02 = 2%)
    eta        : constante de liquidite (calibree sur les donnees — default 0.1)
    noise_bps  : bruit gaussien autour de l'impact (ecart-type en bps)

    Formule :
      impact_bps = sigma * eta * sqrt(size / ADV) * 10_000
      noise      = rng.gauss(0, noise_bps)  si noise_bps > 0
      slippage   = max(0, impact_bps + noise)

    Ref : Almgren & Chriss (2000), "Optimal execution of portfolio transactions"
    """

    def __init__(
        self,
        eta: float = 0.1,
        noise_bps: float = 0.5,
    ) -> None:
        if eta <= 0:
            raise ValueError(f"eta must be > 0, got {eta}")
        if noise_bps < 0:
            raise ValueError(f"noise_bps must be >= 0")
        self.eta = eta
        self.noise_bps = noise_bps

    def compute(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> float:
        sigma = snapshot.volatility_pct / 100.0
        if sigma <= 0:
            return 0.0
        participation = intent.size / snapshot.adv_estimate
        impact_bps = sigma * self.eta * math.sqrt(participation) * 10_000.0
        # Le bruit est proportionnel a l'impact : pas de bruit si pas d'impact
        noise_scale = impact_bps / max(impact_bps, 1.0)
        noise = (
            rng.gauss(0.0, self.noise_bps * noise_scale) if self.noise_bps > 0 else 0.0
        )
        return max(0.0, impact_bps + noise)
