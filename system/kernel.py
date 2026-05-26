"""
System Kernel — the single authority over all modules.

Responsibilities:
  - owns the state machine, module registry, dependency graph, runtime controller
  - executes the startup sequence
  - monitors system health continuously
  - escalates to DEGRADED / PANIC when critical modules fail
  - exposes a unified snapshot for dashboards and the CLI

Usage:
    from system.kernel import kernel
    kernel.boot()          # run at process start
    kernel.snapshot()      # read full system state
    kernel.shutdown()      # graceful teardown
"""

from __future__ import annotations

import signal
import threading
import time
from typing import Any, Dict, Optional

from observability.json_logger import get_logger
from system.dependency_manager import dependency_manager
from system.module_registry import ModulePriority, ModuleStatus, module_registry
from system.runtime_controller import runtime_controller
from system.startup_sequence import startup_sequence
from system.state_manager import SystemState, state_manager

_log = get_logger("system.kernel")


class SystemKernel:
    """
    The authoritative system controller.
    Only one instance should exist per process — use the `kernel` singleton.
    """

    HEALTH_CHECK_INTERVAL_SEC = 15.0

    def __init__(self) -> None:
        self._booted = False
        self._shutdown_event = threading.Event()
        self._health_thread: Optional[threading.Thread] = None

        # Wire state change listener
        state_manager.on_transition(self._on_state_change)
        # Wire module status listener
        module_registry.on_status_change(self._on_module_status_change)

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------

    def boot(self) -> bool:
        """
        Full system boot. Call once from main.py or system_bootstrap.py.
        Returns True if system is healthy after boot.
        """
        if self._booted:
            _log.warning("[Kernel] boot() called but system already booted")
            return True

        _log.info("[Kernel] ==========================================")
        _log.info("[Kernel]  SYSTEM KERNEL BOOT")
        _log.info("[Kernel] ==========================================")

        self._install_signal_handlers()
        runtime_controller.start_monitoring()

        success = startup_sequence.run()
        if not success:
            _log.critical("[Kernel] Boot failed — system in PANIC")
            return False

        self._booted = True
        self._start_health_loop()

        _log.info(f"[Kernel] Boot complete. State: {state_manager.state.name}")
        return True

    def mark_ready(self) -> None:
        """
        Call after SYNCING is complete (exchange connected, data warm).
        Transitions system to READY.
        """
        if state_manager.state == SystemState.SYNCING:
            state_manager.transition(SystemState.READY, "exchange sync complete")
            _log.info("[Kernel] System READY")

    def enable_trading(self) -> bool:
        """Allow live execution. Only valid from READY state."""
        if state_manager.state != SystemState.READY:
            _log.warning(
                f"[Kernel] Cannot enable trading from state {state_manager.state.name}"
            )
            return False
        state_manager.transition(SystemState.TRADING, "trading enabled by operator")
        _log.info("[Kernel] TRADING enabled")
        return True

    def risk_off(self, reason: str = "") -> None:
        """Halt new entries, close positions. Called by kill switch / drawdown monitor."""
        if state_manager.try_transition(
            SystemState.RISK_OFF, reason or "risk_off triggered"
        ):
            _log.warning(f"[Kernel] RISK_OFF: {reason}")

    def panic(self, reason: str) -> None:
        """Emergency halt. All execution stops immediately."""
        state_manager.force_panic(reason)
        _log.critical(f"[Kernel] PANIC: {reason}")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self, reason: str = "operator shutdown") -> None:
        """Graceful shutdown — stop modules in reverse dependency order."""
        _log.info(f"[Kernel] Initiating shutdown: {reason}")
        state_manager.try_transition(SystemState.SHUTDOWN, reason)

        self._shutdown_event.set()
        runtime_controller.stop_monitoring()

        shutdown_order = dependency_manager.shutdown_order()
        for name in shutdown_order:
            info = module_registry.get(name)
            if info and info.status not in {
                ModuleStatus.STOPPED,
                ModuleStatus.DISABLED,
            }:
                runtime_controller.stop_module(name, "system shutdown")

        _log.info("[Kernel] Shutdown complete")

    # ------------------------------------------------------------------
    # Health loop
    # ------------------------------------------------------------------

    def _start_health_loop(self) -> None:
        self._health_thread = threading.Thread(
            target=self._health_loop, daemon=True, name="Kernel.health"
        )
        self._health_thread.start()

    def _health_loop(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                self._evaluate_system_health()
            except Exception as e:
                _log.error(f"[Kernel] Health loop error: {e}")
            time.sleep(self.HEALTH_CHECK_INTERVAL_SEC)

    def _evaluate_system_health(self) -> None:
        score = module_registry.system_health_score()
        unhealthy = module_registry.unhealthy_modules()
        critical_ok = module_registry.all_critical_healthy()
        current = state_manager.state

        if current in {SystemState.SHUTDOWN, SystemState.PANIC}:
            return

        if not critical_ok:
            # Critical module down — escalate
            if current == SystemState.TRADING:
                _log.warning(
                    "[Kernel] Critical module unhealthy during TRADING — RISK_OFF"
                )
                state_manager.try_transition(
                    SystemState.RISK_OFF, "critical module unhealthy"
                )
            elif current not in {
                SystemState.DEGRADED,
                SystemState.RISK_OFF,
                SystemState.RECOVERY,
            }:
                state_manager.try_transition(
                    SystemState.DEGRADED, "critical module unhealthy"
                )

        elif score < 0.6 and current == SystemState.TRADING:
            _log.warning(
                f"[Kernel] Health score {score:.2f} < 0.6 during TRADING — RISK_OFF"
            )
            state_manager.try_transition(
                SystemState.RISK_OFF, f"health score low: {score:.2f}"
            )

        elif current == SystemState.DEGRADED and critical_ok and score > 0.8:
            # Recovery
            _log.info("[Kernel] Health recovered — entering RECOVERY")
            state_manager.try_transition(SystemState.RECOVERY, "health recovered")

        elif current == SystemState.RECOVERY and critical_ok and score >= 0.95:
            _log.info("[Kernel] Full recovery — returning to READY")
            state_manager.try_transition(SystemState.READY, "full recovery")

    # ------------------------------------------------------------------
    # Event listeners
    # ------------------------------------------------------------------

    def _on_state_change(self, old: SystemState, new: SystemState, reason: str) -> None:
        _log.info(f"[Kernel] STATE: {old.name} → {new.name} | {reason}")
        if new == SystemState.PANIC:
            _log.critical("[Kernel] !! PANIC STATE — all execution halted !!")

    def _on_module_status_change(self, name: str, status: ModuleStatus) -> None:
        if status in {ModuleStatus.UNHEALTHY, ModuleStatus.DISABLED}:
            _log.warning(f"[Kernel] Module degraded: {name} → {status.name}")

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _install_signal_handlers(self) -> None:
        try:
            signal.signal(signal.SIGINT, lambda s, f: self.shutdown("SIGINT"))
            signal.signal(signal.SIGTERM, lambda s, f: self.shutdown("SIGTERM"))
        except (OSError, ValueError):
            # Not in main thread or unsupported platform — skip
            pass

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    @property
    def state(self) -> SystemState:
        return state_manager.state

    @property
    def is_trading(self) -> bool:
        return state_manager.is_trading_allowed

    @property
    def is_execution_allowed(self) -> bool:
        return state_manager.is_execution_allowed

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kernel": {
                "booted": self._booted,
                "state": state_manager.state.name,
                "is_trading_allowed": state_manager.is_trading_allowed,
                "is_execution_allowed": state_manager.is_execution_allowed,
            },
            "state_machine": state_manager.snapshot(),
            "modules": module_registry.snapshot(),
            "startup": startup_sequence.snapshot(),
            "runtime": runtime_controller.snapshot(),
            "dependency_graph": dependency_manager.snapshot(),
        }


# -----------------------------------------------------------------------
# Singleton — the one kernel for this process
# -----------------------------------------------------------------------
kernel = SystemKernel()
