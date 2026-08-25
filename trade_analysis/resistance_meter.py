"""
trade_analysis/resistance_meter.py — Mesure de la resistance du marche.

Repond a la question :
  "Le marche resiste-t-il a la pression ou cede-t-il ?"

Concept :
  Market Resistance = Volume Agressif Applique / Deplacement du Prix

  - Haute resistance : beaucoup de volume pour peu de mouvement
    -> quelqu'un absorbe la pression (mur solide, accumulation)
  - Basse resistance (fragilite) : peu de volume, grand mouvement
    -> book fragile, vide de liquidite

Strictement passif (ADR-0007).
"""

from __future__ import annotations

import math
from collections import deque
from typing import Optional

from market_data.models import NormalizedTrade
from trade_analysis.models import MarketResistance


class _PriceSample:
    __slots__ = ("timestamp_ms", "price", "cumul_volume_usd")

    def __init__(self, timestamp_ms: int, price: float, cumul_volume_usd: float):
        self.timestamp_ms = timestamp_ms
        self.price = price
        self.cumul_volume_usd = cumul_volume_usd


class ResistanceMeter:
    """
    Mesure la resistance du marche en comparant le volume agressif
    applique au deplacement du prix resultant.

    Maintient une fenetre glissante de samples (prix + volume cumule)
    et calcule le ratio resistance a chaque intervalle.

    Usage :
        meter = ResistanceMeter()
        for trade in trades:
            result = meter.update(trade)
            if result:
                print(f"resistance={result.resistance_score:.0f}")
    """

    def __init__(
        self,
        window_ms: int = 10_000,
        snapshot_interval_ms: int = 2_000,
        min_volume_usd: float = 1_000.0,
    ) -> None:
        self.window_ms = window_ms
        self.snapshot_interval_ms = snapshot_interval_ms
        self.min_volume_usd = min_volume_usd

        self._samples: deque[_PriceSample] = deque()
        self._cumul_vol_usd: float = 0.0
        self._window_vol_usd: float = 0.0
        self._last_snapshot_ms: int = 0

        self._vol_entering: deque[float] = deque()

    def update(self, trade: NormalizedTrade) -> Optional[MarketResistance]:
        val_usd = trade.price * trade.size
        self._cumul_vol_usd += val_usd

        self._samples.append(
            _PriceSample(trade.timestamp_ms, trade.price, self._cumul_vol_usd)
        )
        self._vol_entering.append(val_usd)

        cutoff = trade.timestamp_ms - self.window_ms
        while self._samples and self._samples[0].timestamp_ms < cutoff:
            self._samples.popleft()
            if self._vol_entering:
                self._vol_entering.popleft()

        if (
            self._last_snapshot_ms == 0
            or trade.timestamp_ms - self._last_snapshot_ms >= self.snapshot_interval_ms
        ):
            self._last_snapshot_ms = trade.timestamp_ms
            return self._build(trade.timestamp_ms)
        return None

    def _build(self, ts: int) -> MarketResistance:
        if len(self._samples) < 2:
            return MarketResistance(
                timestamp_ms=ts,
                volume_applied_usd=0.0,
                price_displacement_bps=0.0,
                resistance_score=0.0,
                fragility_score=0.0,
                absorption_ratio=0.0,
            )

        first = self._samples[0]
        last = self._samples[-1]

        volume_window = sum(self._vol_entering)
        displacement_bps = (
            abs(last.price - first.price) / first.price * 10_000.0
            if first.price > 0
            else 0.0
        )

        if displacement_bps < 0.01:
            resistance = volume_window / 0.01 if volume_window > 0 else 0.0
        else:
            resistance = volume_window / displacement_bps

        max_expected_resistance = 1_000_000.0
        fragility = 1.0 - min(resistance / max_expected_resistance, 1.0)

        if volume_window >= self.min_volume_usd and displacement_bps < 5.0:
            absorption = 1.0 - (displacement_bps / 5.0)
        else:
            absorption = 0.0

        return MarketResistance(
            timestamp_ms=ts,
            volume_applied_usd=volume_window,
            price_displacement_bps=displacement_bps,
            resistance_score=resistance,
            fragility_score=fragility,
            absorption_ratio=max(0.0, absorption),
        )
