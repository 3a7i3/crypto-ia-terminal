"""
Incident Manager — tracks, aggregates, and escalates system incidents.

An "incident" is a named, time-bounded problem that may involve multiple
related errors. Unlike raw error events, incidents have lifecycle:
  OPEN -> INVESTIGATING -> RESOLVED | ESCALATED

Integrates with the error_bus to auto-create incidents from HIGH/CRITICAL errors,
and with the state_manager to escalate to PANIC when warranted.

Usage:
    from errors.incident_manager import incident_manager, IncidentSeverity

    # Auto-created from error_bus (wired at module load)
    # Or manually:
    inc = incident_manager.open(
        title="Exchange API timeout",
        module="exchange_connector",
        severity=IncidentSeverity.HIGH,
        description="Binance REST API returning 504 for 3 consecutive calls",
    )
    incident_manager.resolve(inc.id, "Binance recovered after 45s")
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from errors.error_bus import ErrorCategory, ErrorEvent, ErrorSeverity, error_bus
from observability.json_logger import get_logger
from observability.metrics_bus import metrics_bus

log = get_logger("incident_manager", category="incidents")


class IncidentSeverity(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4  # may trigger PANIC if unresolved


class IncidentStatus(Enum):
    OPEN = auto()
    INVESTIGATING = auto()
    RESOLVED = auto()
    ESCALATED = auto()


@dataclass
class Incident:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    module: str = ""
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    status: IncidentStatus = IncidentStatus.OPEN
    description: str = ""
    opened_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolution: str = ""
    related_errors: List[str] = field(default_factory=list)  # trace_ids
    auto_created: bool = False

    @property
    def duration_sec(self) -> float:
        end = self.resolved_at or time.time()
        return end - self.opened_at

    @property
    def is_open(self) -> bool:
        return self.status in {IncidentStatus.OPEN, IncidentStatus.INVESTIGATING}

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "module": self.module,
            "severity": self.severity.name,
            "status": self.status.name,
            "description": self.description,
            "opened_at": self.opened_at,
            "resolved_at": self.resolved_at,
            "resolution": self.resolution,
            "duration_sec": round(self.duration_sec, 1),
            "related_error_count": len(self.related_errors),
            "auto_created": self.auto_created,
        }


# How long before an unresolved CRITICAL incident triggers PANIC
CRITICAL_INCIDENT_PANIC_TTL_SEC = 120.0


class IncidentManager:
    """
    Lifecycle manager for system incidents.
    Auto-creates incidents from HIGH/CRITICAL error_bus events.
    """

    def __init__(self) -> None:
        self._incidents: Dict[str, Incident] = {}
        self._lock = threading.RLock()
        self._listeners: List[Callable[[Incident], None]] = []
        self._watchdog_thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(
        self,
        title: str,
        module: str,
        severity: IncidentSeverity = IncidentSeverity.MEDIUM,
        description: str = "",
        auto_created: bool = False,
    ) -> Incident:
        inc = Incident(
            title=title,
            module=module,
            severity=severity,
            description=description,
            auto_created=auto_created,
        )
        with self._lock:
            self._incidents[inc.id] = inc

        metrics_bus.increment("incident_manager", f"opened.{severity.name.lower()}")
        log.incident(
            "incident_opened",
            id=inc.id,
            title=title,
            module=module,
            severity=severity.name,
            auto=auto_created,
        )
        self._notify(inc)
        return inc

    def investigate(self, incident_id: str, note: str = "") -> bool:
        with self._lock:
            inc = self._incidents.get(incident_id)
            if inc is None or not inc.is_open:
                return False
            inc.status = IncidentStatus.INVESTIGATING
        log.incident("incident_investigating", id=incident_id, note=note)
        return True

    def resolve(self, incident_id: str, resolution: str = "") -> bool:
        with self._lock:
            inc = self._incidents.get(incident_id)
            if inc is None or not inc.is_open:
                return False
            inc.status = IncidentStatus.RESOLVED
            inc.resolved_at = time.time()
            inc.resolution = resolution

        metrics_bus.increment("incident_manager", "resolved")
        log.incident(
            "incident_resolved",
            id=incident_id,
            duration_sec=round(inc.duration_sec, 1),
            resolution=resolution,
        )
        self._notify(inc)
        return True

    def escalate(self, incident_id: str, reason: str = "") -> bool:
        with self._lock:
            inc = self._incidents.get(incident_id)
            if inc is None:
                return False
            inc.status = IncidentStatus.ESCALATED

        log.incident("incident_escalated", id=incident_id, reason=reason)
        metrics_bus.increment("incident_manager", "escalated")

        # Critical escalated incident → PANIC
        if inc and inc.severity == IncidentSeverity.CRITICAL:
            from system.state_manager import state_manager

            state_manager.force_panic(f"critical incident escalated: {inc.title}")

        self._notify(inc)
        return True

    # ------------------------------------------------------------------
    # Error bus integration
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Wire into error_bus and start the watchdog."""
        error_bus.subscribe(self._on_error_event)
        self._running = True
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="IncidentManager.watchdog"
        )
        self._watchdog_thread.start()

    def stop(self) -> None:
        self._running = False

    def _on_error_event(self, event: ErrorEvent) -> None:
        if event.severity not in {ErrorSeverity.HIGH, ErrorSeverity.CRITICAL}:
            return

        sev = (
            IncidentSeverity.CRITICAL
            if event.severity == ErrorSeverity.CRITICAL
            else IncidentSeverity.HIGH
        )

        # Check if an open incident already covers this module
        with self._lock:
            existing = next(
                (
                    i
                    for i in self._incidents.values()
                    if i.is_open and i.module == event.module
                ),
                None,
            )

        if existing:
            with self._lock:
                existing.related_errors.append(event.trace_id)
        else:
            inc = self.open(
                title=f"{event.category.name}: {event.message[:80]}",
                module=event.module,
                severity=sev,
                description=f"{event.exception_type}: {event.message}",
                auto_created=True,
            )
            with self._lock:
                inc.related_errors.append(event.trace_id)

    # ------------------------------------------------------------------
    # Watchdog — escalates unresolved critical incidents
    # ------------------------------------------------------------------

    def _watchdog_loop(self) -> None:
        while self._running:
            try:
                self._check_stale_incidents()
            except Exception:
                pass
            time.sleep(30.0)

    def _check_stale_incidents(self) -> None:
        now = time.time()
        with self._lock:
            open_incidents = [i for i in self._incidents.values() if i.is_open]

        for inc in open_incidents:
            if (
                inc.severity == IncidentSeverity.CRITICAL
                and inc.duration_sec > CRITICAL_INCIDENT_PANIC_TTL_SEC
            ):
                log.incident(
                    "incident_stale_critical",
                    id=inc.id,
                    duration_sec=round(inc.duration_sec, 1),
                )
                self.escalate(
                    inc.id, reason=f"unresolved after {inc.duration_sec:.0f}s"
                )

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    def on_incident(self, callback: Callable[[Incident], None]) -> None:
        self._listeners.append(callback)

    def _notify(self, inc: Incident) -> None:
        for cb in self._listeners:
            try:
                cb(inc)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get(self, incident_id: str) -> Optional[Incident]:
        return self._incidents.get(incident_id)

    def open_incidents(self) -> List[Incident]:
        with self._lock:
            return [i for i in self._incidents.values() if i.is_open]

    def all_incidents(self, limit: int = 100) -> List[Incident]:
        with self._lock:
            return list(self._incidents.values())[-limit:]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            incidents = list(self._incidents.values())

        open_list = [i for i in incidents if i.is_open]
        critical_open = [
            i for i in open_list if i.severity == IncidentSeverity.CRITICAL
        ]

        return {
            "total_incidents": len(incidents),
            "open": len(open_list),
            "critical_open": len(critical_open),
            "critical_open_ids": [i.id for i in critical_open],
            "open_incidents": [i.snapshot() for i in open_list],
        }


# Singleton
incident_manager = IncidentManager()
incident_manager.start()
