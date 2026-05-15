"""
execution_simulator/latency.py — Simulateur de latence d'execution.

La latence a deux effets :
  1. Delai en ms  (base_ms + jitter)
  2. Derive du prix pendant ce delai (drift stochastique)

LatencyModel.apply(intent, snapshot, rng) -> (latency_ms, price_after_latency)

Derive du prix :
  Le marche continue de se deplacer pendant la latence.
  On modelise le drift comme un mouvement brownien geometrique tronque :
    drift = sigma_per_ms * latency_ms * rng.gauss(0, 1)
  ou sigma_per_ms = volatility_pct / 100 / sqrt(390 * 60 * 1000)
    (volatilite journaliere ramenee a la milliseconde pour 6.5h de trading)
"""

from __future__ import annotations

import math
import random

from execution_simulator.models import MarketSnapshot, OrderIntent

# 6.5 heures de trading Binance perp (continu 24/7 -> 24h)
_MS_PER_DAY = 24 * 60 * 60 * 1_000.0


class LatencyModel:
    """
    Simule la latence reseau + execution et la derive de prix induite.

    Parameters
    ----------
    base_ms    : latence de base en ms (plancher deterministe)
    jitter_ms  : ecart-type du jitter gaussien (ms)
    max_ms     : cap sur la latence totale (evite outliers absurdes)
    drift_factor : multiplicateur du drift stochastique (0 = pas de derive)
    """

    def __init__(
        self,
        base_ms: float = 50.0,
        jitter_ms: float = 20.0,
        max_ms: float = 500.0,
        drift_factor: float = 1.0,
    ) -> None:
        if base_ms < 0:
            raise ValueError(f"base_ms must be >= 0")
        if jitter_ms < 0:
            raise ValueError(f"jitter_ms must be >= 0")
        if max_ms < base_ms:
            raise ValueError(f"max_ms ({max_ms}) < base_ms ({base_ms})")
        if drift_factor < 0:
            raise ValueError(f"drift_factor must be >= 0")

        self.base_ms = base_ms
        self.jitter_ms = jitter_ms
        self.max_ms = max_ms
        self.drift_factor = drift_factor

    def apply(
        self,
        intent: OrderIntent,
        snapshot: MarketSnapshot,
        rng: random.Random,
    ) -> tuple[float, float]:
        """
        Retourne (latency_ms, price_after_latency).

        price_after_latency : prix mid apres la latence simulee.
        """
        # 1. Latence
        jitter = rng.gauss(0.0, self.jitter_ms) if self.jitter_ms > 0 else 0.0
        latency_ms = max(self.base_ms, min(self.base_ms + jitter, self.max_ms))

        # 2. Derive du prix pendant la latence
        price_after = snapshot.price
        if self.drift_factor > 0 and snapshot.volatility_pct > 0:
            sigma = snapshot.volatility_pct / 100.0
            sigma_per_ms = sigma / math.sqrt(_MS_PER_DAY)
            drift_pct = sigma_per_ms * math.sqrt(latency_ms) * rng.gauss(0.0, 1.0)
            price_after = snapshot.price * (1.0 + self.drift_factor * drift_pct)
            price_after = max(price_after, 1e-9)

        return latency_ms, price_after

    def latency_drift_bps(self, original_price: float, price_after: float) -> float:
        """Calcule la derive en bps entre le prix original et post-latence."""
        if original_price <= 0:
            return 0.0
        return (price_after - original_price) / original_price * 10_000.0
