"""
execution_simulator/fill_error_metric.py — P2.4 : Mesure de l'ecart simulation vs replay reel.

Repond a la question :
  "Mon simulateur est-il calibre ? Quel est l'ecart entre le prix simule et le prix reel ?"

Pipeline :
  (OrderIntent + MarketSnapshot) -> ExecutionSimulator -> SimulatedFill
                                                              |
  NormalizedTrade (replay JSONL)  -> FillMatcher  -> RealFill
                                                              |
                                                      FillError (ecart)
                                                              |
                                                    FillErrorMetric -> ErrorStats

Usage :
    matcher = FillMatcher(replay_trades)
    metric  = FillErrorMetric()

    for intent, snapshot, sim_fill in simulated_fills:
        real = matcher.match(intent)
        if real:
            metric.record(sim_fill, real)

    stats = metric.summary()
    print(stats.fill_price_error_mean_bps, stats.p95_abs_price_error_bps)
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from execution_simulator.models import OrderIntent, SimulatedFill

# ---------------------------------------------------------------------------
# RealFill — fill observe sur les donnees d'exchange (replay)
# ---------------------------------------------------------------------------


@dataclass
class RealFill:
    """
    Fill reel observe a partir du replay de trades historiques.

    Construit depuis un NormalizedTrade (market_data) ou manuellement
    pour les tests. signal_price est le prix au moment du signal,
    fill_price est le prix reel execute.
    """

    order_id: str
    symbol: str
    side: str  # "buy" | "sell"
    requested_size: float
    filled_size: float
    fill_price: float
    signal_price: float
    signal_timestamp_ms: int  # timestamp du signal (OrderIntent)
    fill_timestamp_ms: int  # timestamp du trade reel
    fee_usd: float = 0.0
    is_partial: bool = False
    is_rejected: bool = False
    source: str = "replay"  # "replay" | "live" | "manual"

    @property
    def fill_ratio(self) -> float:
        if self.requested_size <= 0:
            return 0.0
        return self.filled_size / self.requested_size

    @property
    def real_slippage_bps(self) -> float:
        """Slippage reel = ecart fill_price vs signal_price en bps."""
        if self.signal_price <= 0:
            return 0.0
        return abs(self.fill_price - self.signal_price) / self.signal_price * 10_000.0

    @property
    def latency_ms(self) -> float:
        return float(self.fill_timestamp_ms - self.signal_timestamp_ms)

    def as_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "requested_size": self.requested_size,
            "filled_size": self.filled_size,
            "fill_price": self.fill_price,
            "signal_price": self.signal_price,
            "signal_timestamp_ms": self.signal_timestamp_ms,
            "fill_timestamp_ms": self.fill_timestamp_ms,
            "fill_ratio": round(self.fill_ratio, 4),
            "real_slippage_bps": round(self.real_slippage_bps, 4),
            "latency_ms": round(self.latency_ms, 2),
            "fee_usd": round(self.fee_usd, 6),
            "is_partial": self.is_partial,
            "is_rejected": self.is_rejected,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# FillError — ecart entre simule et reel
# ---------------------------------------------------------------------------


@dataclass
class FillError:
    """
    Ecart entre un SimulatedFill et un RealFill.

    fill_price_error_bps > 0 : simulation surestimait le cout (conservateur).
    fill_price_error_bps < 0 : simulation sous-estimait le cout (optimiste).
    """

    order_id: str
    symbol: str
    side: str

    # Ecarts prix (bps)
    fill_price_error_bps: float  # (sim - real) / real * 10000
    slippage_error_bps: float  # sim_slippage_bps - real_slippage_bps
    latency_drift_error_bps: (
        float  # sim_latency_drift - real_drift (approx 0 si non mesurable)
    )

    # Ecart fill ratio
    fill_ratio_error: float  # sim_fill_ratio - real_fill_ratio (0 si les deux sont 1.0)

    # Ecart latence
    latency_error_ms: float  # sim_latency_ms - real_latency_ms

    # Ecart frais
    fee_error_usd: float  # sim_fee_usd - real_fee_usd

    # References completes pour audit
    simulated: SimulatedFill = field(repr=False)
    real: RealFill = field(repr=False)

    @property
    def abs_price_error_bps(self) -> float:
        return abs(self.fill_price_error_bps)

    @property
    def sim_was_conservative(self) -> bool:
        """True si la simulation surestimait le cout (fill simule > fill reel)."""
        return self.fill_price_error_bps > 0

    def as_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "fill_price_error_bps": round(self.fill_price_error_bps, 4),
            "abs_price_error_bps": round(self.abs_price_error_bps, 4),
            "slippage_error_bps": round(self.slippage_error_bps, 4),
            "fill_ratio_error": round(self.fill_ratio_error, 4),
            "latency_error_ms": round(self.latency_error_ms, 2),
            "fee_error_usd": round(self.fee_error_usd, 6),
            "sim_was_conservative": self.sim_was_conservative,
        }


def _compute_error(sim: SimulatedFill, real: RealFill) -> FillError:
    """Calcule l'ecart entre un fill simule et un fill reel."""
    # Prix
    price_error_bps = 0.0
    if real.fill_price > 0:
        price_error_bps = (
            (sim.fill_price - real.fill_price) / real.fill_price * 10_000.0
        )

    # Slippage
    slippage_error = sim.slippage_bps - real.real_slippage_bps

    # Drift latence (le reel ne decompose pas latency_drift, donc 0)
    drift_error = sim.latency_price_drift_bps

    # Fill ratio
    fill_ratio_error = sim.fill_ratio - real.fill_ratio

    # Latence
    latency_error = sim.latency_ms - real.latency_ms

    # Frais
    fee_error = sim.fee_usd - real.fee_usd

    return FillError(
        order_id=sim.order_id,
        symbol=sim.symbol,
        side=sim.side,
        fill_price_error_bps=price_error_bps,
        slippage_error_bps=slippage_error,
        latency_drift_error_bps=drift_error,
        fill_ratio_error=fill_ratio_error,
        latency_error_ms=latency_error,
        fee_error_usd=fee_error,
        simulated=sim,
        real=real,
    )


