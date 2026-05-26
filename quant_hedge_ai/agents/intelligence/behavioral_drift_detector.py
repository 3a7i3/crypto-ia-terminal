"""
behavioral_drift_detector.py — Behavioral Drift Detector (P9)

Détecte statistiquement quand le système dévie de son comportement attendu.

4 métriques surveillées :
  threshold_avg   : seuil moyen sur fenêtre glissante
  activity_rate   : fraction des cycles avec un trade exécuté
  score_mean      : score moyen des signaux générés
  refusal_rate    : fraction des signaux refusés

Dérive = métrique actuelle > 2σ de sa moyenne historique (baseline).
Les seuils sont ajustés par régime (HIGH_VOL/CHOPPY = ×1.5 plus tolérant).

Propriétés :
  - meta_confidence : fiabilité du détecteur [0.1, 1.0] selon historique
  - governance_cooldown : silence N cycles après une alerte (anti-spam)
"""

from __future__ import annotations

import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.intelligence.behavioral_drift_detector")

# Régimes avec tolérance augmentée
_LOOSE_REGIMES = {"HIGH_VOL", "CHOPPY", "high_volatility_regime", "choppy"}
_LOOSE_MULTIPLIER = 1.5

_BASELINE_WINDOW_DEFAULT = 50
_SIGMA_THRESHOLD_DEFAULT = 2.0
_COOLDOWN_CYCLES_DEFAULT = 10
_MIN_WINDOW_CONFIDENCE = 20  # fenêtre minimum pour confiance > 0.1


@dataclass
class DriftMetric:
    name: str
    current: float
    baseline_mean: float
    baseline_std: float
    sigma_distance: float
    drifting: bool


@dataclass
class DriftReport:
    cycle: int
    regime: str
    drifting: bool
    drifting_metrics: List[str]
    metrics: List[DriftMetric]
    meta_confidence: float  # 0.1 → 1.0 selon taille fenêtre
    cooldown_active: bool
    ts: float = field(default_factory=time.time)


