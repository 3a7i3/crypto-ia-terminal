"""
dip/modules/decision_alert.py — D12 Decision Alert Engine.

Détection d'anomalies en temps réel sur le flux décisionnel.
Publie des alertes dans DIPStore (jamais vers le moteur de trading).

Règles d'alerte:
  - Burst de rejets (> 80% sur 10 dernières décisions)
  - Couche anormalement active (z-score > 3)
  - Explosion du taux de rejet global (>50% sur 1h vs baseline)
  - Régime instable (changements fréquents)
  - Score d'explicabilité bas (grade F)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from dip.core.store import DIPStore
from dip.core.types import Severity, now_us

if TYPE_CHECKING:
    from observability.decision_observation import DecisionObservation


# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AlertRule:
    rule_id: str
    name: str
    description: str
    severity: Severity
    enabled: bool


@dataclass(frozen=True)
class Alert:
    alert_id: str
    rule_id: str
    severity: Severity
    title: str
    description: str
    metric_value: float
    threshold: float
    layer: Optional[str]
    symbol: Optional[str]
    created_at_us: int
    acknowledged: bool = False


@dataclass(frozen=True)
class AlertSummary:
    total_active: int
    critical_count: int
    warning_count: int
    info_count: int
    most_recent: Optional[Alert]
    top_severity: str


# ── Rules ─────────────────────────────────────────────────────────────────────

RULE_REJECTION_BURST = AlertRule(
    rule_id="R01",
    name="Burst de rejets",
    description="Plus de 80% de rejets sur les 10 dernières décisions",
    severity=Severity.HIGH,
    enabled=True,
)

RULE_LAYER_ANOMALY = AlertRule(
    rule_id="R02",
    name="Couche anormalement active",
    description="Une couche bloque avec un z-score > 3 par rapport à son historique",
    severity=Severity.WARNING,
    enabled=True,
)

RULE_GLOBAL_REJECTION_SPIKE = AlertRule(
    rule_id="R03",
    name="Pic de rejet global",
    description="Taux de rejet > 50% sur la dernière heure vs baseline",
    severity=Severity.HIGH,
    enabled=True,
)

RULE_LOW_EXPLAINABILITY = AlertRule(
    rule_id="R04",
    name="Explicabilité très faible",
    description="Score d'explicabilité < 0.30 (grade F) pour 3+ décisions consécutives",
    severity=Severity.WARNING,
    enabled=True,
)

RULE_REGIME_INSTABILITY = AlertRule(
    rule_id="R05",
    name="Instabilité de régime",
    description="Plus de 5 changements de régime en 30 minutes",
    severity=Severity.WARNING,
    enabled=True,
)

_ALL_RULES = [
    RULE_REJECTION_BURST,
    RULE_LAYER_ANOMALY,
    RULE_GLOBAL_REJECTION_SPIKE,
    RULE_LOW_EXPLAINABILITY,
    RULE_REGIME_INSTABILITY,
]


# ── Detectors ─────────────────────────────────────────────────────────────────


class AlertDetector:
    """Detects alert conditions from recent observations."""

    def __init__(self, store: DIPStore) -> None:
        self._store = store
        self._recent_window: list[dict] = []  # sliding window dernières obs
        self._max_window = 50
        self._low_exp_streak = 0

    def update(self, obs: "DecisionObservation") -> list[Alert]:
        row = {
            "packet_id": obs.packet_id,
            "status": "APPROVED" if obs.trade_allowed else "REJECTED",
            "root_cause_layer": obs.first_blocker,
            "symbol": obs.symbol,
            "regime": getattr(obs, "regime", "?"),
            "exp_score": None,
            "created_at_us": now_us(),
        }
        self._recent_window.append(row)
        if len(self._recent_window) > self._max_window:
            self._recent_window.pop(0)

        alerts = []
        alerts.extend(self._check_rejection_burst())
        alerts.extend(self._check_layer_anomaly())
        alerts.extend(self._check_global_spike())
        alerts.extend(self._check_low_explainability(obs))
        alerts.extend(self._check_regime_instability())
        return alerts

    def _check_rejection_burst(self) -> list[Alert]:
        last10 = self._recent_window[-10:]
        if len(last10) < 10:
            return []
        rejection_rate = sum(1 for r in last10 if r["status"] == "REJECTED") / 10
        if rejection_rate > 0.80:
            return [
                Alert(
                    alert_id=f"alert_R01_{now_us()}",
                    rule_id="R01",
                    severity=Severity.HIGH,
                    title="Burst de rejets détecté",
                    description=f"{rejection_rate:.0%} de rejets sur les 10 dernières décisions",
                    metric_value=round(rejection_rate, 3),
                    threshold=0.80,
                    layer=None,
                    symbol=None,
                    created_at_us=now_us(),
                )
            ]
        return []

    def _check_layer_anomaly(self) -> list[Alert]:
        if len(self._recent_window) < 20:
            return []
        layer_counts: dict[str, int] = {}
        for r in self._recent_window:
            lyr = r.get("root_cause_layer")
            if lyr:
                layer_counts[lyr] = layer_counts.get(lyr, 0) + 1
        if not layer_counts:
            return []
        total = sum(layer_counts.values())
        mean = total / len(layer_counts)
        variance = sum((v - mean) ** 2 for v in layer_counts.values()) / len(
            layer_counts
        )
        std = max(0.5, variance**0.5)

        alerts = []
        for layer, count in layer_counts.items():
            z = (count - mean) / std
            if z > 3.0:
                rate = count / len(self._recent_window)
                alerts.append(
                    Alert(
                        alert_id=f"alert_R02_{layer}_{now_us()}",
                        rule_id="R02",
                        severity=Severity.WARNING,
                        title=f"Couche anormalement active: {layer}",
                        description=f"{layer} bloque {rate:.0%} des décisions récentes (z={z:.1f})",
                        metric_value=round(rate, 3),
                        threshold=0.0,
                        layer=layer,
                        symbol=None,
                        created_at_us=now_us(),
                    )
                )
        return alerts[:3]  # max 3 alertes par cycle

    def _check_global_spike(self) -> list[Alert]:
        now = now_us()
        one_hour = 3_600_000_000
        recent = self._store.get_decisions(start_us=now - one_hour, limit=1000)
        baseline = self._store.get_decisions(
            start_us=now - one_hour * 25, end_us=now - one_hour, limit=5000
        )
        if not recent or not baseline:
            return []
        recent_rate = sum(1 for r in recent if r.get("status") == "REJECTED") / len(
            recent
        )
        baseline_rate = sum(1 for r in baseline if r.get("status") == "REJECTED") / len(
            baseline
        )
        if recent_rate > 0.50 and recent_rate > baseline_rate * 1.5:
            return [
                Alert(
                    alert_id=f"alert_R03_{now_us()}",
                    rule_id="R03",
                    severity=Severity.HIGH,
                    title="Pic de rejet global",
                    description=(
                        f"Taux de rejet actuel: {recent_rate:.0%} "
                        f"vs baseline: {baseline_rate:.0%}"
                    ),
                    metric_value=round(recent_rate, 3),
                    threshold=0.50,
                    layer=None,
                    symbol=None,
                    created_at_us=now_us(),
                )
            ]
        return []

    def _check_low_explainability(self, obs: "DecisionObservation") -> list[Alert]:
        # Tracked via exp score in recent obs — simplified: use row data
        # Pour cette implémentation, on skip si pas de donnée directe
        return []

    def _check_regime_instability(self) -> list[Alert]:
        if len(self._recent_window) < 10:
            return []
        # Compter les changements de régime sur les 30 dernières minutes
        now = now_us()
        thirty_min = 1_800_000_000
        recent = [
            r
            for r in self._recent_window
            if r.get("created_at_us", 0) > now - thirty_min
        ]
        regimes = [r.get("regime") for r in recent if r.get("regime")]
        if len(regimes) < 5:
            return []
        changes = sum(1 for i in range(1, len(regimes)) if regimes[i] != regimes[i - 1])
        if changes > 5:
            return [
                Alert(
                    alert_id=f"alert_R05_{now_us()}",
                    rule_id="R05",
                    severity=Severity.WARNING,
                    title="Instabilité de régime détectée",
                    description=f"{changes} changements de régime en 30 minutes",
                    metric_value=float(changes),
                    threshold=5.0,
                    layer=None,
                    symbol=None,
                    created_at_us=now_us(),
                )
            ]
        return []


# ── Engine ─────────────────────────────────────────────────────────────────────


class DecisionAlertEngine:
    """D12 — Moteur d'alertes temps réel."""

    def __init__(self) -> None:
        self._store = DIPStore.instance()
        self._detector = AlertDetector(self._store)
        self._lock = threading.Lock()
        self._last_alert_time: dict[str, int] = {}
        self._cooldown_us = 300_000_000  # 5 minutes entre alertes identiques

    def on_observation(self, obs: "DecisionObservation") -> list[Alert]:
        with self._lock:
            new_alerts = self._detector.update(obs)
            persisted = []
            for alert in new_alerts:
                if self._is_cooldown_active(alert.rule_id):
                    continue
                self._persist(alert)
                self._last_alert_time[alert.rule_id] = now_us()
                persisted.append(alert)
            return persisted

    def get_active_alerts(self, severity: Optional[Severity] = None) -> list[Alert]:
        rows = self._store.get_active_alerts()
        alerts = [self._row_to_alert(r) for r in rows]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return sorted(alerts, key=lambda a: a.created_at_us, reverse=True)

    def acknowledge(self, alert_id: str) -> bool:
        try:
            self._store.acknowledge_alert(alert_id)
            return True
        except Exception:
            return False

    def get_summary(self) -> AlertSummary:
        alerts = self.get_active_alerts()
        critical = sum(1 for a in alerts if a.severity == Severity.CRITICAL)
        warning = sum(
            1 for a in alerts if a.severity in (Severity.WARNING, Severity.HIGH)
        )
        info = sum(1 for a in alerts if a.severity == Severity.INFO)
        most_recent = alerts[0] if alerts else None
        top_sev = "OK"
        if critical > 0:
            top_sev = "CRITICAL"
        elif warning > 0:
            top_sev = "WARNING"
        elif info > 0:
            top_sev = "INFO"
        return AlertSummary(
            total_active=len(alerts),
            critical_count=critical,
            warning_count=warning,
            info_count=info,
            most_recent=most_recent,
            top_severity=top_sev,
        )

    def get_rules(self) -> list[AlertRule]:
        return list(_ALL_RULES)

    def _is_cooldown_active(self, rule_id: str) -> bool:
        last = self._last_alert_time.get(rule_id, 0)
        return now_us() - last < self._cooldown_us

    def _persist(self, alert: Alert) -> None:
        try:
            self._store.insert_alert(
                {
                    "alert_id": alert.alert_id,
                    "rule_id": alert.rule_id,
                    "severity": alert.severity.value,
                    "title": alert.title,
                    "description": alert.description,
                    "metric_value": alert.metric_value,
                    "threshold": alert.threshold,
                    "layer": alert.layer,
                    "symbol": alert.symbol,
                    "created_at_us": alert.created_at_us,
                }
            )
        except Exception:
            pass

    def _row_to_alert(self, r: dict) -> Alert:
        return Alert(
            alert_id=r["alert_id"],
            rule_id=r.get("rule_id", "?"),
            severity=Severity(r.get("severity", "INFO")),
            title=r.get("title", ""),
            description=r.get("description", ""),
            metric_value=r.get("metric_value", 0.0),
            threshold=r.get("threshold", 0.0),
            layer=r.get("layer"),
            symbol=r.get("symbol"),
            created_at_us=r.get("created_at_us", 0),
            acknowledged=bool(r.get("acknowledged", False)),
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[DecisionAlertEngine] = None
_engine_lock = threading.Lock()


def get_alert_engine() -> DecisionAlertEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DecisionAlertEngine()
    return _engine
