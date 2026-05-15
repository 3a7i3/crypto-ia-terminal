"""
market_data/replay_engine.py — Moteur de replay microstructure.

ReplayEngine rejoue des evenements enregistres (JSONL) en ordre chronologique
et calcule les metriques de flux en temps reel.

Pipeline de replay :
  JSONL file -> MarketEvent stream -> MetricsComputer -> FlowSnapshot

Usage :
    engine = ReplayEngine("data/btcusdt_20240101.jsonl")
    for snapshot in engine.replay():
        print(snapshot.delta_1m, snapshot.book_imbalance)

Format JSONL attendu :
  Chaque ligne = JSON d'un MarketEvent.as_dict()
  {"event_type": "trade", "exchange": "binance", "symbol": "BTCUSDT",
   "timestamp_ms": 1704067200000, "data": {...}}
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Optional

from market_data.metrics.flow import (
    AbsorptionEvent,
    AbsorptionTracker,
    CumulativeDeltaTracker,
    FlowSnapshot,
    PersistenceTracker,
    SweepDetector,
    SweepEvent,
    WallLifecycle,
)
from market_data.metrics.orderbook import book_pressure, features_vector
from market_data.models import (
    MarketEvent,
    NormalizedCandle,
    NormalizedLiquidityEvent,
    NormalizedOrderBook,
    NormalizedTrade,
)


@dataclass
class ReplayStats:
    total_events: int = 0
    trade_count: int = 0
    orderbook_count: int = 0
    candle_count: int = 0
    liquidity_count: int = 0
    absorptions: int = 0
    sweeps: int = 0
    wall_closures: int = 0
    duration_ms: float = 0.0
    first_ts_ms: int = 0
    last_ts_ms: int = 0

    @property
    def events_per_second(self) -> float:
        if self.duration_ms <= 0:
            return 0.0
        return self.total_events / (self.duration_ms / 1000.0)


class ReplayEngine:
    """
    Replay d'un fichier JSONL d'evenements de marche.

    Le moteur maintient l'etat des metriques (CVD, absorption, sweep, murs)
    et emet des FlowSnapshot a chaque interval configurable.
    """

    def __init__(
        self,
        source: str | Path,
        symbol: str = "",
        snapshot_interval_ms: int = 1_000,  # emettre un snapshot toutes les Xms
        absorption_window_ms: int = 5_000,
        sweep_min_vol_usd: float = 100_000.0,
        wall_min_usd: float = 200_000.0,
    ) -> None:
        self.source = Path(source)
        self.symbol = symbol
        self.snapshot_interval_ms = snapshot_interval_ms

        self._cvd = CumulativeDeltaTracker([60_000, 300_000])
        self._absorption = AbsorptionTracker(
            window_ms=absorption_window_ms,
            min_volume_usd=50_000.0,
        )
        self._sweep = SweepDetector(min_volume_usd=sweep_min_vol_usd)
        self._persistence = PersistenceTracker(min_wall_usd=wall_min_usd)

        self._last_book: Optional[NormalizedOrderBook] = None
        self._last_snapshot_ms: int = 0
        self._last_absorption: Optional[AbsorptionEvent] = None
        self._last_sweep: Optional[SweepEvent] = None
        self.stats = ReplayStats()

    # ------------------------------------------------------------------
    # Chargement JSONL
    # ------------------------------------------------------------------

    def _iter_events(self) -> Iterator[MarketEvent]:
        """Lit les evenements du fichier JSONL ligne par ligne."""
        with open(self.source, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    event = self._deserialize(raw)
                    if event:
                        yield event
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

    def _deserialize(self, raw: dict) -> Optional[MarketEvent]:
        """Reconstruit un MarketEvent depuis un dict JSON."""
        etype = raw.get("event_type")
        exch = raw.get("exchange", "")
        sym = raw.get("symbol", self.symbol)
        ts = int(raw.get("timestamp_ms", 0))
        d = raw.get("data", {})

        if etype == "trade":
            obj = NormalizedTrade(
                exchange=exch,
                symbol=sym,
                timestamp_ms=ts,
                price=float(d.get("price", 0)),
                size=float(d.get("size", 0)),
                side=d.get("side", "buy"),
                trade_id=str(d.get("trade_id", "")),
                is_liquidation=bool(d.get("is_liquidation", False)),
            )
            return MarketEvent.from_trade(obj)

        if etype == "orderbook":
            obj = NormalizedOrderBook(
                exchange=exch,
                symbol=sym,
                timestamp_ms=ts,
                bids=[(float(b[0]), float(b[1])) for b in d.get("bids", [])],
                asks=[(float(a[0]), float(a[1])) for a in d.get("asks", [])],
                sequence=int(d.get("sequence", 0)),
                is_snapshot=bool(d.get("is_snapshot", True)),
            )
            return MarketEvent.from_orderbook(obj)

        if etype == "candle":
            obj = NormalizedCandle(
                exchange=exch,
                symbol=sym,
                timestamp_ms=ts,
                timeframe=d.get("timeframe", "1m"),
                open=float(d.get("open", 0)),
                high=float(d.get("high", 0)),
                low=float(d.get("low", 0)),
                close=float(d.get("close", 0)),
                volume=float(d.get("volume", 0)),
                buy_volume=float(d.get("buy_volume", 0)),
                sell_volume=float(d.get("sell_volume", 0)),
                trade_count=int(d.get("trade_count", 0)),
                is_closed=bool(d.get("is_closed", True)),
            )
            return MarketEvent.from_candle(obj)

        if etype == "liquidity":
            obj = NormalizedLiquidityEvent(
                exchange=exch,
                symbol=sym,
                timestamp_ms=ts,
                event_type=d.get("event_type", "liquidation"),
                side=d.get("side", "buy"),
                price=float(d.get("price", 0)),
                size=float(d.get("size", 0)),
            )
            return MarketEvent.from_liquidity(obj)

        return None

    # ------------------------------------------------------------------
    # Replay principal
    # ------------------------------------------------------------------

    def replay(
        self,
        on_event: Optional[Callable[[MarketEvent], None]] = None,
    ) -> Iterator[FlowSnapshot]:
        """
        Rejoue tous les evenements et emet des FlowSnapshot periodiques.

        on_event : callback optionnel appele pour chaque evenement brut.
        Yields   : FlowSnapshot a chaque snapshot_interval_ms.
        """
        t0 = time.monotonic()
        self.stats = ReplayStats()

        for event in self._iter_events():
            self.stats.total_events += 1
            if self.stats.first_ts_ms == 0:
                self.stats.first_ts_ms = event.timestamp_ms
            self.stats.last_ts_ms = event.timestamp_ms

            # Dispatcher par type
            if event.event_type == "trade":
                self.stats.trade_count += 1
                snapshot = self._process_trade(event.data)
                if snapshot:
                    yield snapshot

            elif event.event_type == "orderbook":
                self.stats.orderbook_count += 1
                self._last_book = event.data
                closed_walls = self._persistence.update(event.data)
                self.stats.wall_closures += len(closed_walls)

            elif event.event_type == "candle":
                self.stats.candle_count += 1

            elif event.event_type == "liquidity":
                self.stats.liquidity_count += 1

            if on_event:
                on_event(event)

        self.stats.duration_ms = (time.monotonic() - t0) * 1000.0
        if self.stats.first_ts_ms and self.stats.last_ts_ms:
            self.stats.duration_ms = float(
                self.stats.last_ts_ms - self.stats.first_ts_ms
            )

    def _process_trade(self, trade: NormalizedTrade) -> Optional[FlowSnapshot]:
        """Traite un trade et emet un snapshot si l'interval est depasse."""
        self._cvd.update(trade)

        absorption = self._absorption.update(trade)
        if absorption:
            self._last_absorption = absorption
            self.stats.absorptions += 1

        sweep = self._sweep.update(trade)
        if sweep:
            self._last_sweep = sweep
            self.stats.sweeps += 1

        # Emettre snapshot
        if (
            self._last_snapshot_ms == 0
            or trade.timestamp_ms - self._last_snapshot_ms >= self.snapshot_interval_ms
        ):
            self._last_snapshot_ms = trade.timestamp_ms
            return self._build_snapshot(trade.timestamp_ms, trade.symbol)
        return None

    def _build_snapshot(self, ts_ms: int, symbol: str) -> FlowSnapshot:
        cvd = self._cvd.snapshot()
        book_imb = 0.0
        press_imb = 0.0
        spread = 0.0
        if self._last_book:
            book_imb = self._last_book.imbalance(5)
            press_imb = book_pressure(self._last_book, 0.5)["imbalance"]
            spread = self._last_book.spread_bps or 0.0

        return FlowSnapshot(
            timestamp_ms=ts_ms,
            symbol=symbol,
            delta_1m=cvd.get("delta_1m", 0.0),
            delta_5m=cvd.get("delta_5m", 0.0),
            delta_pct_1m=cvd.get("delta_pct_1m", 0.0),
            book_imbalance=book_imb,
            book_pressure_imbalance=press_imb,
            spread_bps=spread,
            last_absorption=self._last_absorption,
            last_sweep=self._last_sweep,
            active_wall_count=self._persistence.active_wall_count,
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def snapshots_to_jsonl(
        self, output: str | Path, on_event: Optional[Callable] = None
    ) -> ReplayStats:
        """Replay complet en ecrivant les snapshots dans un fichier JSONL."""
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for snap in self.replay(on_event):
                f.write(json.dumps(snap.as_dict()) + "\n")
        return self.stats
