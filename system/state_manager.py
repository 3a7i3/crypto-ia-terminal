"""
State machine for the entire system lifecycle.
One global instance — all modules read from it, never write to it directly.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, List


class SystemState(Enum):
    BOOTING = auto()  # process just started, dependencies loading
    SYNCING = auto()  # connecting to exchanges, syncing data
    READY = auto()  # all systems nominal, no trading yet
    TRADING = auto()  # normal trading operations
    RISK_OFF = auto()  # conditions degraded — close positions, halt new entries
    DEGRADED = auto()  # one or more critical modules unhealthy
    RECOVERY = auto()  # self-healing in progress
    SHUTDOWN = auto()  # graceful shutdown underway
    PANIC = auto()  # emergency — all execution halted immediately


# Allowed state transitions (source -> set of valid targets)
_TRANSITIONS: dict[SystemState, set[SystemState]] = {
    SystemState.BOOTING: {SystemState.SYNCING, SystemState.PANIC, SystemState.SHUTDOWN},
    SystemState.SYNCING: {
        SystemState.READY,
        SystemState.DEGRADED,
        SystemState.PANIC,
        SystemState.SHUTDOWN,
    },
    SystemState.READY: {
        SystemState.TRADING,
        SystemState.RISK_OFF,
        SystemState.DEGRADED,
        SystemState.SHUTDOWN,
        SystemState.PANIC,
    },
    SystemState.TRADING: {
        SystemState.RISK_OFF,
        SystemState.DEGRADED,
        SystemState.READY,
        SystemState.SHUTDOWN,
        SystemState.PANIC,
    },
    SystemState.RISK_OFF: {
        SystemState.READY,
        SystemState.TRADING,
        SystemState.DEGRADED,
        SystemState.RECOVERY,
        SystemState.SHUTDOWN,
        SystemState.PANIC,
    },
    SystemState.DEGRADED: {
        SystemState.RECOVERY,
        SystemState.RISK_OFF,
        SystemState.SHUTDOWN,
        SystemState.PANIC,
    },
    SystemState.RECOVERY: {
        SystemState.READY,
        SystemState.DEGRADED,
        SystemState.SHUTDOWN,
        SystemState.PANIC,
    },
    SystemState.SHUTDOWN: set(),
    SystemState.PANIC: {SystemState.SHUTDOWN},
}

# States where execution is completely forbidden
EXECUTION_FORBIDDEN = {
    SystemState.BOOTING,
    SystemState.SYNCING,
    SystemState.RISK_OFF,
    SystemState.DEGRADED,
    SystemState.RECOVERY,
    SystemState.SHUTDOWN,
    SystemState.PANIC,
}


@dataclass
class StateTransition:
    from_state: SystemState
    to_state: SystemState
    reason: str
    timestamp: float = field(default_factory=time.time)


class InvalidTransition(Exception):
    pass


class StateManager:
    """Thread-safe global state machine. Single source of truth for system state."""

    def __init__(self) -> None:
        self._state = SystemState.BOOTING
        self._lock = threading.RLock()
        self._history: List[StateTransition] = []
        self._listeners: List[Callable[[SystemState, SystemState, str], None]] = []
        self._state_entered_at: float = time.time()

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    @property
    def state(self) -> SystemState:
        return self._state

    @property
    def is_trading_allowed(self) -> bool:
        return self._state == SystemState.TRADING

    @property
    def is_execution_allowed(self) -> bool:
        return self._state not in EXECUTION_FORBIDDEN

    @property
    def time_in_current_state(self) -> float:
        return time.time() - self._state_entered_at

    def is_healthy(self) -> bool:
        return self._state in {SystemState.READY, SystemState.TRADING}

    # ------------------------------------------------------------------
    # Transition API
    # ------------------------------------------------------------------

    def transition(self, new_state: SystemState, reason: str = "") -> None:
        with self._lock:
            if new_state not in _TRANSITIONS.get(self._state, set()):
                raise InvalidTransition(
                    f"Illegal transition {self._state.name} → {new_state.name} | reason: {reason}"
                )
            old_state = self._state
            self._state = new_state
            self._state_entered_at = time.time()
            record = StateTransition(old_state, new_state, reason)
            self._history.append(record)
            self._notify(old_state, new_state, reason)

    def force_panic(self, reason: str) -> None:
        """Skip transition validation — used by kill switch and error bus."""
        with self._lock:
            old = self._state
            self._state = SystemState.PANIC
            self._state_entered_at = time.time()
            self._history.append(StateTransition(old, SystemState.PANIC, reason))
            self._notify(old, SystemState.PANIC, reason)

    def try_transition(self, new_state: SystemState, reason: str = "") -> bool:
        """Returns False instead of raising if transition is invalid."""
        try:
            self.transition(new_state, reason)
            return True
        except InvalidTransition:
            return False

    # ------------------------------------------------------------------
    # Listener API
    # ------------------------------------------------------------------

    def on_transition(
        self, callback: Callable[[SystemState, SystemState, str], None]
    ) -> None:
        """Register a listener called on every state change."""
        self._listeners.append(callback)

    def _notify(self, old: SystemState, new: SystemState, reason: str) -> None:
        for cb in self._listeners:
            try:
                cb(old, new, reason)
            except Exception:
                pass  # listeners must never crash the state machine

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def history(self, last_n: int = 20) -> List[StateTransition]:
        return self._history[-last_n:]

    def snapshot(self) -> dict:
        return {
            "state": self._state.name,
            "is_trading_allowed": self.is_trading_allowed,
            "is_execution_allowed": self.is_execution_allowed,
            "time_in_state_sec": round(self.time_in_current_state, 2),
            "transition_count": len(self._history),
        }


# Singleton — import and use directly
state_manager = StateManager()
