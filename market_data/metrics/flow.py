"""
market_data/metrics/flow.py — Metriques de flux d'ordres (microstructure).

Ces metriques repondent a la question :
  "Qui controle le marche en ce moment — acheteurs ou vendeurs ?"

Metriques implementees :
  CumulativeDelta   : CVD (Cumulative Volume Delta) — buy - sell volume
  AbsorptionTracker : detecte quand un gros volume est absorbe sans mouvement de prix
  SweepDetector     : detecte les balayages rapides de liquidite
  PersistenceTracker: mesure combien de temps un mur reste dans le book
  FlowMetrics       : agregat complet pour le replay engine

Regle absolue (user) :
  Toute nouvelle metrique doit ameliorer prediction / robustness / regime / risk.
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from market_data.models import NormalizedOrderBook, NormalizedTrade

# ---------------------------------------------------------------------------
# Cumulative Volume Delta (CVD)
# ---------------------------------------------------------------------------


@dataclass
class DeltaWindow:
    """CVD sur une fenetre temporelle glissante."""

    window_ms: int
    _trades: deque = field(default_factory=deque, repr=False)

    def update(self, trade: NormalizedTrade) -> None:
        self._trades.append(trade)
        cutoff = trade.timestamp_ms - self.window_ms
        while self._trades and self._trades[0].timestamp_ms < cutoff:
            self._trades.popleft()

    @property
    def delta(self) -> float:
        """Buy volume - sell volume dans la fenetre."""
        return sum(t.signed_size for t in self._trades)

    @property
    def buy_volume(self) -> float:
        return sum(t.size for t in self._trades if t.side == "buy")

    @property
    def sell_volume(self) -> float:
        return sum(t.size for t in self._trades if t.side == "sell")

    @property
    def total_volume(self) -> float:
        return self.buy_volume + self.sell_volume

    @property
    def delta_pct(self) -> float:
        """Delta en % du volume total."""
        tv = self.total_volume
        return self.delta / tv * 100.0 if tv > 0 else 0.0

    @property
    def n_trades(self) -> int:
        return len(self._trades)

    @property
    def buy_count(self) -> int:
        return sum(1 for t in self._trades if t.side == "buy")

    @property
    def sell_count(self) -> int:
        return sum(1 for t in self._trades if t.side == "sell")


class CumulativeDeltaTracker:
    """
    Suit le CVD sur plusieurs fenetres simultanement (1m, 5m, 15m).
    Reinitialise a chaque nouvelle bougie si desired.
    """

    def __init__(
        self,
        windows_ms: Optional[list[int]] = None,
    ) -> None:
        windows_ms = windows_ms or [60_000, 300_000, 900_000]  # 1m, 5m, 15m
        self.windows: dict[int, DeltaWindow] = {
            w: DeltaWindow(window_ms=w) for w in windows_ms
        }
        self._session_delta = 0.0  # CVD depuis le debut de la session

    def update(self, trade: NormalizedTrade) -> None:
        for w in self.windows.values():
            w.update(trade)
        self._session_delta += trade.signed_size

    @property
    def session_delta(self) -> float:
        return self._session_delta

    def snapshot(self) -> dict[str, float]:
        result = {"session_delta": self._session_delta}
        for ms, w in self.windows.items():
            label = f"{ms // 60_000}m"
            result[f"delta_{label}"] = w.delta
            result[f"delta_pct_{label}"] = w.delta_pct
            result[f"buy_vol_{label}"] = w.buy_volume
            result[f"sell_vol_{label}"] = w.sell_volume
        return result

    def reset_session(self) -> None:
        self._session_delta = 0.0


# ---------------------------------------------------------------------------
# Absorption
# ---------------------------------------------------------------------------


@dataclass
class AbsorptionEvent:
    timestamp_ms: int
    side: str  # "buy" | "sell" : cote qui absorbe
    price: float
    volume_absorbed: float  # volume trade
    price_move_bps: float  # mouvement de prix pendant l'absorption
    absorption_score: (
        float  # volume / |price_move| (plus c'est haut, plus c'est absorbant)
    )


class AbsorptionTracker:
    """
    Detecte l'absorption : gros volume trade a un niveau sans que le prix bouge.
    Signal : les vendeurs (ou acheteurs) "absorbent" la pression opposee.

    Un absorption_score eleve signifie :
      "beaucoup de volume a ete digere sans que le prix bouge" -> mur solide.
    """

    def __init__(
        self,
        window_ms: int = 5_000,  # fenetre d'observation (5 secondes)
        min_volume_usd: float = 50_000.0,  # volume minimum pour qualifier
        max_price_move_bps: float = 5.0,  # mouvement prix max pour qualifier
    ) -> None:
        self.window_ms = window_ms
        self.min_volume_usd = min_volume_usd
        self.max_price_move_bps = max_price_move_bps
        self._trades: deque[NormalizedTrade] = deque()
        self._price_open: Optional[float] = None
        self._window_start_ms: int = 0

    def update(self, trade: NormalizedTrade) -> Optional[AbsorptionEvent]:
        """
        Ajoute un trade. Retourne un AbsorptionEvent si detecte, None sinon.
        """
        if self._price_open is None:
            self._price_open = trade.price
            self._window_start_ms = trade.timestamp_ms

        # Nouveau window si depasse
        if trade.timestamp_ms - self._window_start_ms > self.window_ms:
            event = self._evaluate()
            self._trades.clear()
            self._price_open = trade.price
            self._window_start_ms = trade.timestamp_ms
            if event:
                return event

        self._trades.append(trade)
        return None

    def _evaluate(self) -> Optional[AbsorptionEvent]:
        if not self._trades or self._price_open is None:
            return None

        last_price = self._trades[-1].price
        price_move_bps = (
            abs(last_price - self._price_open) / self._price_open * 10_000.0
        )

        buy_vol_usd = sum(t.price * t.size for t in self._trades if t.side == "buy")
        sell_vol_usd = sum(t.price * t.size for t in self._trades if t.side == "sell")
        dominant_vol = max(buy_vol_usd, sell_vol_usd)
        dominant_side = "buy" if buy_vol_usd >= sell_vol_usd else "sell"

        if dominant_vol < self.min_volume_usd:
            return None
        if price_move_bps > self.max_price_move_bps:
            return None

        # Score : volume / max(price_move_bps, 0.1) pour eviter division par zero
        score = dominant_vol / max(price_move_bps, 0.1)

        return AbsorptionEvent(
            timestamp_ms=self._trades[-1].timestamp_ms,
            side=dominant_side,
            price=last_price,
            volume_absorbed=dominant_vol,
            price_move_bps=price_move_bps,
            absorption_score=score,
        )


# ---------------------------------------------------------------------------
# Sweep Detection
# ---------------------------------------------------------------------------


@dataclass
class SweepEvent:
    timestamp_ms: int
    side: str  # "buy" | "sell"
    start_price: float
    end_price: float
    price_move_bps: float
    volume_usd: float
    duration_ms: float
    velocity: float  # volume_usd / duration_ms (USD par ms)
    n_trades: int


class SweepDetector:
    """
    Detecte les sweeps : consommation rapide de liquidite sur plusieurs niveaux.
    Signal fort : ordre agressif qui traverse plusieurs niveaux du book.

    Criteres :
      - volume_usd > min_volume_usd
      - price_move_bps > min_move_bps
      - duration < max_duration_ms
    """

    def __init__(
        self,
        min_volume_usd: float = 100_000.0,
        min_move_bps: float = 10.0,
        max_duration_ms: float = 2_000.0,
    ) -> None:
        self.min_volume_usd = min_volume_usd
        self.min_move_bps = min_move_bps
        self.max_duration_ms = max_duration_ms
        self._buffer: deque[NormalizedTrade] = deque()
        self._in_sweep = False
        self._sweep_start: Optional[NormalizedTrade] = None

    def update(self, trade: NormalizedTrade) -> Optional[SweepEvent]:
        self._buffer.append(trade)
        # Garder seulement les trades dans la fenetre temporelle
        cutoff = trade.timestamp_ms - self.max_duration_ms
        while self._buffer and self._buffer[0].timestamp_ms < cutoff:
            self._buffer.popleft()

        if len(self._buffer) < 2:
            return None

        first = self._buffer[0]
        last = trade
        duration_ms = last.timestamp_ms - first.timestamp_ms
        if duration_ms <= 0:
            return None

        price_move_bps = abs(last.price - first.price) / first.price * 10_000.0
        total_usd = sum(t.price * t.size for t in self._buffer)

        if price_move_bps >= self.min_move_bps and total_usd >= self.min_volume_usd:
            # Determiner la direction dominante du sweep
            buy_usd = sum(t.price * t.size for t in self._buffer if t.side == "buy")
            sell_usd = total_usd - buy_usd
            side = "buy" if buy_usd >= sell_usd else "sell"

            event = SweepEvent(
                timestamp_ms=last.timestamp_ms,
                side=side,
                start_price=first.price,
                end_price=last.price,
                price_move_bps=price_move_bps,
                volume_usd=total_usd,
                duration_ms=duration_ms,
                velocity=total_usd / max(duration_ms, 1.0),
                n_trades=len(self._buffer),
            )
            self._buffer.clear()
            return event
        return None


# ---------------------------------------------------------------------------
# Persistence & Wall Migration
# ---------------------------------------------------------------------------


@dataclass
class WallSnapshot:
    timestamp_ms: int
    side: str
    price: float
    size_usd: float


@dataclass
class WallLifecycle:
    """Cycle de vie complet d'un mur (apparition, deplacement, disparition)."""

    side: str
    first_seen_ms: int
    last_seen_ms: int
    initial_price: float
    final_price: float
    initial_size_usd: float
    final_size_usd: float
    price_migration_bps: float  # deplacement du mur en bps
    duration_ms: float
    fate: str  # "filled" | "cancelled" | "migrated" | "active"


