"""
warmup_metrics.py — Métriques de confiance opérationnelle (P10)

Le warmup est piloté par la confiance, pas par le temps.
Chaque état produit un score [0.0, 1.0] calculé depuis l'état réel des modules.

Hiérarchie :
  WarmupMetrics       — snapshot complet à un instant T
  StateConfidence     — score de confiance pour un état donné
  MetricsCollector    — accumule les snapshots sur la fenêtre de stabilisation
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

# Seuil global : score >= 0.85 requis pour LIVE_READY
LIVE_READY_THRESHOLD = float(os.getenv("P10_LIVE_READY_THRESHOLD", "0.85"))
# Nombre min de cycles en SHADOW_MODE avant de passer LIVE_READY
SHADOW_MIN_CYCLES = int(os.getenv("P10_SHADOW_MIN_CYCLES", "10"))


@dataclass
class WarmupMetrics:
    """Snapshot de confiance opérationnelle à un instant T."""

    # Données marché
    symbols_ready: int = 0
    symbols_total: int = 0
    avg_feature_confidence: float = 0.0  # ratio features non-NaN

    # Intelligence
    regime_stability: float = 0.0  # stabilité détection régime [0,1]
    dwe_sample_coverage: float = 0.0  # % stratégies DWE avec ≥5 trades

    # Risk
    risk_sync: bool = False  # RiskGovernor + PortfolioBrain cohérents
    hard_limits_ok: bool = True  # Hard limits non dépassés

    # Mémoire stateful
    probation_consistent: bool = True  # États probation cohérents
    evolution_memory_loaded: bool = False
    transition_cache_populated: bool = False

    # Exécution
    shadow_cycles_completed: int = 0
    open_positions_unknown: bool = False  # positions live sans snapshot

    # Meta
    ts: float = field(default_factory=time.time)
    anomaly_count: int = 0  # anomalies P9 actives

    # ── Calculs ──────────────────────────────────────────────────────────────

    @property
    def data_coverage(self) -> float:
        """Ratio symboles avec données valides."""
        if self.symbols_total <= 0:
            return 0.0
        return min(1.0, self.symbols_ready / self.symbols_total)

    @property
    def warmup_score(self) -> float:
        """
        Score composite [0.0, 1.0].
        Pondération conservative : penalise fortement les risques critiques.
        """
        if not self.hard_limits_ok:
            return 0.0
        if self.open_positions_unknown:
            return 0.0

        weights = {
            "data": (self.data_coverage, 0.20),
            "features": (self.avg_feature_confidence, 0.15),
            "regime": (self.regime_stability, 0.20),
            "risk": (1.0 if self.risk_sync else 0.0, 0.20),
            "probation": (1.0 if self.probation_consistent else 0.0, 0.10),
            "memory": (1.0 if self.evolution_memory_loaded else 0.5, 0.05),
            "transition": (1.0 if self.transition_cache_populated else 0.7, 0.05),
            "anomaly": (max(0.0, 1.0 - self.anomaly_count * 0.1), 0.05),
        }
        score = sum(v * w for v, w in weights.values())
        return round(min(1.0, score), 4)

    @property
    def live_ready(self) -> bool:
        return (
            self.warmup_score >= LIVE_READY_THRESHOLD
            and self.shadow_cycles_completed >= SHADOW_MIN_CYCLES
            and self.hard_limits_ok
            and not self.open_positions_unknown
            and self.risk_sync
        )

    def to_dict(self) -> dict:
        return {
            "symbols_ready": self.symbols_ready,
            "symbols_total": self.symbols_total,
            "data_coverage": round(self.data_coverage, 3),
            "avg_feature_confidence": round(self.avg_feature_confidence, 3),
            "regime_stability": round(self.regime_stability, 3),
            "dwe_sample_coverage": round(self.dwe_sample_coverage, 3),
            "risk_sync": self.risk_sync,
            "hard_limits_ok": self.hard_limits_ok,
            "probation_consistent": self.probation_consistent,
            "evolution_memory_loaded": self.evolution_memory_loaded,
            "transition_cache_populated": self.transition_cache_populated,
            "shadow_cycles_completed": self.shadow_cycles_completed,
            "open_positions_unknown": self.open_positions_unknown,
            "anomaly_count": self.anomaly_count,
            "warmup_score": self.warmup_score,
            "live_ready": self.live_ready,
            "ts": round(self.ts, 3),
        }


@dataclass
class StateConfidence:
    """Score de confiance pour un état WarmupState spécifique."""

    state_name: str
    score: float  # [0.0, 1.0]
    details: dict = field(default_factory=dict)
    blocking_reason: Optional[str] = None

    @property
    def is_blocking(self) -> bool:
        return self.blocking_reason is not None

    def to_dict(self) -> dict:
        return {
            "state": self.state_name,
            "score": round(self.score, 3),
            "blocking": self.blocking_reason,
            "details": self.details,
        }


class MetricsHistory:
    """
    Fenêtre glissante de WarmupMetrics pour calculer la stabilité.
    La stabilité = faible variance du warmup_score sur N cycles.
    """

    def __init__(self, window: int = 5) -> None:
        self._window = window
        self._records: list[WarmupMetrics] = []

    def record(self, metrics: WarmupMetrics) -> None:
        self._records.append(metrics)
        if len(self._records) > self._window:
            self._records.pop(0)

    def stability_score(self) -> float:
        """1.0 si les scores sont stables, 0.0 si très variables."""
        if len(self._records) < 2:
            return 0.5
        scores = [m.warmup_score for m in self._records]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        # variance < 0.01 → stable, > 0.10 → instable
        return round(max(0.0, 1.0 - variance * 10), 3)

    def latest(self) -> Optional[WarmupMetrics]:
        return self._records[-1] if self._records else None

    def avg_score(self) -> float:
        if not self._records:
            return 0.0
        return round(sum(m.warmup_score for m in self._records) / len(self._records), 4)
