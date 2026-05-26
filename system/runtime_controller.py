"""
RuntimeController — starts, stops, restarts, and monitors individual modules.
Operates on ModuleInfo objects from the registry and delegates lifecycle hooks.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional

from observability.json_logger import get_logger
from system.module_registry import (
    ModuleInfo,
    ModulePriority,
    ModuleStatus,
    module_registry,
)
from system.state_manager import SystemState, state_manager

_log = get_logger("system.runtime_controller")


class ModuleStartError(Exception):
    pass


class ModuleStopError(Exception):
    pass


class RuntimeController:
    """
    Manages the lifecycle of registered modules.
    Knows about restart policies and failure escalation.
    """

    MAX_RESTART_ATTEMPTS = 3
    RESTART_BACKOFF_SEC = 5.0
    HEALTH_POLL_INTERVAL_SEC = 10.0

    def __init__(self) -> None:
        self._restart_counts: Dict[str, int] = {}
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_module(self, name: str) -> None:
        info = module_registry.get(name)
        if info is None:
            raise ModuleStartError(f"Module '{name}' not registered")
        if info.status in {ModuleStatus.HEALTHY, ModuleStatus.DEGRADED}:
            return  # already running

        _log.info(f"[RuntimeController] Starting module: {name}")
        module_registry.set_status(name, ModuleStatus.STARTING)

        try:
            if info.start_fn is not None:
                info.start_fn()
            module_registry.set_status(name, ModuleStatus.HEALTHY)
            module_registry.heartbeat(name, event="started")
            self._restart_counts[name] = 0
            _log.info(f"[RuntimeController] Module started: {name}")
        except Exception as e:
            err = str(e)
            module_registry.report_error(name, err)
            module_registry.set_status(name, ModuleStatus.UNHEALTHY)
            _log.error(f"[RuntimeController] Failed to start {name}: {err}")
            raise ModuleStartError(f"Start failed for '{name}': {err}") from e

    def stop_module(self, name: str, reason: str = "") -> None:
        info = module_registry.get(name)
        if info is None:
            return
        if info.status == ModuleStatus.STOPPED:
            return

        _log.info(f"[RuntimeController] Stopping module: {name} | {reason}")
        try:
            if info.stop_fn is not None:
                info.stop_fn()
        except Exception as e:
            _log.warning(f"[RuntimeController] Error while stopping {name}: {e}")
        finally:
            module_registry.set_status(name, ModuleStatus.STOPPED, reason)

    def restart_module(self, name: str, reason: str = "") -> bool:
        """
        Attempts to restart a module with backoff.
        Returns False if max retries exceeded — caller should escalate.
        """
        attempts = self._restart_counts.get(name, 0)
        if attempts >= self.MAX_RESTART_ATTEMPTS:
            _log.error(
                f"[RuntimeController] {name} exceeded max restarts ({self.MAX_RESTART_ATTEMPTS})"
            )
            module_registry.set_status(
                name, ModuleStatus.DISABLED, "max restarts exceeded"
            )
            return False

        _log.warning(
            f"[RuntimeController] Restarting {name} (attempt {attempts + 1}) | {reason}"
        )
        self._restart_counts[name] = attempts + 1
        time.sleep(self.RESTART_BACKOFF_SEC * (attempts + 1))

        self.stop_module(name, reason="restarting")
        try:
            self.start_module(name)
            return True
        except ModuleStartError:
            return False

    def disable_module(self, name: str, reason: str = "") -> None:
        """Permanently disable a module (operator action)."""
        self.stop_module(name, reason)
        module_registry.set_status(name, ModuleStatus.DISABLED, reason)
        _log.warning(f"[RuntimeController] Module disabled: {name} | {reason}")

    # ------------------------------------------------------------------
    # Background health monitor
    # ------------------------------------------------------------------

    def start_monitoring(self) -> None:
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="RuntimeController.monitor"
        )
        self._monitor_thread.start()
        _log.info("[RuntimeController] Health monitor started")

    def stop_monitoring(self) -> None:
        self._running = False

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self._check_all_modules()
            except Exception as e:
                _log.error(f"[RuntimeController] Monitor loop error: {e}")
            time.sleep(self.HEALTH_POLL_INTERVAL_SEC)

    def _check_all_modules(self) -> None:
        for info in module_registry.all_modules():
            if info.status in {
                ModuleStatus.STOPPED,
                ModuleStatus.DISABLED,
                ModuleStatus.STARTING,
            }:
                continue
            self._check_module(info)

    def _check_module(self, info: ModuleInfo) -> None:
        # 1. Heartbeat timeout
        if not info.is_alive:
            _log.warning(
                f"[RuntimeController] Heartbeat timeout: {info.name} (age={info.heartbeat_age:.1f}s)"
            )
            module_registry.set_status(
                info.name, ModuleStatus.UNHEALTHY, "heartbeat timeout"
            )
            self._handle_unhealthy(info)
            return

        # 2. Custom health check
        if info.health_fn is not None:
            try:
                healthy = info.health_fn()
                if not healthy and info.status == ModuleStatus.HEALTHY:
                    module_registry.set_status(
                        info.name, ModuleStatus.DEGRADED, "health_fn returned False"
                    )
            except Exception as e:
                module_registry.report_error(info.name, str(e))

    def _handle_unhealthy(self, info: ModuleInfo) -> None:
        if info.priority == ModulePriority.CRITICAL:
            _log.critical(
                f"[RuntimeController] CRITICAL module unhealthy: {info.name} — escalating to state machine"
            )
            state_manager.try_transition(
                SystemState.DEGRADED, f"critical module down: {info.name}"
            )
        # Attempt auto-restart for non-disabled modules
        if info.status != ModuleStatus.DISABLED:
            success = self.restart_module(
                info.name, reason="unhealthy detected by monitor"
            )
            if not success and info.priority == ModulePriority.CRITICAL:
                _log.critical(
                    f"[RuntimeController] Cannot recover critical module {info.name} — forcing PANIC"
                )
                state_manager.force_panic(f"unrecoverable critical module: {info.name}")

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        return {
            "monitoring_active": self._running,
            "restart_counts": dict(self._restart_counts),
            "max_restart_attempts": self.MAX_RESTART_ATTEMPTS,
        }


# Singleton
runtime_controller = RuntimeController()
