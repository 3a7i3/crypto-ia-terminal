"""
model_degradation_monitor.py — Model Health & Degradation Detection

Surveille en continu la performance de chaque composant (régime, signal,
arbitration) et déclenche des alertes si dégradation détectée.
Évite que des modèles stale continuent de prendre des décisions.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DegradationAlert:
    component: str
    alert_type: str  # "accuracy_drop", "drift", "stale", "regime_mismatch"
    severity: str  # "info", "warning", "critical"
    current_score: float
    baseline_score: float
    degradation_pct: float
    message: str
    timestamp: float = field(default_factory=time.time)
    auto_action: str = ""  # "retrain", "disable", "alert_only"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class ModelDegradationMonitor:
    """
    Monitore la santé de chaque composant du pipeline de décision.

    Métriques surveillées :
    - Win rate glissant (fenêtre 50 trades)
    - Précision de la prédiction de régime
    - Erreur de slippage (prédit vs réel)
    - Staleness (âge du dernier entraînement)
    """

    DEGRADATION_THRESHOLD = 0.20  # alerte si performance baisse de 20%
    CRITICAL_THRESHOLD = 0.40  # critique si baisse de 40%
    MIN_SAMPLES = 20

    def __init__(self) -> None:
        self._metrics: dict[str, deque] = {}
        self._baselines: dict[str, float] = {}
        self._alerts: list[DegradationAlert] = []
        self._last_update: dict[str, float] = {}

    # ------------------------------------------------------------------
    # API principale
    # ------------------------------------------------------------------

    def record(self, component: str, metric_name: str, value: float) -> None:
        key = f"{component}:{metric_name}"
        if key not in self._metrics:
            self._metrics[key] = deque(maxlen=200)
        self._metrics[key].append(value)
        self._last_update[key] = time.time()
        self._check_degradation(component, metric_name, key)

    def record_trade_result(self, component: str, was_correct: bool) -> None:
        self.record(component, "accuracy", 1.0 if was_correct else 0.0)

    def record_regime_prediction(self, predicted: str, actual: str) -> None:
        correct = 1.0 if predicted == actual else 0.0
        self.record("hmm_regime", "accuracy", correct)

    def record_slippage(self, predicted_bps: float, actual_bps: float) -> None:
        error = abs(actual_bps - predicted_bps)
        self.record("slippage_predictor", "mae", error)

    def check_staleness(self, component: str, max_age_hours: float = 24.0) -> bool:
        key = f"{component}:accuracy"
        last = self._last_update.get(key, 0.0)
        age_hours = (time.time() - last) / 3600.0
        if age_hours > max_age_hours and last > 0:
            self._emit_alert(
                component,
                "stale",
                "info",
                1.0,
                1.0,
                0.0,
                f"{component} sans mise à jour depuis {age_hours:.1f}h",
                "alert_only",
            )
            return True
        return False

    def health_report(self) -> dict[str, Any]:
        report = {}
        for key, metrics in self._metrics.items():
            if len(metrics) < 5:
                continue
            vals = list(metrics)
            report[key] = {
                "mean": sum(vals) / len(vals),
                "recent_mean": sum(vals[-20:]) / min(len(vals), 20),
                "n_samples": len(vals),
                "trend": vals[-1] - vals[-min(10, len(vals))],
            }
        return report

    def active_alerts(self, severity: str | None = None) -> list[DegradationAlert]:
        if severity:
            return [a for a in self._alerts if a.severity == severity]
        return list(self._alerts)

    def clear_alerts(self) -> None:
        self._alerts.clear()

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _check_degradation(self, component: str, metric_name: str, key: str) -> None:
        vals = list(self._metrics[key])
        if len(vals) < self.MIN_SAMPLES:
            return

        # Établir baseline sur les premiers 50% des samples
        mid = len(vals) // 2
        baseline = sum(vals[:mid]) / mid
        recent = sum(vals[-min(20, len(vals)) :]) / min(20, len(vals))

        if baseline == 0:
            return

        # Pour MAE (erreur) : dégradation si ça augmente
        is_error_metric = metric_name in ("mae", "error", "slippage_error")
        if is_error_metric:
            degradation = (recent - baseline) / baseline
        else:
            degradation = (baseline - recent) / baseline

        if degradation <= 0:
            return

        if key not in self._baselines:
            self._baselines[key] = baseline

        severity = "info"
        action = "alert_only"
        if degradation >= self.CRITICAL_THRESHOLD:
            severity = "critical"
            action = "retrain"
        elif degradation >= self.DEGRADATION_THRESHOLD:
            severity = "warning"
            action = "alert_only"
        else:
            return

        self._emit_alert(
            component,
            "accuracy_drop",
            severity,
            recent,
            baseline,
            degradation,
            f"{component}/{metric_name}: dégradation {degradation:.0%} (baseline={baseline:.3f}, recent={recent:.3f})",
            action,
        )

    def _emit_alert(
        self,
        component: str,
        alert_type: str,
        severity: str,
        current: float,
        baseline: float,
        degradation: float,
        message: str,
        action: str,
    ) -> None:
        alert = DegradationAlert(
            component=component,
            alert_type=alert_type,
            severity=severity,
            current_score=current,
            baseline_score=baseline,
            degradation_pct=degradation,
            message=message,
            auto_action=action,
        )
        self._alerts.append(alert)
        level = (
            logging.CRITICAL
            if severity == "critical"
            else logging.WARNING if severity == "warning" else logging.INFO
        )
        logger.log(level, "[DegradationMonitor] %s: %s", severity.upper(), message)
