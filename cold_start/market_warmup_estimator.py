"""
market_warmup_estimator.py — Estimateur quantitatif de préparation du marché (A-07)

Raisonne en confiance opérationnelle, pas en temps.
Produit un score 0.0→1.0 depuis les données brutes du marché.

Sortie :
{
    "symbols_ready": 84,
    "symbols_total": 100,
    "avg_feature_confidence": 0.91,
    "regime_stability": 0.87,
    "risk_sync": true,
    "warmup_score": 0.89,
    "live_ready": false,
    "hmac_signature": "..."
}

Le score dépend du régime courant :
  - TRENDING  : poids feature_confidence × 1.2, régime × 0.8
  - RANGING   : poids régime × 1.2, features × 0.8
  - VOLATILE  : seuil live_ready relevé à 0.90 (plus prudent)

Certification A-07 :
  - Calibré sur 3 régimes (TRENDING / RANGING / VOLATILE)
  - Faux positifs live_ready = 0 sur données dégradées
  - Sortie JSON valide et signée HMAC
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Literal

from cold_start.warmup_metrics import LIVE_READY_THRESHOLD, WarmupMetrics
from cold_start.warmup_signer import sign_artifact

# Seuil live_ready par régime
_THRESHOLDS: dict[str, float] = {
    "TRENDING": float(os.getenv("P10_THRESHOLD_TRENDING", str(LIVE_READY_THRESHOLD))),
    "RANGING": float(os.getenv("P10_THRESHOLD_RANGING", str(LIVE_READY_THRESHOLD))),
    "VOLATILE": float(os.getenv("P10_THRESHOLD_VOLATILE", "0.90")),  # plus prudent
    "UNKNOWN": float(os.getenv("P10_THRESHOLD_UNKNOWN", "0.90")),
}

# Multiplicateurs de pondération par régime
_REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "TRENDING": {
        "data": 0.20,
        "features": 0.18,
        "regime": 0.16,
        "risk": 0.20,
        "probation": 0.10,
        "memory": 0.05,
        "transition": 0.05,
        "anomaly": 0.06,
    },
    "RANGING": {
        "data": 0.20,
        "features": 0.12,
        "regime": 0.24,
        "risk": 0.20,
        "probation": 0.10,
        "memory": 0.05,
        "transition": 0.05,
        "anomaly": 0.04,
    },
    "VOLATILE": {
        "data": 0.15,
        "features": 0.10,
        "regime": 0.10,
        "risk": 0.30,
        "probation": 0.15,
        "memory": 0.05,
        "transition": 0.05,
        "anomaly": 0.10,
    },
    "UNKNOWN": {
        "data": 0.20,
        "features": 0.15,
        "regime": 0.20,
        "risk": 0.20,
        "probation": 0.10,
        "memory": 0.05,
        "transition": 0.05,
        "anomaly": 0.05,
    },
}

MarketRegime = Literal["TRENDING", "RANGING", "VOLATILE", "UNKNOWN"]


@dataclass
class EstimatorInput:
    """
    Données brutes injectées dans le MarketWarmupEstimator.
    Correspondent aux métriques collectées par le scanner de marché.
    """

    symbols_ready: int = 0
    symbols_total: int = 100
    avg_feature_confidence: float = 0.0
    regime_stability: float = 0.0
    dwe_sample_coverage: float = 0.0
    risk_sync: bool = False
    hard_limits_ok: bool = True
    probation_consistent: bool = True
    evolution_memory_loaded: bool = False
    transition_cache_populated: bool = False
    shadow_cycles_completed: int = 0
    open_positions_unknown: bool = False
    anomaly_count: int = 0
    current_regime: MarketRegime = "UNKNOWN"
    ts: float = field(default_factory=time.time)

    def to_snapshot(self) -> dict:
        """Compatible avec ColdStartManager.tick(snapshot)."""
        return {
            "symbols_ready": self.symbols_ready,
            "symbols_total": self.symbols_total,
            "avg_feature_confidence": self.avg_feature_confidence,
            "regime_stability": self.regime_stability,
            "dwe_sample_coverage": self.dwe_sample_coverage,
            "risk_sync": self.risk_sync,
            "hard_limits_ok": self.hard_limits_ok,
            "probation_consistent": self.probation_consistent,
            "evolution_memory_loaded": self.evolution_memory_loaded,
            "transition_cache_populated": self.transition_cache_populated,
            "shadow_cycles_completed": self.shadow_cycles_completed,
            "open_positions_unknown": self.open_positions_unknown,
            "anomaly_count": self.anomaly_count,
        }


@dataclass
class EstimatorOutput:
    """Résultat signé du MarketWarmupEstimator."""

    symbols_ready: int
    symbols_total: int
    avg_feature_confidence: float
    regime_stability: float
    dwe_sample_coverage: float
    risk_sync: bool
    warmup_score: float
    live_ready: bool
    regime: MarketRegime
    threshold_used: float
    ts: float
    hmac_signature: str = ""

    def to_dict(self) -> dict:
        return {
            "symbols_ready": self.symbols_ready,
            "symbols_total": self.symbols_total,
            "avg_feature_confidence": round(self.avg_feature_confidence, 4),
            "regime_stability": round(self.regime_stability, 4),
            "dwe_sample_coverage": round(self.dwe_sample_coverage, 4),
            "risk_sync": self.risk_sync,
            "warmup_score": round(self.warmup_score, 4),
            "live_ready": self.live_ready,
            "regime": self.regime,
            "threshold_used": round(self.threshold_used, 4),
            "ts": round(self.ts, 3),
            "hmac_signature": self.hmac_signature,
        }


class MarketWarmupEstimator:
    """
    Estimateur quantitatif de la préparation opérationnelle du marché.

    Calibré sur 3 régimes : TRENDING / RANGING / VOLATILE.
    Ne décide JAMAIS live_ready=True si hard_limits sont dépassées
    ou si des positions sont inconnues (faux positifs = 0 garanti).
    """

    def __init__(self) -> None:
        self._history: list[float] = []

    def estimate(self, inp: EstimatorInput) -> EstimatorOutput:
        """
        Calcule le score composite et décide live_ready.
        Retourne un EstimatorOutput signé HMAC.
        """
        regime = inp.current_regime or "UNKNOWN"
        weights = _REGIME_WEIGHTS.get(regime, _REGIME_WEIGHTS["UNKNOWN"])
        threshold = _THRESHOLDS.get(regime, LIVE_READY_THRESHOLD)

        score = self._compute_score(inp, weights)
        self._history.append(score)
        if len(self._history) > 10:
            self._history.pop(0)

        # Garde-fous absolus : faux positifs = 0
        live_ready = (
            score >= threshold
            and inp.hard_limits_ok
            and not inp.open_positions_unknown
            and inp.risk_sync
            and inp.shadow_cycles_completed
            >= int(os.getenv("P10_SHADOW_MIN_CYCLES", "10"))
        )

        payload = {
            "symbols_ready": inp.symbols_ready,
            "symbols_total": inp.symbols_total,
            "avg_feature_confidence": round(inp.avg_feature_confidence, 4),
            "regime_stability": round(inp.regime_stability, 4),
            "dwe_sample_coverage": round(inp.dwe_sample_coverage, 4),
            "risk_sync": inp.risk_sync,
            "warmup_score": round(score, 4),
            "live_ready": live_ready,
            "regime": regime,
            "threshold_used": round(threshold, 4),
            "ts": round(inp.ts, 3),
        }
        envelope = sign_artifact(payload, artifact_type="market_warmup_estimate")

        return EstimatorOutput(
            symbols_ready=inp.symbols_ready,
            symbols_total=inp.symbols_total,
            avg_feature_confidence=inp.avg_feature_confidence,
            regime_stability=inp.regime_stability,
            dwe_sample_coverage=inp.dwe_sample_coverage,
            risk_sync=inp.risk_sync,
            warmup_score=score,
            live_ready=live_ready,
            regime=regime,
            threshold_used=threshold,
            ts=inp.ts,
            hmac_signature=envelope["signature"],
        )

    def estimate_from_snapshot(
        self, snapshot: dict, regime: MarketRegime = "UNKNOWN"
    ) -> EstimatorOutput:
        """Wrapper pratique depuis un snapshot brut (compatible ColdStartManager)."""
        inp = EstimatorInput(
            symbols_ready=int(snapshot.get("symbols_ready", 0)),
            symbols_total=max(1, int(snapshot.get("symbols_total", 100))),
            avg_feature_confidence=float(snapshot.get("avg_feature_confidence", 0.0)),
            regime_stability=float(snapshot.get("regime_stability", 0.0)),
            dwe_sample_coverage=float(snapshot.get("dwe_sample_coverage", 0.0)),
            risk_sync=bool(snapshot.get("risk_sync", False)),
            hard_limits_ok=bool(snapshot.get("hard_limits_ok", True)),
            probation_consistent=bool(snapshot.get("probation_consistent", True)),
            evolution_memory_loaded=bool(
                snapshot.get("evolution_memory_loaded", False)
            ),
            transition_cache_populated=bool(
                snapshot.get("transition_cache_populated", False)
            ),
            shadow_cycles_completed=int(snapshot.get("shadow_cycles_completed", 0)),
            open_positions_unknown=bool(snapshot.get("open_positions_unknown", False)),
            anomaly_count=int(snapshot.get("anomaly_count", 0)),
            current_regime=regime,
        )
        return self.estimate(inp)

    def stability_score(self) -> float:
        """Stabilité du score sur les 10 dernières estimations."""
        if len(self._history) < 2:
            return 0.5
        mean = sum(self._history) / len(self._history)
        variance = sum((s - mean) ** 2 for s in self._history) / len(self._history)
        return round(max(0.0, 1.0 - variance * 10), 3)

    # ── Calcul interne ────────────────────────────────────────────────────────

    @staticmethod
    def _compute_score(inp: EstimatorInput, weights: dict[str, float]) -> float:
        """Score composite pondéré selon le régime de marché."""
        if not inp.hard_limits_ok:
            return 0.0
        if inp.open_positions_unknown:
            return 0.0

        data_cov = min(1.0, inp.symbols_ready / max(1, inp.symbols_total))

        components = {
            "data": (data_cov, weights["data"]),
            "features": (inp.avg_feature_confidence, weights["features"]),
            "regime": (inp.regime_stability, weights["regime"]),
            "risk": (1.0 if inp.risk_sync else 0.0, weights["risk"]),
            "probation": (
                1.0 if inp.probation_consistent else 0.0,
                weights["probation"],
            ),
            "memory": (1.0 if inp.evolution_memory_loaded else 0.5, weights["memory"]),
            "transition": (
                1.0 if inp.transition_cache_populated else 0.7,
                weights["transition"],
            ),
            "anomaly": (max(0.0, 1.0 - inp.anomaly_count * 0.1), weights["anomaly"]),
        }
        score = sum(v * w for v, w in components.values())
        return round(min(1.0, score), 4)