class PersistenceTracker:
    """
    Suit les murs de liquidite a travers les snapshots du book.

    Detecte :
      - persistence : combien de temps un mur reste (signal de vraie liquidite)
      - cancellation velocity : disparition rapide sans trade (spoofing signal)
      - wall migration : le mur se deplace en suivant le prix

    Usage :
      tracker.update(book_snapshot)  -> list[WallLifecycle] (murs fermes)
    """

    def __init__(
        self,
        min_wall_usd: float = 200_000.0,
        price_tolerance_bps: float = 10.0,  # pour tracker un mur qui migre
        max_gap_ms: int = 30_000,  # si absent > 30s, le mur est ferme
    ) -> None:
        self.min_wall_usd = min_wall_usd
        self.price_tolerance_bps = price_tolerance_bps
        self.max_gap_ms = max_gap_ms
        self._active_walls: dict[str, list[WallSnapshot]] = {}  # key = "side_price"
        self._last_update_ms: int = 0

    def update(
        self,
        book: NormalizedOrderBook,
    ) -> list[WallLifecycle]:
        """
        Met a jour le tracker avec un nouveau snapshot.
        Retourne les murs qui viennent de fermer (cancelled ou migres).
        """
        ts = book.timestamp_ms
        closed: list[WallLifecycle] = []

        # Identifier les murs dans le snapshot courant
        current_walls: dict[str, WallSnapshot] = {}
        all_levels = [("bid", p, p * s) for p, s in book.bids] + [
            ("ask", p, p * s) for p, s in book.asks
        ]
        usd_vols = [v for _, _, v in all_levels]
        if len(usd_vols) < 3:
            return []

        mean = statistics.mean(usd_vols)
        stdev = statistics.stdev(usd_vols) if len(usd_vols) > 1 else 0.0

        for side, price, vol_usd in all_levels:
            if vol_usd >= self.min_wall_usd and (stdev == 0 or vol_usd > mean + stdev):
                key = f"{side}_{price:.8g}"
                current_walls[key] = WallSnapshot(ts, side, price, vol_usd)

        # Fermer les murs actifs disparus depuis plus de max_gap_ms
        for key, snapshots in list(self._active_walls.items()):
            if key not in current_walls:
                if ts - snapshots[-1].timestamp_ms > self.max_gap_ms:
                    closed.append(self._close_wall(key, snapshots, "cancelled"))
                    del self._active_walls[key]

        # Mettre a jour ou creer les murs actifs
        for key, snap in current_walls.items():
            if key in self._active_walls:
                self._active_walls[key].append(snap)
            else:
                self._active_walls[key] = [snap]

        self._last_update_ms = ts
        return closed

    def _close_wall(
        self,
        key: str,
        snapshots: list[WallSnapshot],
        fate: str,
    ) -> WallLifecycle:
        first = snapshots[0]
        last = snapshots[-1]
        migration_bps = (
            abs(last.price - first.price) / max(first.price, 1e-9) * 10_000.0
        )
        if migration_bps > 5.0:
            fate = "migrated"
        return WallLifecycle(
            side=first.side,
            first_seen_ms=first.timestamp_ms,
            last_seen_ms=last.timestamp_ms,
            initial_price=first.price,
            final_price=last.price,
            initial_size_usd=first.size_usd,
            final_size_usd=last.size_usd,
            price_migration_bps=migration_bps,
            duration_ms=float(last.timestamp_ms - first.timestamp_ms),
            fate=fate,
        )

    @property
    def active_wall_count(self) -> int:
        return len(self._active_walls)


