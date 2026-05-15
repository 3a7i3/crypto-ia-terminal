"""
execution_simulator/fill_simulator.py — Modeles de probabilite de fill.

Deux niveaux de realisme :
  AlwaysFullFill     : fill complet garanti (baseline, backtests simples)
  LiquidityBasedFill : fill partiel possible selon participation et volatilite

Toutes les classes exposent :
  simulate(intent, snapshot, rng) -> (filled_size, is_partial, rejection_reason)
  rejection_reason est None si l'ordre est au moins partiellement rempli.
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from typing import Optional

from execution_simulator.models import MarketSnapshot, OrderIntent


class BaseFillSimulator(ABC):
    @abstractmethod
    def simulate(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> tuple[float, bool, Optional[str]]:
        """
        Retourne (filled_size, is_partial, rejection_reason).
        filled_size == 0 si rejection_reason n'est pas None.
        """


class AlwaysFullFill(BaseFillSimulator):
    """
    Fill complet garanti (aucun rejet, aucun fill partiel).
    Utile pour backtests sans modelisation de liquidite.
    """

    def simulate(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> tuple[float, bool, Optional[str]]:
        return intent.size, False, None


class LiquidityBasedFill(BaseFillSimulator):
    """
    Fill partiel/rejet base sur la participation au volume journalier.

    Logique :
    1. Participation = size / ADV
    2. Taux de fill max = f(participation, volatility) — decroit si participation > seuil
    3. Pour limit orders : probabilite de fill reduite si le marche ne touche pas le prix
    4. Rejet possible si fill_size < min_fill_ratio * requested_size

    Parameters
    ----------
    max_participation   : au-dela de ce % du volume, le fill commence a degrader
    fill_decay_factor   : vitesse de degradation au-dela du seuil (>0)
    min_fill_ratio      : en-dessous, l'ordre est rejete (ex: 0.01 = 1% minimum)
    limit_fill_prob     : probabilite de base qu'un limit order soit touche (0-1)
    vol_limit_penalty   : en haute vol, les limit orders sont moins souvent touches
    """

    def __init__(
        self,
        max_participation: float = 0.05,
        fill_decay_factor: float = 10.0,
        min_fill_ratio: float = 0.01,
        limit_fill_prob: float = 0.7,
        vol_limit_penalty: float = 0.02,
    ) -> None:
        if not 0 < max_participation <= 1:
            raise ValueError(f"max_participation must be in (0, 1]")
        if fill_decay_factor <= 0:
            raise ValueError(f"fill_decay_factor must be > 0")
        if not 0 <= min_fill_ratio < 1:
            raise ValueError(f"min_fill_ratio must be in [0, 1)")
        if not 0 <= limit_fill_prob <= 1:
            raise ValueError(f"limit_fill_prob must be in [0, 1]")

        self.max_participation = max_participation
        self.fill_decay_factor = fill_decay_factor
        self.min_fill_ratio = min_fill_ratio
        self.limit_fill_prob = limit_fill_prob
        self.vol_limit_penalty = vol_limit_penalty

    def simulate(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> tuple[float, bool, Optional[str]]:
        # Limit order : probabilite d'etre touche par le marche
        if intent.order_type == "limit":
            vol_penalty = snapshot.volatility_pct * self.vol_limit_penalty
            effective_prob = max(0.0, min(1.0, self.limit_fill_prob - vol_penalty))
            if rng.random() > effective_prob:
                return 0.0, False, "limit_order_not_reached"

        # Taux de fill base sur la participation
        participation = intent.size / snapshot.adv_estimate
        if participation <= self.max_participation:
            fill_ratio = 1.0
        else:
            excess = participation - self.max_participation
            decay = math.exp(-self.fill_decay_factor * excess)
            fill_ratio = max(self.min_fill_ratio, decay)

        filled_size = intent.size * fill_ratio

        # Rejet si trop petit
        if filled_size < intent.size * self.min_fill_ratio:
            return (
                0.0,
                False,
                f"insufficient_liquidity (participation={participation:.4f})",
            )

        is_partial = fill_ratio < 0.9999
        return filled_size, is_partial, None
