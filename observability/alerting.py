"""
alerting.py — Moteur d'alertes sur seuils (P12-B).

Évalue un MetricsSnapshot contre des règles configurables.
Les alertes déclenchées sont :
  - loguées (json_logger)
  - appendées à un fichier JSONL (optionnel)
  - retournées pour consommation par l'appelant

Règles par défaut :
  DRAWDOWN      : drawdown_pct > 10%
  MEMORY        : memory_mb   > 800 MB
  ERROR_RATE    : error_rate  > 3 err/min
  RECONCILE     : reconciliation_failures >= 1
  BOOT_BLOCKED  : boot_gate_cleared == False
  HIGH_LATENCY  : cycle_duration_ms > 2000 ms
  EXCEPTION     : exception_count > 5

Usage :
    engine = AlertEngine()
    fired = engine.check(snapshot)
    for alert in fired:
        print(alert.rule, alert.severity, alert.message)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from observability.json_logger import get_logger
from observability.metrics_collector import MetricsSnapshot

_log = get_logger("observability.alerting")

_DEFAULT_ALERT_PATH = Path(os.getenv("P12_ALERT_PATH", "cache/startup/alerts.jsonl"))


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class Alert:
    rule: str
    severity: AlertSeverity
    message: str
    value: float
    threshold: float
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class AlertRule:
    name: str
    severity: AlertSeverity
    condition: Callable[[MetricsSnapshot], bool]
    message_fn: Callable[[MetricsSnapshot], str]
    value_fn: Callable[[MetricsSnapshot], float]
    threshold: float
    enabled: bool = True


class AlertEngine:
    """
    Évalue un snapshot contre un ensemble de règles d'alerte.

    Peut persister les alertes déclenchées en JSONL.
    """

    def __init__(
        self,
        alert_path: Optional[Path] = None,
        persist: bool = False,
        extra_rules: Optional[list[AlertRule]] = None,
    ) -> None:
        self._path = alert_path or _DEFAULT_ALERT_PATH
        self._persist = persist
        self._rules = _DEFAULT_RULES + (extra_rules or [])
        self._fired_count: int = 0

    # ── API publique ─────────────────────────────────────────────────────────

    def check(self, snap: MetricsSnapshot) -> list[Alert]:
        """
        Évalue le snapshot contre toutes les règles actives.
        Retourne les alertes déclenchées, les persiste si persist=True.
        """
        fired: list[Alert] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            try:
                if rule.condition(snap):
                    alert = Alert(
                        rule=rule.name,
                        severity=rule.severity,
                        message=rule.message_fn(snap),
                        value=rule.value_fn(snap),
                        threshold=rule.threshold,
                    )
                    fired.append(alert)
                    self._log_alert(alert)
                    self._fired_count += 1
            except Exception as exc:
                _log.warning(
                    "[AlertEngine] Erreur évaluation règle %s: %s", rule.name, exc
                )

        if fired and self._persist:
            self._write_to_jsonl(fired)

        return fired

    def add_rule(self, rule: AlertRule) -> None:
        self._rules.append(rule)

    def enable_rule(self, name: str) -> None:
        for r in self._rules:
            if r.name == name:
                r.enabled = True

    def disable_rule(self, name: str) -> None:
        for r in self._rules:
            if r.name == name:
                r.enabled = False

    def total_fired(self) -> int:
        return self._fired_count

    def rule_names(self) -> list[str]:
        return [r.name for r in self._rules]

    # ── Internals ────────────────────────────────────────────────────────────

    def _log_alert(self, alert: Alert) -> None:
        if alert.severity == AlertSeverity.CRITICAL:
            _log.error(
                "[ALERT][%s] %s (val=%.2f seuil=%.2f)",
                alert.rule,
                alert.message,
                alert.value,
                alert.threshold,
            )
        else:
            _log.warning(
                "[ALERT][%s] %s (val=%.2f seuil=%.2f)",
                alert.rule,
                alert.message,
                alert.value,
                alert.threshold,
            )

    def _write_to_jsonl(self, alerts: list[Alert]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                for a in alerts:
                    f.write(json.dumps(a.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:
            _log.warning("[AlertEngine] Écriture JSONL échouée: %s", exc)


# ── Règles par défaut ─────────────────────────────────────────────────────────

_DRAWDOWN_THRESHOLD = 10.0
_MEMORY_THRESHOLD_MB = 800.0
_ERROR_RATE_THRESHOLD = 3.0
_RECONCILE_THRESHOLD = 1
_LATENCY_THRESHOLD_MS = 2_000.0
_EXCEPTION_THRESHOLD = 5

_DEFAULT_RULES: list[AlertRule] = [
    AlertRule(
        name="DRAWDOWN",
        severity=AlertSeverity.CRITICAL,
        condition=lambda s: s.drawdown_pct > _DRAWDOWN_THRESHOLD,
        message_fn=lambda s: f"Drawdown critique: {s.drawdown_pct:.1f}%",
        value_fn=lambda s: s.drawdown_pct,
        threshold=_DRAWDOWN_THRESHOLD,
    ),
    AlertRule(
        name="MEMORY",
        severity=AlertSeverity.WARNING,
        condition=lambda s: s.memory_mb > _MEMORY_THRESHOLD_MB,
        message_fn=lambda s: f"Mémoire élevée: {s.memory_mb:.0f} MB",
        value_fn=lambda s: s.memory_mb,
        threshold=_MEMORY_THRESHOLD_MB,
    ),
    AlertRule(
        name="ERROR_RATE",
        severity=AlertSeverity.WARNING,
        condition=lambda s: s.error_rate > _ERROR_RATE_THRESHOLD,
        message_fn=lambda s: f"Taux d'erreur: {s.error_rate:.2f} err/min",
        value_fn=lambda s: s.error_rate,
        threshold=_ERROR_RATE_THRESHOLD,
    ),
    AlertRule(
        name="RECONCILE_FAILURE",
        severity=AlertSeverity.CRITICAL,
        condition=lambda s: s.reconciliation_failures >= _RECONCILE_THRESHOLD,
        message_fn=lambda s: f"Échecs reconciliation: {s.reconciliation_failures}",
        value_fn=lambda s: float(s.reconciliation_failures),
        threshold=float(_RECONCILE_THRESHOLD),
    ),
    AlertRule(
        name="BOOT_BLOCKED",
        severity=AlertSeverity.CRITICAL,
        condition=lambda s: not s.boot_gate_cleared,
        message_fn=lambda s: "Boot gate non levé — trading bloqué",
        value_fn=lambda s: 0.0,
        threshold=1.0,
    ),
    AlertRule(
        name="HIGH_LATENCY",
        severity=AlertSeverity.WARNING,
        condition=lambda s: s.cycle_duration_ms > _LATENCY_THRESHOLD_MS,
        message_fn=lambda s: f"Cycle lent: {s.cycle_duration_ms:.0f} ms",
        value_fn=lambda s: s.cycle_duration_ms,
        threshold=_LATENCY_THRESHOLD_MS,
    ),
    AlertRule(
        name="EXCEPTION_COUNT",
        severity=AlertSeverity.WARNING,
        condition=lambda s: s.exception_count > _EXCEPTION_THRESHOLD,
        message_fn=lambda s: f"Exceptions: {s.exception_count}",
        value_fn=lambda s: float(s.exception_count),
        threshold=float(_EXCEPTION_THRESHOLD),
    ),
]
