"""
P10-F — OperationalState machine.

Remplace le comportement EMERGENCY_STOP pour les erreurs techniques
d'exécution (503, timeout, connexion exchange).

Transitions:
    RUNNING  → DEGRADED : DEGRADED_THRESHOLD erreurs consécutives
    DEGRADED → HALTED   : HALTED_THRESHOLD erreurs OU 15min en DEGRADED
    RUNNING  → HALTED   : HALTED_THRESHOLD erreurs directes (cas extrême)
    *        → RUNNING  : uniquement via reset() (opérateur /RESUME)

Callbacks:
    on_degraded(reason)  — alerte douce, trading continue
    on_halted(reason)    — arrêt réel, requiert /RESUME
    on_recovered()       — retour RUNNING automatique après succès
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Callable, Optional


class OpState(str, Enum):
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"


class OperationalState:
    DEGRADED_THRESHOLD: int = 2
    HALTED_THRESHOLD: int = 10
    DEGRADED_MAX_DURATION_S: float = 900.0  # 15 minutes

    def __init__(
        self,
        on_degraded: Optional[Callable[[str], None]] = None,
        on_halted: Optional[Callable[[str], None]] = None,
        on_recovered: Optional[Callable[[], None]] = None,
    ) -> None:
        self._state = OpState.RUNNING
        self._lock = threading.Lock()
        self._consecutive_errors: int = 0
        self._degraded_since: Optional[float] = None
        self.on_degraded = on_degraded
        self.on_halted = on_halted
        self.on_recovered = on_recovered

    # ── Propriétés ────────────────────────────────────────────────────────────

    @property
    def state(self) -> OpState:
        return self._state

    def is_running(self) -> bool:
        return self._state == OpState.RUNNING

    def is_degraded(self) -> bool:
        return self._state == OpState.DEGRADED

    def is_halted(self) -> bool:
        return self._state == OpState.HALTED

    # ── Enregistrement ────────────────────────────────────────────────────────

    def record_error(self) -> OpState:
        """Appelé une fois par cycle en cas d'échec d'exécution."""
        with self._lock:
            self._consecutive_errors += 1
            n = self._consecutive_errors

            if n >= self.HALTED_THRESHOLD:
                return self._transition(
                    OpState.HALTED,
                    f"{n} erreurs consécutives — seuil HALTED"
                    f" ({self.HALTED_THRESHOLD}) atteint",
                )

            if n >= self.DEGRADED_THRESHOLD:
                if self._state != OpState.DEGRADED:
                    return self._transition(
                        OpState.DEGRADED,
                        f"{n} erreurs consécutives — passage DEGRADED",
                    )
                elapsed = time.time() - (self._degraded_since or time.time())
                if elapsed >= self.DEGRADED_MAX_DURATION_S:
                    return self._transition(
                        OpState.HALTED,
                        f"DEGRADED depuis {elapsed / 60:.0f}min — seuil 15min atteint",
                    )

            return self._state

    def record_success(self) -> None:
        """Appelé quand le cycle se passe sans erreur d'exécution."""
        with self._lock:
            self._consecutive_errors = 0
            if self._state == OpState.DEGRADED:
                self._state = OpState.RUNNING
                self._degraded_since = None
                if self.on_recovered:
                    try:
                        self.on_recovered()
                    except Exception:
                        pass

    def reset(self) -> None:
        """Opérateur /RESUME — retour forcé à RUNNING."""
        with self._lock:
            self._state = OpState.RUNNING
            self._consecutive_errors = 0
            self._degraded_since = None

    # ── Observabilité ─────────────────────────────────────────────────────────

    def summary(self) -> dict:
        with self._lock:
            elapsed = None
            if self._state == OpState.DEGRADED and self._degraded_since:
                elapsed = round(time.time() - self._degraded_since, 1)
            return {
                "state": self._state.value,
                "consecutive_errors": self._consecutive_errors,
                "degraded_duration_s": elapsed,
            }

    # ── Interne ───────────────────────────────────────────────────────────────

    def _transition(self, new_state: OpState, reason: str) -> OpState:
        if self._state == new_state:
            return new_state
        self._state = new_state
        if new_state == OpState.DEGRADED:
            self._degraded_since = time.time()
            if self.on_degraded:
                try:
                    self.on_degraded(reason)
                except Exception:
                    pass
        elif new_state == OpState.HALTED:
            self._degraded_since = None
            if self.on_halted:
                try:
                    self.on_halted(reason)
                except Exception:
                    pass
        return new_state