# ---------------------------------------------------------------------------
# ErrorStats — agregat de statistiques
# ---------------------------------------------------------------------------


@dataclass
class ErrorStats:
    """
    Statistiques agregees sur N paires (sim, real).

    Toutes les valeurs sont en bps sauf ou indique.
    Un simulateur bien calibre devrait avoir :
      - fill_price_error_mean_bps proche de 0 (pas de biais systematique)
      - p95_abs_price_error_bps < 10 bps (erreur max acceptable)
      - fill_ratio_error_mean proche de 0
    """

    n_samples: int
    n_conservative: int  # sim > real (surestimation du cout)
    n_optimistic: int  # sim < real (sous-estimation du cout)

    # fill_price_error_bps
    fill_price_error_mean_bps: float
    fill_price_error_std_bps: float
    fill_price_error_median_bps: float
    p95_abs_price_error_bps: float
    p99_abs_price_error_bps: float
    max_abs_price_error_bps: float

    # slippage_error_bps
    slippage_error_mean_bps: float
    slippage_error_std_bps: float

    # fill_ratio_error
    fill_ratio_error_mean: float
    fill_ratio_error_std: float

    # latency_error_ms
    latency_error_mean_ms: float
    latency_error_std_ms: float

    # fee_error_usd
    fee_error_mean_usd: float

    @property
    def bias_direction(self) -> str:
        """'conservative' | 'optimistic' | 'unbiased'."""
        if abs(self.fill_price_error_mean_bps) < 0.5:
            return "unbiased"
        return "conservative" if self.fill_price_error_mean_bps > 0 else "optimistic"

    @property
    def is_well_calibrated(self) -> bool:
        """
        True si le simulateur est considere bien calibre :
          - biais < 2 bps
          - p95 erreur absolue < 10 bps
          - fill ratio error < 5%
        """
        return (
            abs(self.fill_price_error_mean_bps) < 2.0
            and self.p95_abs_price_error_bps < 10.0
            and abs(self.fill_ratio_error_mean) < 0.05
        )

    def as_dict(self) -> dict:
        return {
            "n_samples": self.n_samples,
            "n_conservative": self.n_conservative,
            "n_optimistic": self.n_optimistic,
            "bias_direction": self.bias_direction,
            "is_well_calibrated": self.is_well_calibrated,
            "fill_price_error_mean_bps": round(self.fill_price_error_mean_bps, 4),
            "fill_price_error_std_bps": round(self.fill_price_error_std_bps, 4),
            "fill_price_error_median_bps": round(self.fill_price_error_median_bps, 4),
            "p95_abs_price_error_bps": round(self.p95_abs_price_error_bps, 4),
            "p99_abs_price_error_bps": round(self.p99_abs_price_error_bps, 4),
            "max_abs_price_error_bps": round(self.max_abs_price_error_bps, 4),
            "slippage_error_mean_bps": round(self.slippage_error_mean_bps, 4),
            "slippage_error_std_bps": round(self.slippage_error_std_bps, 4),
            "fill_ratio_error_mean": round(self.fill_ratio_error_mean, 4),
            "fill_ratio_error_std": round(self.fill_ratio_error_std, 4),
            "latency_error_mean_ms": round(self.latency_error_mean_ms, 2),
            "latency_error_std_ms": round(self.latency_error_std_ms, 2),
            "fee_error_mean_usd": round(self.fee_error_mean_usd, 6),
        }


