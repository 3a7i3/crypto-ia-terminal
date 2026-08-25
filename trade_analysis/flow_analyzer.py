"""
trade_analysis/flow_analyzer.py — Analyse du flux d'ordres agressifs.

Repond a la question :
  "Quelle quantite de pression arrive actuellement, et accelere-t-elle ?"

Observe :
  - Volume agressif (taker buy vs taker sell)
  - Frequence des trades
  - Acceleration (derivee du volume)
  - Distribution de taille (detection gros ordres)
  - Cote dominant

Strictement passif (ADR-0007) — aucune influence sur les decisions.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from market_data.models import NormalizedTrade
from trade_analysis.models import AggressiveFlow


@dataclass
class _VolumeSlice:
    """Volume agrege sur un micro-intervalle (bucket)."""

    start_ms: int
    buy_usd: float = 0.0
    sell_usd: float = 0.0
    buy_count: int = 0
    sell_count: int = 0


class FlowAnalyzer:
    """
    Analyse le flux d'ordres agressifs en temps reel.

    Decoupe le temps en buckets (par defaut 1 seconde) et maintient
    une fenetre glissante pour calculer volume, acceleration et
    distribution de taille.

    Usage :
        analyzer = FlowAnalyzer()
        for trade in trades:
            snapshot = analyzer.update(trade)
            if snapshot:
                print(snapshot.pressure_ratio)
    """

    def __init__(
        self,
        window_ms: int = 10_000,
        bucket_ms: int = 1_000,
        large_order_usd: float = 50_000.0,
        snapshot_interval_ms: int = 1_000,
    ) -> None:
        self.window_ms = window_ms
        self.bucket_ms = bucket_ms
        self.large_order_usd = large_order_usd
        self.snapshot_interval_ms = snapshot_interval_ms

        self._buckets: deque[_VolumeSlice] = deque()
        self._current_bucket: _VolumeSlice | None = None
        self._trades: deque[NormalizedTrade] = deque()
        self._last_snapshot_ms: int = 0
        self._prev_buy_rate: float = 0.0
        self._prev_sell_rate: float = 0.0

    def update(self, trade: NormalizedTrade) -> AggressiveFlow | None:
        self._trades.append(trade)
        cutoff = trade.timestamp_ms - self.window_ms
        while self._trades and self._trades[0].timestamp_ms < cutoff:
            self._trades.popleft()

        self._update_bucket(trade)

        if (
            self._last_snapshot_ms == 0
            or trade.timestamp_ms - self._last_snapshot_ms >= self.snapshot_interval_ms
        ):
            self._last_snapshot_ms = trade.timestamp_ms
            return self._build_snapshot(trade.timestamp_ms)
        return None

    def _update_bucket(self, trade: NormalizedTrade) -> None:
        bucket_start = (trade.timestamp_ms // self.bucket_ms) * self.bucket_ms

        if self._current_bucket is None or self._current_bucket.start_ms != bucket_start:
            if self._current_bucket is not None:
                self._buckets.append(self._current_bucket)
            self._current_bucket = _VolumeSlice(start_ms=bucket_start)
            cutoff = bucket_start - self.window_ms
            while self._buckets and self._buckets[0].start_ms < cutoff:
                self._buckets.popleft()

        val_usd = trade.price * trade.size
        if trade.side == "buy":
            self._current_bucket.buy_usd += val_usd
            self._current_bucket.buy_count += 1
        else:
            self._current_bucket.sell_usd += val_usd
            self._current_bucket.sell_count += 1

    def _build_snapshot(self, ts: int) -> AggressiveFlow:
        buy_vol = 0.0
        sell_vol = 0.0
        buy_count = 0
        sell_count = 0
        large_buy = 0
        large_sell = 0

        for t in self._trades:
            val = t.price * t.size
            if t.side == "buy":
                buy_vol += val
                buy_count += 1
                if val >= self.large_order_usd:
                    large_buy += 1
            else:
                sell_vol += val
                sell_count += 1
                if val >= self.large_order_usd:
                    large_sell += 1

        buy_avg = buy_vol / buy_count if buy_count > 0 else 0.0
        sell_avg = sell_vol / sell_count if sell_count > 0 else 0.0

        total = buy_vol + sell_vol
        pressure = buy_vol / total if total > 0 else 0.5

        if pressure > 0.55:
            dominant = "buy"
        elif pressure < 0.45:
            dominant = "sell"
        else:
            dominant = "neutral"

        window_s = self.window_ms / 1000.0
        buy_rate = buy_vol / window_s if window_s > 0 else 0.0
        sell_rate = sell_vol / window_s if window_s > 0 else 0.0

        buy_accel = buy_rate - self._prev_buy_rate
        sell_accel = sell_rate - self._prev_sell_rate
        self._prev_buy_rate = buy_rate
        self._prev_sell_rate = sell_rate

        return AggressiveFlow(
            timestamp_ms=ts,
            window_ms=self.window_ms,
            buy_volume_usd=buy_vol,
            sell_volume_usd=sell_vol,
            buy_count=buy_count,
            sell_count=sell_count,
            buy_avg_size_usd=buy_avg,
            sell_avg_size_usd=sell_avg,
            large_buy_count=large_buy,
            large_sell_count=large_sell,
            buy_acceleration=buy_accel,
            sell_acceleration=sell_accel,
            dominant_side=dominant,
            pressure_ratio=pressure,
        )

    @property
    def current_buy_pressure(self) -> float:
        if not self._trades:
            return 0.5
        buy = sum(t.price * t.size for t in self._trades if t.side == "buy")
        total = sum(t.price * t.size for t in self._trades)
        return buy / total if total > 0 else 0.5
