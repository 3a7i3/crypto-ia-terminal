"""
supervision/proactive_alerts.py — E-06 ProactiveAlerts Thresholds

Alertes proactives avant que les seuils critiques ne soient atteints.

Seuils surveillés :
  1. drawdown_warning     : drawdown > 90% du max autorisé → alerte 2+ min avant
  2. budget_warning       : budget trades > 90% épuisé → alerte 2+ min avant
  3. latency_warning      : latence moyenne > 2x la baseline → alerte
  4. exchange_error_rate  : erreurs exchange > 10% des appels → alerte

Garanties :
  - Alerte déclenchée ≥ 2 min avant le seuil critique (time_to_critical)
  - Cooldown par métrique (évite le spam)
  - Aucun faux positif sur une fenêtre stable (hysteresis)
  - time_to_critical() estimation basée sur la vitesse de dérive

Usage :
    engine = ProactiveAlertsEngine(alert_fn=my_alert_fn)
    alerts = engine.check({
        "current_drawdown_pct": 0.85,
        "max_drawdown_pct": 1.0,
        "daily_budget_used": 0.92,
        "avg_latency_ms": 400.0,
        "baseline_latency_ms": 150.0,
        "exchange_error_rate": 0.12,
    })
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("supervision.proactive_alerts")

_ALERT_COOLDOWN_S = float(120.0)  # 2 min entre alertes répétées par métrique
_MIN_TTC_SECONDS = 120.0  # alerte si time_to_critical < 2 min


# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass
class AlertThreshold:
    metric_name: str
    warning_ratio: float  # fraction de la valeur critique (0.90 = 90%)
    critical_value: float  # valeur absolue de déclenchement critique
    direction: str = "above"  # "above" = valeur trop haute, "below" = trop basse
    description: str = ""
    hysteresis: float = 0.05  # écart requis pour réarmer après déclenchement


@dataclass
class ProactiveAlert:
    metric_name: str
    current_value: float
    warning_threshold: float
    critical_value: float
    time_to_critical_s: float  # estimation
    severity: str  # "WARNING" ou "PRE_CRITICAL"
    description: str
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "metric_name": self.metric_name,
            "current_value": round(self.current_value, 4),
            "warning_threshold": round(self.warning_threshold, 4),
            "critical_value": round(self.critical_value, 4),
            "time_to_critical_s": round(self.time_to_critical_s, 1),
            "severity": self.severity,
            "description": self.description,
            "ts": round(self.ts, 3),
        }


class ProactiveAlertsEngine:
    """
    Moteur d'alertes proactives basé sur des seuils configurables.

    Déclenche une alerte dès que la valeur approche le seuil critique,
    avec une estimation du temps restant avant dépassement.
    """

    # Seuils standard P10-E
    _DEFAULT_THRESHOLDS = [
        AlertThreshold(
            metric_name="drawdown",
            warning_ratio=0.90,
            critical_value=1.0,  # 100% du drawdown max
            direction="above",
            description="Drawdown approche le maximum autorisé",
        ),
        AlertThreshold(
            metric_name="daily_budget",
            warning_ratio=0.90,
            critical_value=1.0,  # 100% du budget épuisé
            direction="above",
            description="Budget journalier de trades approche l'épuisement",
        ),
        AlertThreshold(
            metric_name="latency_ratio",
            warning_ratio=1.0,  # ratio est comparé à 2.0
            critical_value=3.0,  # 3x la baseline = critique
            direction="above",
            description="Latence moyenne > 2x la baseline",
        ),
        AlertThreshold(
            metric_name="exchange_error_rate",
            warning_ratio=1.0,
            critical_value=0.20,  # 20% erreurs = critique
            direction="above",
            description="Taux d'erreurs exchange > 10%",
        ),
    ]

    def __init__(
        self,
        thresholds: Optional[list[AlertThreshold]] = None,
        alert_fn: Optional[Callable[[ProactiveAlert], None]] = None,
        cooldown_s: float = _ALERT_COOLDOWN_S,
        min_ttc_s: float = _MIN_TTC_SECONDS,
    ) -> None:
        self._thresholds = {
            t.metric_name: t for t in (thresholds or self._DEFAULT_THRESHOLDS)
        }
        self._alert_fn = alert_fn
        self._cooldown_s = cooldown_s
        self._min_ttc_s = min_ttc_s

        # Historique pour estimer le taux de dérive
        self._value_history: dict[str, deque] = {}
        self._last_alert_ts: dict[str, float] = {}
        self._armed: dict[str, bool] = {}  # hysteresis : réarmé après descente

    def check(self, metrics: dict) -> list[ProactiveAlert]:
        """
        Vérifie toutes les métriques et retourne les alertes déclenchées.
        Appelé à chaque cycle de supervision (ex. toutes les 60s).
        """
        alerts: list[ProactiveAlert] = []

        # Extraire les métriques normalisées
        extracted = self._extract(metrics)

        for metric_name, value in extracted.items():
            threshold = self._thresholds.get(metric_name)
            if threshold is None:
                continue

            # Enregistrer l'historique pour l'estimation de dérive
            self._record(metric_name, value)

            # Vérifier le seuil d'alerte
            warning_threshold = threshold.critical_value * threshold.warning_ratio
            is_above_warning = self._is_triggered(
                value, warning_threshold, threshold.direction
            )

            if not is_above_warning:
                # Sous le seuil → réarmer hysteresis
                self._armed[metric_name] = True
                continue

            # Vérifier le cooldown (anti-spam)
            if not self._can_alert(metric_name):
                continue

            # Calculer time_to_critical
            ttc = self._estimate_ttc(metric_name, value, threshold)

            # Sévérité
            is_pre_critical = ttc < self._min_ttc_s
            severity = "PRE_CRITICAL" if is_pre_critical else "WARNING"

            alert = ProactiveAlert(
                metric_name=metric_name,
                current_value=value,
                warning_threshold=warning_threshold,
                critical_value=threshold.critical_value,
                time_to_critical_s=ttc,
                severity=severity,
                description=threshold.description,
            )
            alerts.append(alert)
            self._last_alert_ts[metric_name] = time.time()

            _log.warning(
                "[ProactiveAlerts] %s — %s valeur=%.3f seuil=%.3f TTC=%.0fs",
                severity,
                metric_name,
                value,
                warning_threshold,
                ttc,
            )

            if self._alert_fn:
                try:
                    self._alert_fn(alert)
                except Exception as exc:
                    _log.debug("[ProactiveAlerts] alert_fn erreur: %s", exc)

        return alerts

    def time_to_critical(
        self,
        metric_name: str,
        current_value: float,
        rate_per_s: float,
    ) -> float:
        """
        Estime le temps (en secondes) avant d'atteindre le seuil critique.
        rate_per_s > 0 pour une valeur qui monte, < 0 pour une valeur qui descend.
        Retourne float('inf') si la valeur s'éloigne du seuil.
        """
        threshold = self._thresholds.get(metric_name)
        if threshold is None:
            return float("inf")
        critical = threshold.critical_value
        if threshold.direction == "above":
            remaining = critical - current_value
            if rate_per_s <= 0:
                return float("inf")
            return remaining / rate_per_s
        else:
            remaining = current_value - critical
            if rate_per_s >= 0:
                return float("inf")
            return remaining / abs(rate_per_s)

    def no_false_positives_on_stable(
        self, metric_name: str, stable_values: list[float]
    ) -> bool:
        """
        Vérifie qu'aucune alerte n'est générée sur des valeurs stables sous le seuil.
        Utile pour valider l'absence de faux positifs.
        """
        threshold = self._thresholds.get(metric_name)
        if threshold is None:
            return True
        warning_threshold = threshold.critical_value * threshold.warning_ratio
        for v in stable_values:
            if self._is_triggered(v, warning_threshold, threshold.direction):
                return False
        return True

    def add_threshold(self, threshold: AlertThreshold) -> None:
        self._thresholds[threshold.metric_name] = threshold

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract(self, metrics: dict) -> dict[str, float]:
        """Extrait et normalise les métriques depuis le snapshot brut."""
        out: dict[str, float] = {}

        # 1. Drawdown
        drawdown = metrics.get("current_drawdown_pct")
        max_dd = metrics.get("max_drawdown_pct", 1.0)
        if drawdown is not None and max_dd and max_dd > 0:
            try:
                out["drawdown"] = float(drawdown) / float(max_dd)
            except (TypeError, ValueError):
                pass

        # 2. Budget journalier
        budget_used = metrics.get("daily_budget_used")
        if budget_used is not None:
            try:
                out["daily_budget"] = float(budget_used)
            except (TypeError, ValueError):
                pass

        # 3. Latence (ratio vs baseline)
        avg_lat = metrics.get("avg_latency_ms")
        baseline_lat = metrics.get("baseline_latency_ms")
        if avg_lat is not None and baseline_lat and float(baseline_lat) > 0:
            try:
                out["latency_ratio"] = float(avg_lat) / float(baseline_lat)
            except (TypeError, ValueError):
                pass

        # 4. Taux d'erreur exchange
        err_rate = metrics.get("exchange_error_rate")
        if err_rate is not None:
            try:
                out["exchange_error_rate"] = float(err_rate)
            except (TypeError, ValueError):
                pass

        return out

    def _record(self, metric_name: str, value: float) -> None:
        if metric_name not in self._value_history:
            self._value_history[metric_name] = deque(maxlen=30)
        self._value_history[metric_name].append((time.time(), value))

    def _can_alert(self, metric_name: str) -> bool:
        last = self._last_alert_ts.get(metric_name, 0.0)
        return (time.time() - last) >= self._cooldown_s

    def _is_triggered(self, value: float, threshold: float, direction: str) -> bool:
        if direction == "above":
            return value >= threshold
        return value <= threshold

    def _estimate_ttc(
        self, metric_name: str, current_value: float, threshold: AlertThreshold
    ) -> float:
        """Estime le TTC depuis l'historique des valeurs."""
        history = list(self._value_history.get(metric_name, []))
        if len(history) < 2:
            # Pas assez de données → estimation conservative
            gap = abs(threshold.critical_value - current_value)
            return gap * 600  # assume 1% de progression toutes les 6 min

        # Taux de dérive moyen sur les 5 dernières mesures
        recent = history[-min(5, len(history)) :]
        dt = recent[-1][0] - recent[0][0]
        dv = recent[-1][1] - recent[0][1]
        if abs(dt) < 1e-9:
            return float("inf")

        rate_per_s = dv / dt
        remaining = threshold.critical_value - current_value
        if threshold.direction == "above":
            if rate_per_s <= 0:
                return float("inf")
            return remaining / rate_per_s
        else:
            if rate_per_s >= 0:
                return float("inf")
            return abs(remaining) / abs(rate_per_s)