def _percentile(sorted_data: list[float], p: float) -> float:
    """Percentile lineaire sur liste triee."""
    if not sorted_data:
        return 0.0
    n = len(sorted_data)
    idx = p / 100.0 * (n - 1)
    lo = int(math.floor(idx))
    hi = min(lo + 1, n - 1)
    return sorted_data[lo] + (idx - lo) * (sorted_data[hi] - sorted_data[lo])


def _stats_from_errors(errors: list[FillError]) -> ErrorStats:
    """Calcule ErrorStats a partir d'une liste de FillError."""
    if not errors:
        raise ValueError("Cannot compute stats on empty error list")

    price_errors = [e.fill_price_error_bps for e in errors]
    abs_errors = sorted(abs(x) for x in price_errors)
    slip_errors = [e.slippage_error_bps for e in errors]
    ratio_errors = [e.fill_ratio_error for e in errors]
    lat_errors = [e.latency_error_ms for e in errors]
    fee_errors = [e.fee_error_usd for e in errors]

    n = len(errors)
    n_cons = sum(1 for e in errors if e.fill_price_error_bps > 0)

    def _mean(lst: list[float]) -> float:
        return statistics.mean(lst) if lst else 0.0

    def _std(lst: list[float]) -> float:
        return statistics.stdev(lst) if len(lst) > 1 else 0.0

    return ErrorStats(
        n_samples=n,
        n_conservative=n_cons,
        n_optimistic=n - n_cons,
        fill_price_error_mean_bps=_mean(price_errors),
        fill_price_error_std_bps=_std(price_errors),
        fill_price_error_median_bps=statistics.median(price_errors),
        p95_abs_price_error_bps=_percentile(abs_errors, 95),
        p99_abs_price_error_bps=_percentile(abs_errors, 99),
        max_abs_price_error_bps=max(abs_errors) if abs_errors else 0.0,
        slippage_error_mean_bps=_mean(slip_errors),
        slippage_error_std_bps=_std(slip_errors),
        fill_ratio_error_mean=_mean(ratio_errors),
        fill_ratio_error_std=_std(ratio_errors),
        latency_error_mean_ms=_mean(lat_errors),
        latency_error_std_ms=_std(lat_errors),
        fee_error_mean_usd=_mean(fee_errors),
    )


