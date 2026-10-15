"""Génération de barres synthétiques déterministes (seed explicite)."""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SYNTHETIC_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)  # horloge fictive
BAR_SECONDS = 60


@dataclass(frozen=True)
class Bar:
    i: int
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def as_dict(self) -> dict:
        return {
            "i": self.i,
            "ts": self.ts,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


def bar_ts(i: int) -> str:
    return (SYNTHETIC_EPOCH + timedelta(seconds=BAR_SECONDS * i)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def generate_bars(
    *,
    seed: int,
    n: int,
    start_price: float = 100.0,
    drift_bps: float = 0.0,
    vol_bps: float = 15.0,
    shocks: dict[int, float] | None = None,
    volume_base: float = 5_000.0,
) -> list[Bar]:
    """Marche aléatoire géométrique + chocs scénarisés `{indice: bps}`."""
    rng = random.Random(seed)
    shocks = shocks or {}
    bars: list[Bar] = []
    prev = float(start_price)
    for i in range(n):
        ret = (
            drift_bps + vol_bps * rng.gauss(0.0, 1.0) + shocks.get(i, 0.0)
        ) / 10_000.0
        close = prev * math.exp(ret)
        wick = abs(rng.gauss(0.0, 1.0)) * vol_bps * 0.3 / 10_000.0
        high = max(prev, close) * (1.0 + wick)
        low = min(prev, close) * (1.0 - wick)
        vol = volume_base * (0.8 + 0.4 * rng.random())
        bars.append(
            Bar(
                i,
                bar_ts(i),
                round(prev, 6),
                round(high, 6),
                round(low, 6),
                round(close, 6),
                round(vol, 3),
            )
        )
        prev = close
    return bars


def bars_digest(bars: list[Bar]) -> str:
    blob = json.dumps(
        [b.as_dict() for b in bars], sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode()).hexdigest()
