"""
Heartbeat System — active heartbeat monitor per module.

Each module calls beat() periodically. The HeartbeatSystem detects
silent deaths (no beat within timeout) and reports them to the module
registry and metrics bus.

Usage:
    from observability.heartbeat_system import heartbeat_system

    # From within any module's main loop:
    heartbeat_system.beat("signal_engine", latency_ms=12.4)

    # Start background monitor (called by kernel):
    heartbeat_system.start()
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from observability.metrics_bus import metrics_bus
from system.module_registry import ModuleStatus, module_registry

logger = logging.getLogger("observability.heartbeat_system")


@dataclass
class HeartbeatRecord:
    module: str
    timeout_sec: float
    last_beat: float = field(default_factory=time.time)
    beat_count: int = 0
    miss_count: int = 0
    latency_ms: float = 0.0
    alive: bool = True

    @property
    def age_sec(self) -> float:
        return time.time() - self.last_beat

    @property
    def is_alive(self) -> bool:
        return self.age_sec < self.timeout_sec

    def snapshot(self) -> dict:
        return {
            "module": self.module,
            "alive": self.is_alive,
            "age_sec": round(self.age_sec, 2),
            "timeout_sec": self.timeout_sec,
            "beat_count": self.beat_count,
            "miss_count": self.miss_count,
            "latency_ms": round(self.latency_ms, 1),
        }


class HeartbeatSystem:
    """
    Background monitor that tracks module liveness via heartbeat records.
    Modules must call beat() regularly to remain "alive".
    Silent deaths are detected and escalated to the module registry.
    """

    POLL_INTERVAL_SEC = 5.0

    def __init__(self) -> None:
        self._records: Dict[str, HeartbeatRecord] = {}
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._death_callbacks: List[Callable[[str], None]] = []
        self._revival_callbacks: List[Callable[[str], None]] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, module: str, timeout_sec: float = 30.0) -> None:
        with self._lock:
            if module not in self._records:
                self._records[module] = HeartbeatRecord(
                    module=module, timeout_sec=timeout_sec
                )

    # ------------------------------------------------------------------
    # Beat API (called by modules)
    # ------------------------------------------------------------------

    def beat(
        self, module: str, latency_ms: float = 0.0, event: Optional[str] = None
    ) -> None:
        """Module signals it is alive. Call this inside every main loop iteration."""
        with self._lock:
            rec = self._records.get(module)
            if rec is None:
                rec = HeartbeatRecord(module=module, timeout_sec=30.0)
                self._records[module] = rec

            was_dead = not rec.is_alive
            rec.last_beat = time.time()
            rec.beat_count += 1
            rec.latency_ms = latency_ms
            rec.alive = True

        # Also update the module registry
        module_registry.heartbeat(module, latency_ms=latency_ms, event=event)
        metrics_bus.record(module, "heartbeat_latency_ms", latency_ms)
        metrics_bus.increment(module, "heartbeat_count")

        if was_dead:
            self._on_revival(module)

    # ------------------------------------------------------------------
    # Background monitor
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="HeartbeatSystem.monitor"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self._check_all()
            except Exception:
                logger.exception("Heartbeat monitor loop failed")
            time.sleep(self.POLL_INTERVAL_SEC)

    def _check_all(self) -> None:
        with self._lock:
            records = list(self._records.values())

        for rec in records:
            if not rec.is_alive and rec.alive:
                rec.alive = False
                rec.miss_count += 1
                self._on_death(rec.module)
            metrics_bus.gauge(rec.module, "heartbeat_age_sec", rec.age_sec)

    def _on_death(self, module: str) -> None:
        module_registry.set_status(module, ModuleStatus.UNHEALTHY, "heartbeat timeout")
        metrics_bus.increment(module, "heartbeat_misses")
        for cb in self._death_callbacks:
            try:
                cb(module)
            except Exception:
                logger.exception("Heartbeat death callback failed for %s", module)

    def _on_revival(self, module: str) -> None:
        module_registry.set_status(module, ModuleStatus.HEALTHY, "heartbeat resumed")
        for cb in self._revival_callbacks:
            try:
                cb(module)
            except Exception:
                logger.exception("Heartbeat revival callback failed for %s", module)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_death(self, callback: Callable[[str], None]) -> None:
        self._death_callbacks.append(callback)

    def on_revival(self, callback: Callable[[str], None]) -> None:
        self._revival_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get(self, module: str) -> Optional[HeartbeatRecord]:
        return self._records.get(module)

    def dead_modules(self) -> List[str]:
        with self._lock:
            return [r.module for r in self._records.values() if not r.is_alive]

    def snapshot(self) -> dict:
        with self._lock:
            records = list(self._records.values())
        alive = [r for r in records if r.is_alive]
        dead = [r for r in records if not r.is_alive]
        return {
            "monitored_modules": len(records),
            "alive": len(alive),
            "dead": len(dead),
            "dead_modules": [r.module for r in dead],
            "records": [r.snapshot() for r in records],
        }


# Singleton
heartbeat_system = HeartbeatSystem()