# ---------------------------------------------------------------------------
# FillErrorMetric — collecteur principal
# ---------------------------------------------------------------------------


class FillErrorMetric:
    """
    Collecte les paires (SimulatedFill, RealFill) et calcule les statistiques d'ecart.

    Usage :
        metric = FillErrorMetric()
        metric.record(sim_fill, real_fill)
        ...
        stats = metric.summary()
        metric.to_jsonl("errors.jsonl")
    """

    def __init__(self) -> None:
        self._errors: list[FillError] = []

    @property
    def n_samples(self) -> int:
        return len(self._errors)

    def record(self, sim: SimulatedFill, real: RealFill) -> FillError:
        """
        Enregistre une paire et retourne l'ecart calcule.
        Les fills rejetes sont ignores (pas d'ecart mesurable).
        """
        if sim.is_rejected or real.is_rejected:
            raise ValueError("Cannot compute error for rejected fills")
        error = _compute_error(sim, real)
        self._errors.append(error)
        return error

    def summary(self) -> ErrorStats:
        """Calcule les statistiques agregees sur tous les echantillons enregistres."""
        if not self._errors:
            raise ValueError("No samples recorded — call record() first")
        return _stats_from_errors(self._errors)

    def errors(self) -> list[FillError]:
        """Retourne la liste brute des ecarts."""
        return list(self._errors)

    def reset(self) -> None:
        """Vide tous les echantillons."""
        self._errors.clear()

    def to_jsonl(self, path: str | Path) -> None:
        """Exporte tous les ecarts dans un fichier JSONL."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for e in self._errors:
                f.write(json.dumps(e.as_dict()) + "\n")


# ---------------------------------------------------------------------------
# FillMatcher — apparie un OrderIntent avec le trade reel le plus proche
# ---------------------------------------------------------------------------


class FillMatcher:
    """
    Apparie un OrderIntent avec le trade reel correspondant dans un replay.

    Cherche le premier trade apres le signal qui :
      - correspond au meme symbole
      - correspond au meme cote (side) que le taker
      - survient dans la fenetre max_window_ms

    Usage :
        matcher = FillMatcher(trades, max_window_ms=2000)
        real_fill = matcher.match(intent, signal_ts_ms)
    """

    def __init__(
        self,
        trades: list,  # list[NormalizedTrade] du replay
        max_window_ms: int = 2_000,
        requested_size: float = 0.0,
    ) -> None:
        # Trier par timestamp pour la recherche binaire
        self._trades = sorted(trades, key=lambda t: t.timestamp_ms)
        self.max_window_ms = max_window_ms
        self.requested_size = requested_size

    def match(
        self,
        intent: OrderIntent,
        signal_ts_ms: int,
        order_id: str = "",
    ) -> Optional[RealFill]:
        """
        Retourne un RealFill construit depuis le premier trade correspondant,
        ou None si aucun trade trouve dans la fenetre.
        """
        deadline_ms = signal_ts_ms + self.max_window_ms
        candidate = None

        for trade in self._trades:
            if trade.timestamp_ms < signal_ts_ms:
                continue
            if trade.timestamp_ms > deadline_ms:
                break
            if trade.symbol.upper() != intent.symbol.upper():
                continue
            if trade.side != intent.side:
                continue
            candidate = trade
            break

        if candidate is None:
            return None

        size = self.requested_size if self.requested_size > 0 else intent.size
        return RealFill(
            order_id=order_id or intent.strategy_id or "unknown",
            symbol=intent.symbol,
            side=intent.side,
            requested_size=size,
            filled_size=min(size, candidate.size),
            fill_price=candidate.price,
            signal_price=intent.signal_price,
            signal_timestamp_ms=signal_ts_ms,
            fill_timestamp_ms=candidate.timestamp_ms,
            is_partial=candidate.size < size,
            source="replay",
        )
