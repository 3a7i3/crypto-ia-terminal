"""
Central registry for all system modules.
Each module registers itself, publishes heartbeats, and exposes a health snapshot.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("system.module_registry")


class ModuleStatus(Enum):
    STARTING = auto()
    HEALTHY = auto()
    DEGRADED = auto()  # working but with issues
    UNHEALTHY = auto()  # not responding / errors
    STOPPED = auto()
    DISABLED = auto()  # manually disabled by operator


class ModulePriority(Enum):
    CRITICAL = 0  # system cannot run without it (exchange, risk gate)
    HIGH = 1  # important but degradable (AI advisor, scanner)
    MEDIUM = 2  # useful (analytics, dashboard)
    LOW = 3  # optional (reporting, backtest)


@dataclass
class ModuleInfo:
    name: str
    priority: ModulePriority
    status: ModuleStatus = ModuleStatus.STARTING
    last_heartbeat: float = field(default_factory=time.time)
    heartbeat_timeout_sec: float = 30.0
    latency_ms: float = 0.0
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    error_count: int = 0
    last_error: Optional[str] = None
    last_event: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Lifecycle hooks — set by the module itself
    start_fn: Optional[Callable] = field(default=None, repr=False)
    stop_fn: Optional[Callable] = field(default=None, repr=False)
    health_fn: Optional[Callable[[], bool]] = field(default=None, repr=False)

    @property
    def heartbeat_age(self) -> float:
        return time.time() - self.last_heartbeat

    @property
    def is_alive(self) -> bool:
        if self.status in {ModuleStatus.STOPPED, ModuleStatus.DISABLED}:
            return False
        return self.heartbeat_age < self.heartbeat_timeout_sec

    def snapshot(self) -> dict:
        return {
            "module": self.name,
            "status": self.status.name,
            "priority": self.priority.name,
            "is_alive": self.is_alive,
            "heartbeat_age_sec": round(self.heartbeat_age, 2),
            "latency_ms": round(self.latency_ms, 1),
            "memory_mb": round(self.memory_mb, 1),
            "cpu_percent": round(self.cpu_percent, 1),
            "error_count": self.error_count,
            "last_error": self.last_error,
            "last_event": self.last_event,
        }


class ModuleRegistry:
    """
    Single source of truth for all running modules.
    Thread-safe. The kernel reads from it; modules write to it.
    """

    def __init__(self) -> None:
        self._modules: Dict[str, ModuleInfo] = {}
        self._lock = threading.RLock()
        self._listeners: List[Callable[[str, ModuleStatus], None]] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        priority: ModulePriority = ModulePriority.MEDIUM,
        heartbeat_timeout_sec: float = 30.0,
        start_fn: Optional[Callable] = None,
        stop_fn: Optional[Callable] = None,
        health_fn: Optional[Callable[[], bool]] = None,
    ) -> ModuleInfo:
        with self._lock:
            if name in self._modules:
                return self._modules[name]
            info = ModuleInfo(
                name=name,
                priority=priority,
                heartbeat_timeout_sec=heartbeat_timeout_sec,
                start_fn=start_fn,
                stop_fn=stop_fn,
                health_fn=health_fn,
            )
            self._modules[name] = info
            return info

    def unregister(self, name: str) -> None:
        with self._lock:
            self._modules.pop(name, None)

    # ------------------------------------------------------------------
    # Heartbeat + status updates
    # ------------------------------------------------------------------

    def heartbeat(
        self, name: str, latency_ms: float = 0.0, event: Optional[str] = None
    ) -> None:
        with self._lock:
            m = self._modules.get(name)
            if m is None:
                return
            m.last_heartbeat = time.time()
            m.latency_ms = latency_ms
            if event:
                m.last_event = event
            if m.status == ModuleStatus.STARTING:
                self._set_status(m, ModuleStatus.HEALTHY)

    def set_status(
        self, name: str, status: ModuleStatus, reason: Optional[str] = None
    ) -> None:
        with self._lock:
            m = self._modules.get(name)
            if m is None:
                return
            if reason:
                m.last_event = reason
            self._set_status(m, status)

    def report_error(self, name: str, error: str) -> None:
        with self._lock:
            m = self._modules.get(name)
            if m is None:
                return
            m.error_count += 1
            m.last_error = error
            if m.status == ModuleStatus.HEALTHY:
                self._set_status(m, ModuleStatus.DEGRADED)

    def update_metrics(
        self, name: str, memory_mb: float = 0.0, cpu_percent: float = 0.0
    ) -> None:
        with self._lock:
            m = self._modules.get(name)
            if m is None:
                return
            m.memory_mb = memory_mb
            m.cpu_percent = cpu_percent

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[ModuleInfo]:
        return self._modules.get(name)

    def all_modules(self) -> List[ModuleInfo]:
        return list(self._modules.values())

    def critical_modules(self) -> List[ModuleInfo]:
        return [
            m for m in self._modules.values() if m.priority == ModulePriority.CRITICAL
        ]

    def unhealthy_modules(self) -> List[ModuleInfo]:
        with self._lock:
            result = []
            for m in self._modules.values():
                if m.status in {ModuleStatus.STOPPED, ModuleStatus.DISABLED}:
                    continue
                if not m.is_alive or m.status in {
                    ModuleStatus.UNHEALTHY,
                    ModuleStatus.DEGRADED,
                }:
                    result.append(m)
            return result

    def all_critical_healthy(self) -> bool:
        return all(
            m.is_alive and m.status == ModuleStatus.HEALTHY
            for m in self.critical_modules()
        )

    def system_health_score(self) -> float:
        """0.0 (all dead) to 1.0 (all healthy)."""
        with self._lock:
            modules = list(self._modules.values())
            if not modules:
                return 0.0
            weights = {
                ModulePriority.CRITICAL: 4,
                ModulePriority.HIGH: 2,
                ModulePriority.MEDIUM: 1,
                ModulePriority.LOW: 0.5,
            }
            total = sum(weights[m.priority] for m in modules)
            healthy = sum(
                weights[m.priority]
                for m in modules
                if m.is_alive and m.status == ModuleStatus.HEALTHY
            )
            return healthy / total if total else 0.0

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    def on_status_change(self, callback: Callable[[str, ModuleStatus], None]) -> None:
        self._listeners.append(callback)

    def _set_status(self, m: ModuleInfo, new_status: ModuleStatus) -> None:
        if m.status == new_status:
            return
        m.status = new_status
        for cb in self._listeners:
            try:
                cb(m.name, new_status)
            except Exception:
                logger.exception(
                    "Module status listener failed for %s -> %s",
                    m.name,
                    new_status.name,
                )

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "health_score": round(self.system_health_score(), 3),
                "total_modules": len(self._modules),
                "all_critical_healthy": self.all_critical_healthy(),
                "unhealthy": [m.name for m in self.unhealthy_modules()],
                "modules": [m.snapshot() for m in self._modules.values()],
            }


# Singleton
module_registry = ModuleRegistry()
