"""
system_health_monitor.py — System Health Monitor (P9)

Surveille la santé opérationnelle de chaque composant en temps réel.
Chaque composant reporte : latence, erreurs, retries, état circuit-breaker.

Statuts :
  GREEN  : tout nominal
  YELLOW : latence > seuil OU error_rate > seuil OU cb_state dégradé
  RED    : YELLOW depuis > P9_YELLOW_ESCALATION_CYCLES cycles
           OU error_rate critique OU circuit-breaker DEGRADED/DISABLED

Alertes : RED = immédiate, YELLOW prolongé = escalade différée.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.agents.risk.system_health_monitor")

_CB_CRITICAL = {"DEGRADED", "DISABLED"}
_CB_WARN = {"UNSTABLE"}


class ComponentStatus(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class ComponentHealth:
    name: str
    status: ComponentStatus = ComponentStatus.GREEN
    latency_ms: float = 0.0
    error_rate: float = 0.0
    retry_count: int = 0
    circuit_breaker_state: str = "HEALTHY"
    yellow_cycles: int = 0
    total_calls: int = 0
    total_errors: int = 0
    last_updated_ts: float = field(default_factory=time.time)


@dataclass
class HealthEvent:
    component: str
    previous: str
    current: str
    reason: str
    ts: float = field(default_factory=time.time)


class SystemHealthMonitor:
    """
    Collecte et agrège l'état de santé de chaque composant.

    Usage dans advisor_loop :
        health.record("risk_governor", latency_ms=12.3)
        health.record("market_scanner", latency_ms=450.0, error=True)
        events = health.tick_cycle()   # appeler 1×/cycle
    """

    def __init__(self) -> None:
        self._latency_warn = float(os.getenv("P9_LATENCY_WARN_MS", "500"))
        self._latency_crit = float(os.getenv("P9_LATENCY_CRIT_MS", "2000"))
        self._error_warn = float(os.getenv("P9_ERROR_RATE_WARN", "0.05"))
        self._error_crit = float(os.getenv("P9_ERROR_RATE_CRIT", "0.20"))
        self._yellow_escalation = int(os.getenv("P9_YELLOW_ESCALATION_CYCLES", "20"))
        self._components: Dict[str, ComponentHealth] = {}
        self._events: List[HealthEvent] = []

    # ── Enregistrement ────────────────────────────────────────────────────────

    def record(
        self,
        name: str,
        latency_ms: float = 0.0,
        error: bool = False,
        retries: int = 0,
        cb_state: str = "HEALTHY",
    ) -> None:
        """Enregistre un appel de composant. Appelé à chaque invocation."""
        if name not in self._components:
            self._components[name] = ComponentHealth(name=name)

        c = self._components[name]
        c.total_calls += 1
        if error:
            c.total_errors += 1
        c.latency_ms = latency_ms
        c.retry_count = retries
        c.circuit_breaker_state = cb_state
        c.error_rate = c.total_errors / c.total_calls if c.total_calls else 0.0
        c.last_updated_ts = time.time()

        prev = c.status
        c.status = self._compute_status(c)
        if c.status != ComponentStatus.YELLOW:
            c.yellow_cycles = 0
        if c.status != prev:
            self._emit_event(c, prev.value, c.status.value)

    def _compute_status(self, c: ComponentHealth) -> ComponentStatus:
        if (
            c.circuit_breaker_state in _CB_CRITICAL
            or c.error_rate >= self._error_crit
            or c.latency_ms >= self._latency_crit
        ):
            return ComponentStatus.RED
        if (
            c.circuit_breaker_state in _CB_WARN
            or c.error_rate >= self._error_warn
            or c.latency_ms >= self._latency_warn
        ):
            return ComponentStatus.YELLOW
        return ComponentStatus.GREEN

    # ── Tick cycle ────────────────────────────────────────────────────────────

    def tick_cycle(self) -> List[str]:
        """
        Appelé 1 fois par cycle principal.
        Incrémente yellow_cycles, escalade YELLOW → RED si nécessaire.
        Retourne liste d'événements d'alerte (strings).
        """
        alerts: List[str] = []
        for c in self._components.values():
            if c.status == ComponentStatus.YELLOW:
                c.yellow_cycles += 1
                if c.yellow_cycles >= self._yellow_escalation:
                    prev = c.status
                    c.status = ComponentStatus.RED
                    self._emit_event(
                        c,
                        prev.value,
                        c.status.value,
                        f"YELLOW depuis {c.yellow_cycles} cycles",
                    )
                    alerts.append(
                        f"[P9/Health] {c.name} escaladé RED "
                        f"(YELLOW x{c.yellow_cycles} cycles)"
                    )
            elif c.status == ComponentStatus.RED:
                alerts.append(
                    f"[P9/Health] {c.name} RED "
                    f"err={c.error_rate:.1%} lat={c.latency_ms:.0f}ms "
                    f"cb={c.circuit_breaker_state}"
                )
        return alerts

    # ── Consultation ─────────────────────────────────────────────────────────

    def get_status(self, name: str) -> Optional[ComponentHealth]:
        return self._components.get(name)

    def get_dashboard(self) -> Dict[str, ComponentHealth]:
        return dict(self._components)

    def overall_health(self) -> ComponentStatus:
        if not self._components:
            return ComponentStatus.GREEN
        statuses = [c.status for c in self._components.values()]
        if ComponentStatus.RED in statuses:
            return ComponentStatus.RED
        if ComponentStatus.YELLOW in statuses:
            return ComponentStatus.YELLOW
        return ComponentStatus.GREEN

    def summary(self) -> dict:
        dashboard = self.get_dashboard()
        counts = {s.value: 0 for s in ComponentStatus}
        for c in dashboard.values():
            counts[c.status.value] += 1
        return {
            "overall": self.overall_health().value,
            "components": len(dashboard),
            **counts,
            "events_count": len(self._events),
        }

    def recent_events(self, n: int = 10) -> List[HealthEvent]:
        return list(self._events[-n:])

    def _emit_event(
        self,
        c: ComponentHealth,
        prev: str,
        curr: str,
        reason: str = "",
    ) -> None:
        evt = HealthEvent(
            component=c.name,
            previous=prev,
            current=curr,
            reason=reason or f"err={c.error_rate:.1%} lat={c.latency_ms:.0f}ms",
        )
        self._events.append(evt)
        if len(self._events) > 500:
            self._events = self._events[-500:]
        if curr == "RED":
            _log.warning(
                "[P9/Health] %s → RED reason=%s",
                c.name,
                evt.reason,
            )
        else:
            _log.info(
                "[P9/Health] %s %s→%s reason=%s",
                c.name,
                prev,
                curr,
                evt.reason,
            )