# ---------------------------------------------------------------------------
# Agregat complet (pour le replay engine)
# ---------------------------------------------------------------------------


@dataclass
class FlowSnapshot:
    """Etat complet des metriques de flux a un instant T."""

    timestamp_ms: int
    symbol: str
    # CVD
    delta_1m: float
    delta_5m: float
    delta_pct_1m: float
    # Imbalance book
    book_imbalance: float
    book_pressure_imbalance: float
    spread_bps: float
    # Evenements recents
    last_absorption: Optional[AbsorptionEvent]
    last_sweep: Optional[SweepEvent]
    active_wall_count: int

    def as_dict(self) -> dict:
        d = {
            "timestamp_ms": self.timestamp_ms,
            "symbol": self.symbol,
            "delta_1m": round(self.delta_1m, 4),
            "delta_5m": round(self.delta_5m, 4),
            "delta_pct_1m": round(self.delta_pct_1m, 2),
            "book_imbalance": round(self.book_imbalance, 4),
            "book_pressure_imbalance": round(self.book_pressure_imbalance, 4),
            "spread_bps": round(self.spread_bps, 4),
            "active_wall_count": self.active_wall_count,
        }
        if self.last_absorption:
            d["absorption_score"] = round(self.last_absorption.absorption_score, 2)
            d["absorption_side"] = self.last_absorption.side
        if self.last_sweep:
            d["sweep_velocity"] = round(self.last_sweep.velocity, 2)
            d["sweep_side"] = self.last_sweep.side
        return d
