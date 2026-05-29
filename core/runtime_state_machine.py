"""Runtime State Machine — transitions formelles du système."""

from enum import Enum, auto
from typing import Optional


class SystemMode(Enum):
    BOOTING = auto()
    WARMING = auto()
    READY = auto()
    DEGRADED = auto()
    SAFE_MODE = auto()
    HALTED = auto()
    RECOVERING = auto()
    SHUTDOWN = auto()


# Transitions autorisees
ALLOWED_TRANSITIONS = {
    SystemMode.BOOTING: {SystemMode.WARMING},
    SystemMode.WARMING: {SystemMode.READY, SystemMode.HALTED},
    SystemMode.READY: {SystemMode.DEGRADED, SystemMode.SAFE_MODE, SystemMode.HALTED, SystemMode.SHUTDOWN},
    SystemMode.DEGRADED: {SystemMode.RECOVERING, SystemMode.SAFE_MODE, SystemMode.HALTED, SystemMode.READY},
    SystemMode.SAFE_MODE: {SystemMode.RECOVERING, SystemMode.HALTED},
    SystemMode.HALTED: {SystemMode.RECOVERING},  # UNIQUEMENT intervention humaine
    SystemMode.RECOVERING: {SystemMode.READY, SystemMode.HALTED},
    SystemMode.SHUTDOWN: set(),
}


class RuntimeStateMachine:
    """État runtime central. Une seule instance."""

    def __init__(self):
        self._mode: SystemMode = SystemMode.BOOTING
        self._previous_mode: Optional[SystemMode] = None
        self._mode_history: list[tuple[SystemMode, str]] = [(SystemMode.BOOTING, "init")]

    @property
    def mode(self) -> SystemMode:
        return self._mode

    @property
    def mode_name(self) -> str:
        return self._mode.name

    def can_transition_to(self, target: SystemMode) -> bool:
        return target in ALLOWED_TRANSITIONS.get(self._mode, set())

    def transition_to(self, target: SystemMode, reason: str = "") -> bool:
        if target == self._mode:
            return True
        if not self.can_transition_to(target):
            raise RuntimeError(
                f"Transition interdite: {self._mode.name} -> {target.name}"
            )
        self._previous_mode = self._mode
        self._mode = target
        self._mode_history.append((target, reason))
        return True

    def can_execute(self) -> bool:
        return self._mode in (SystemMode.READY, SystemMode.DEGRADED)

    def require_ready(self) -> None:
        if not self.can_execute():
            raise RuntimeError(f"System in {self._mode.name}, cannot execute")

    @property
    def degraded_since(self) -> Optional[float]:
        for mode, _ in reversed(self._mode_history):
            if mode == SystemMode.DEGRADED:
                return 0.0
        return None

    @property
    def human_intervention_required(self) -> bool:
        return self._mode == SystemMode.HALTED
