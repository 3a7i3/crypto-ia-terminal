"""
alert_manager.py — Gestion centralisée des alertes et auto-heal

Note: fichier restauré minimalement pour compatibilité d'import:
`from supervision.alert_manager import Alert, AlertManager`
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional


class Alert:
    def __init__(
        self,
        type_: str,
        severity: str,
        module: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.type = type_
        self.severity = severity  # info, warning, critical
        self.module = module
        self.message = message
        self.context = context or {}
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "module": self.module,
            "message": self.message,
            "context": self.context,
            "timestamp": self.timestamp,
        }


class AlertManager:
    def __init__(self, audit_file: str = "alerts_audit.jsonl"):
        self.alerts: List[Alert] = []
        self.autoheal_registry: Dict[str, Any] = {}
        self.audit_file = audit_file

    def raise_alert(self, alert: Alert) -> None:
        self.alerts.append(alert)
        with open(self.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(alert.to_dict()) + "\n")
        self._emit_event(alert)
        if alert.severity == "critical" and alert.module in self.autoheal_registry:
            self.run_autoheal(alert)

    def _emit_event(self, alert: Alert) -> None:
        """Émet l'alerte sur l'EventBus global — silencieux si non dispo."""
        try:
            from event_bus.bus import EventBus
            from event_bus.events import DrawdownAlertEvent, SecurityAlertEvent

            if alert.type == "drawdown":
                EventBus.get().emit(
                    DrawdownAlertEvent(
                        current_drawdown_pct=float(
                            alert.context.get("drawdown_pct", 0)
                        ),
                        max_allowed_pct=float(alert.context.get("max_allowed_pct", 0)),
                        symbol=alert.context.get("symbol", ""),
                        action_taken=alert.context.get("action", "warn"),
                        source=f"alert_manager.{alert.module}",
                    )
                )
            else:
                EventBus.get().emit(
                    SecurityAlertEvent(
                        severity=alert.severity,
                        rule=alert.type,
                        file=alert.module,
                        line=0,
                        message=alert.message[:200],
                        tentacle="alert_manager",
                        source=f"alert_manager.{alert.module}",
                    )
                )
        except Exception:
            pass

    def get_alerts(self, filter_func=None) -> List[Alert]:
        if filter_func:
            return [a for a in self.alerts if filter_func(a)]
        return list(self.alerts)

    def register_autoheal(self, module_name: str, heal_func) -> None:
        self.autoheal_registry[module_name] = heal_func

    def run_autoheal(self, alert: Alert):
        heal_func = self.autoheal_registry.get(alert.module)
        if not heal_func:
            return None

        result = heal_func(alert)
        correction = {
            "correction": True,
            "module": alert.module,
            "alert": alert.to_dict(),
            "result": result,
            "timestamp": datetime.utcnow().isoformat(),
        }
        with open(self.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(correction) + "\n")
        return result
