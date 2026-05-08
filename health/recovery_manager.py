"""
Recovery Manager — automated recovery strategies per failure type.

When a module fails, the recovery manager selects and executes
the appropriate recovery strategy (restart, disable, escalate).
Integrates with the kernel's state machine and runtime controller.

Usage:
    from health.recovery_manager import recovery_manager

    # Register a custom recovery strategy for a module
    recovery_manager.register_strategy(
        module="signal_engine",
        strategy=RestartStrategy(max_attempts=5, backoff_sec=10),
    )

    # Trigger recovery manually (also called automatically by RuntimeController)
    recovery_manager.recover("signal_engine", reason="heartbeat timeout")
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional

from observability.json_logger import get_logger
from observability.metrics_bus import metrics_bus
from system.module_registry import ModulePriority, ModuleStatus, module_registry
from system.runtime_controller import runtime_controller
from system.state_manager import SystemState, state_manager

log = get_logger("recovery_manager")


# ------------------------------------------------------------------
# Recovery outcomes
# ------------------------------------------------------------------


class RecoveryOutcome(Enum):
    SUCCESS = auto()
    FAILED = auto()
    ESCALATED = auto()
    SKIPPED = auto()


@dataclass
class RecoveryEvent:
    module: str
    reason: str
    outcome: RecoveryOutcome
    strategy_name: str
    attempt: int
    duration_sec: float
    timestamp: float = field(default_factory=time.time)

    def snapshot(self) -> dict:
        return {
            "module": self.module,
            "reason": self.reason,
            "outcome": self.outcome.name,
            "strategy": self.strategy_name,
            "attempt": self.attempt,
            "duration_sec": round(self.duration_sec, 2),
            "timestamp": self.timestamp,
        }


# ------------------------------------------------------------------
# Recovery strategies
# ------------------------------------------------------------------


class RecoveryStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def execute(self, module: str, attempt: int) -> RecoveryOutcome: ...


class RestartStrategy(RecoveryStrategy):
    """Try to restart the module with exponential backoff."""

    def __init__(self, max_attempts: int = 3, backoff_sec: float = 5.0) -> None:
        self.max_attempts = max_attempts
        self.backoff_sec = backoff_sec

    @property
    def name(self) -> str:
        return "restart"

    def execute(self, module: str, attempt: int) -> RecoveryOutcome:
        if attempt > self.max_attempts:
            return RecoveryOutcome.ESCALATED

        wait = self.backoff_sec * (2 ** (attempt - 1))
        log.warning(
            "recovery_restart_wait", module=module, attempt=attempt, wait_sec=wait
        )
        time.sleep(min(wait, 60.0))

        success = runtime_controller.restart_module(
            module, reason=f"recovery attempt {attempt}"
        )
        return RecoveryOutcome.SUCCESS if success else RecoveryOutcome.FAILED


class DisableAndAlertStrategy(RecoveryStrategy):
    """Disable the module and trigger a RISK_OFF state."""

    @property
    def name(self) -> str:
        return "disable_and_alert"

    def execute(self, module: str, attempt: int) -> RecoveryOutcome:
        runtime_controller.disable_module(
            module, reason="unrecoverable — disabled by recovery manager"
        )
        info = module_registry.get(module)
        if info and info.priority == ModulePriority.CRITICAL:
            state_manager.try_transition(
                SystemState.RISK_OFF, f"critical module disabled: {module}"
            )
        return RecoveryOutcome.ESCALATED


class RiskOffAndRestartStrategy(RecoveryStrategy):
    """Transition to RISK_OFF, attempt restart, then resume if successful."""

    def __init__(self, max_attempts: int = 2) -> None:
        self.max_attempts = max_attempts

    @property
    def name(self) -> str:
        return "risk_off_then_restart"

    def execute(self, module: str, attempt: int) -> RecoveryOutcome:
        if attempt == 1:
            state_manager.try_transition(
                SystemState.RISK_OFF, f"recovery: {module} restarting"
            )

        if attempt > self.max_attempts:
            log.critical(
                "recovery_max_attempts_exceeded", module=module, attempt=attempt
            )
            state_manager.force_panic(f"unrecoverable module: {module}")
            return RecoveryOutcome.ESCALATED

        time.sleep(10.0)
        success = runtime_controller.restart_module(
            module, reason=f"risk_off recovery attempt {attempt}"
        )
        if success:
            state_manager.try_transition(
                SystemState.READY, f"recovery succeeded: {module}"
            )
            return RecoveryOutcome.SUCCESS
        return RecoveryOutcome.FAILED


# ------------------------------------------------------------------
# Recovery Manager
# ------------------------------------------------------------------


class RecoveryManager:
    """
    Coordinates automated recovery for failed modules.
    Chooses the right strategy based on module priority and failure count.
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, RecoveryStrategy] = {}
        self._attempts: Dict[str, int] = {}
        self._history: List[RecoveryEvent] = []
        self._lock = threading.RLock()
        self._callbacks: List[Callable[[RecoveryEvent], None]] = []

        # Default strategies per priority
        self._default_strategies: Dict[ModulePriority, RecoveryStrategy] = {
            ModulePriority.CRITICAL: RiskOffAndRestartStrategy(max_attempts=2),
            ModulePriority.HIGH: RestartStrategy(max_attempts=3, backoff_sec=10.0),
            ModulePriority.MEDIUM: RestartStrategy(max_attempts=3, backoff_sec=5.0),
            ModulePriority.LOW: DisableAndAlertStrategy(),
        }

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_strategy(self, module: str, strategy: RecoveryStrategy) -> None:
        self._strategies[module] = strategy

    def on_recovery_event(self, callback: Callable[[RecoveryEvent], None]) -> None:
        self._callbacks.append(callback)

    # ------------------------------------------------------------------
    # Recovery execution
    # ------------------------------------------------------------------

    def recover(self, module: str, reason: str = "") -> RecoveryOutcome:
        """
        Attempt to recover a failed module.
        Thread-safe — can be called concurrently.
        """
        with self._lock:
            attempt = self._attempts.get(module, 0) + 1
            self._attempts[module] = attempt

        strategy = self._get_strategy(module)
        log.warning(
            "recovery_started",
            module=module,
            reason=reason,
            strategy=strategy.name,
            attempt=attempt,
        )

        t0 = time.time()
        outcome = strategy.execute(module, attempt)
        duration = time.time() - t0

        event = RecoveryEvent(
            module=module,
            reason=reason,
            outcome=outcome,
            strategy_name=strategy.name,
            attempt=attempt,
            duration_sec=duration,
        )

        with self._lock:
            self._history.append(event)
            if outcome == RecoveryOutcome.SUCCESS:
                self._attempts[module] = 0  # reset counter on success

        metrics_bus.increment(module, f"recovery.{outcome.name.lower()}")
        log.info(
            "recovery_outcome",
            module=module,
            outcome=outcome.name,
            attempt=attempt,
            duration_sec=round(duration, 2),
        )

        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

        return outcome

    def reset_attempts(self, module: str) -> None:
        with self._lock:
            self._attempts[module] = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_strategy(self, module: str) -> RecoveryStrategy:
        if module in self._strategies:
            return self._strategies[module]
        info = module_registry.get(module)
        priority = info.priority if info else ModulePriority.MEDIUM
        return self._default_strategies[priority]

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def history(self, last_n: int = 50) -> List[RecoveryEvent]:
        with self._lock:
            return list(self._history[-last_n:])

    def snapshot(self) -> dict:
        with self._lock:
            attempts = dict(self._attempts)
            recent = [e.snapshot() for e in self._history[-20:]]
        return {
            "active_recoveries": {m: a for m, a in attempts.items() if a > 0},
            "total_recovery_events": len(self._history),
            "recent_events": recent,
        }


# Singleton
recovery_manager = RecoveryManager()

# ------------------------------------------------------------------
# Wire recovery_manager into the runtime controller's failure escalation
# ------------------------------------------------------------------
from system.module_registry import ModuleStatus as _MS


def _on_module_unhealthy(name: str, status: _MS) -> None:
    if status == _MS.UNHEALTHY:
        threading.Thread(
            target=recovery_manager.recover,
            args=(name, "module status → UNHEALTHY"),
            daemon=True,
            name=f"recovery.{name}",
        ).start()


module_registry.on_status_change(_on_module_unhealthy)