class BehavioralDriftDetector:
    """
    Détecteur de dérive comportementale statistique.

    Usage :
        bdd = BehavioralDriftDetector()
        bdd.record(cycle=1, threshold_used=68, score=72, signal_generated=True,
                   refused=False, regime="sideways")
        report = bdd.check(regime="sideways")
        if report.drifting:
            log.warning("Dérive détectée : %s", report.drifting_metrics)
    """

    def __init__(self) -> None:
        w = int(os.getenv("P9_DRIFT_WINDOW", str(_BASELINE_WINDOW_DEFAULT)))
        self._sigma_threshold = float(
            os.getenv("P9_DRIFT_SIGMA", str(_SIGMA_THRESHOLD_DEFAULT))
        )
        self._cooldown_cycles = int(
            os.getenv("P9_DRIFT_COOLDOWN", str(_COOLDOWN_CYCLES_DEFAULT))
        )
        self._min_confidence_window = int(
            os.getenv("P9_DRIFT_MIN_WINDOW", str(_MIN_WINDOW_CONFIDENCE))
        )

        self._thresholds: Deque[float] = deque(maxlen=w)
        self._activity_flags: Deque[int] = deque(maxlen=w)
        self._scores: Deque[float] = deque(maxlen=w)
        self._refusal_flags: Deque[int] = deque(maxlen=w)

        self._cycle_count: int = 0
        self._last_alert_cycle: int = -9999
        self._alert_count: int = 0
        self._last_report: Optional[DriftReport] = None

    # ── Enregistrement ────────────────────────────────────────────────────────

    def record(
        self,
        cycle: int,
        threshold_used: float,
        score: float = 0.0,
        signal_generated: bool = False,
        refused: bool = False,
        regime: str = "unknown",
    ) -> None:
        """Enregistre les métriques d'un cycle. Appelé chaque cycle."""
        self._cycle_count += 1
        self._thresholds.append(float(threshold_used))
        self._activity_flags.append(1 if signal_generated and not refused else 0)
        if signal_generated:
            self._scores.append(float(score))
        self._refusal_flags.append(1 if (signal_generated and refused) else 0)

    # ── Détection ────────────────────────────────────────────────────────────

    def check(self, regime: str = "unknown") -> DriftReport:
        """
        Vérifie si une dérive est détectée sur les métriques actuelles.
        Retourne DriftReport (cooldown_active=True si dans la période de silence).
        """
        cooldown_active = (
            self._cycle_count - self._last_alert_cycle
        ) < self._cooldown_cycles

        sigma_mult = _LOOSE_MULTIPLIER if regime in _LOOSE_REGIMES else 1.0
        effective_sigma = self._sigma_threshold * sigma_mult

        metrics: List[DriftMetric] = []
        drifting_names: List[str] = []

        for name, window in [
            ("threshold_avg", self._thresholds),
            ("activity_rate", self._activity_flags),
            ("score_mean", self._scores),
            ("refusal_rate", self._refusal_flags),
        ]:
            dm = self._check_metric(name, list(window), effective_sigma)
            metrics.append(dm)
            if dm.drifting and not cooldown_active:
                drifting_names.append(name)

        is_drifting = bool(drifting_names)
        if is_drifting:
            self._last_alert_cycle = self._cycle_count
            self._alert_count += 1
            _log.warning(
                "[P9/Drift] Dérive détectée cycle=%d régime=%s métriques=%s "
                "confiance=%.2f",
                self._cycle_count,
                regime,
                drifting_names,
                self._meta_confidence(),
            )

        report = DriftReport(
            cycle=self._cycle_count,
            regime=regime,
            drifting=is_drifting,
            drifting_metrics=drifting_names,
            metrics=metrics,
            meta_confidence=self._meta_confidence(),
            cooldown_active=cooldown_active,
        )
        self._last_report = report
        return report

    # ── Propriétés ────────────────────────────────────────────────────────────

    @property
    def alert_count(self) -> int:
        return self._alert_count

    @property
    def last_report(self) -> Optional[DriftReport]:
        return self._last_report

    @property
    def alert_frequency(self) -> float:
        """Alertes par 10 cycles (pour Self-Monitoring Loop)."""
        if self._cycle_count < 10:
            return 0.0
        return self._alert_count / (self._cycle_count / 10)

    # ── Helpers privés ────────────────────────────────────────────────────────

    def _check_metric(
        self, name: str, window: list, effective_sigma: float
    ) -> DriftMetric:
        if len(window) < 3:
            return DriftMetric(
                name=name,
                current=0.0,
                baseline_mean=0.0,
                baseline_std=0.0,
                sigma_distance=0.0,
                drifting=False,
            )
        # baseline = toute la fenêtre sauf les 5 derniers points
        baseline = window[:-5] if len(window) > 10 else window
        recent = window[-5:] if len(window) > 5 else window[-1:]

        mean_b = sum(baseline) / len(baseline)
        std_b = math.sqrt(sum((x - mean_b) ** 2 for x in baseline) / len(baseline))
        current = sum(recent) / len(recent)
        sigma_dist = abs(current - mean_b) / (std_b + 1e-8)

        return DriftMetric(
            name=name,
            current=round(current, 4),
            baseline_mean=round(mean_b, 4),
            baseline_std=round(std_b, 4),
            sigma_distance=round(sigma_dist, 3),
            drifting=sigma_dist > effective_sigma,
        )

    def _meta_confidence(self) -> float:
        """
        Confiance du détecteur en ses propres alertes.
        Croît linéairement de 0.1 (window vide) à 1.0 (window pleine).
        """
        n = len(self._thresholds)
        if n < self._min_confidence_window:
            return 0.1 + 0.9 * (n / self._min_confidence_window)
        return 1.0

    def snapshot(self) -> dict:
        return {
            "cycle_count": self._cycle_count,
            "alert_count": self._alert_count,
            "alert_frequency_per_10c": round(self.alert_frequency, 3),
            "meta_confidence": round(self._meta_confidence(), 3),
            "cooldown_remaining": max(
                0,
                self._cooldown_cycles - (self._cycle_count - self._last_alert_cycle),
            ),
        }
