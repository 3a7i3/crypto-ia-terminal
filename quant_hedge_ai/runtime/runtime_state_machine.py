"""
runtime_state_machine.py — Machine d'état runtime à 5 niveaux de dégradation.

États :
    NORMAL    → fonctionnement nominal, trading autorisé
    DEGRADED  → erreurs isolées, trading autorisé avec taille réduite
    CRITICAL  → multiple failures, trading suspendu, lecture seule
    SAFE_MODE → blocage total, attente manuelle ou silence prolongé
    RECOVERY  → silence confirmé, retour progressif vers NORMAL

Transitions automatiques basées sur un compteur d'erreurs en fenêtre glissante.
L'horloge est injectable (_clock) pour les tests déterministes sans sleep().

Usage :
    sm = RuntimeStateMachine()
    sm.report_error("exchange_offline")  # → peut déclencher DEGRADED
    sm.report_ok()                       # → peut déclencher RECOVERY
    if not sm.can_trade:
        logger.warning("Trading suspendu — état %s", sm.state)
"""

from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
from typing import Callable

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.runtime.runtime_state_machine")


class SystemState(str, Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    SAFE_MODE = "SAFE_MODE"
    RECOVERY = "RECOVERY"


# Politiques par état : (can_trade, can_fetch_data, size_factor)
_POLICIES: dict[SystemState, tuple[bool, bool, float]] = {
    SystemState.NORMAL: (True, True, 1.0),
    SystemState.DEGRADED: (True, True, 0.5),  # taille réduite de 50 %
    SystemState.CRITICAL: (False, True, 0.0),
    SystemState.SAFE_MODE: (False, False, 0.0),
    SystemState.RECOVERY: (False, True, 0.0),
}


class RuntimeStateMachine:
    """
    Moniteur de santé runtime thread-safe.

    Paramètres-clés :
        degraded_threshold  — nb erreurs → DEGRADED
        critical_threshold  — nb erreurs → CRITICAL
        safe_threshold      — nb erreurs → SAFE_MODE
        window_s            — durée de la fenêtre glissante (secondes)
        silence_s           — silence requis pour entrer en RECOVERY
        stability_s         — stabilité requise pour sortir de RECOVERY → NORMAL
    """

    def __init__(
        self,
        degraded_threshold: int = 3,
        critical_threshold: int = 7,
        safe_threshold: int = 10,
        window_s: float = 60.0,
        silence_s: float = 30.0,
        stability_s: float = 60.0,
        _clock: Callable[[], float] | None = None,
    ) -> None:
        self._state = SystemState.NORMAL
        self._lock = threading.Lock()
        self._errors: deque[float] = deque()  # timestamps des erreurs récentes
        self._last_error_ts: float = 0.0
        self._recovery_started: float = 0.0
        self._callbacks: list[Callable[[SystemState, SystemState], None]] = []
        self._fault_counts: dict[str, int] = {}

        self._thr_degraded = degraded_threshold
        self._thr_critical = critical_threshold
        self._thr_safe = safe_threshold
        self._window_s = window_s
        self._silence_s = silence_s
        self._stability_s = stability_s
        self._clock = _clock or time.time

    # ── Observabilité ─────────────────────────────────────────────────────────

    @property
    def state(self) -> SystemState:
        with self._lock:
            return self._state

    @property
    def can_trade(self) -> bool:
        return _POLICIES[self.state][0]

    @property
    def can_fetch_data(self) -> bool:
        return _POLICIES[self.state][1]

    @property
    def size_factor(self) -> float:
        return _POLICIES[self.state][2]

    @property
    def error_count(self) -> int:
        """Nombre d'erreurs dans la fenêtre courante."""
        with self._lock:
            self._evict(self._clock())
            return len(self._errors)

    @property
    def fault_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._fault_counts)

    def on_transition(self, fn: Callable[[SystemState, SystemState], None]) -> None:
        """Enregistre un callback appelé à chaque transition (old_state, new_state)."""
        self._callbacks.append(fn)

    # ── API publique ───────────────────────────────────────────────────────────

    def report_error(self, fault_type: str = "generic") -> SystemState:
        """Signale une erreur. Peut déclencher une transition vers un état dégradé."""
        with self._lock:
            now = self._clock()
            self._errors.append(now)
            self._last_error_ts = now
            self._fault_counts[fault_type] = self._fault_counts.get(fault_type, 0) + 1
            self._evict(now)
            self._evaluate_degradation(now)
            return self._state

    def report_ok(self) -> SystemState:
        """
        Signale un tick de bonne santé.
        Déclenche RECOVERY si le silence est suffisant, NORMAL si stable.
        """
        with self._lock:
            now = self._clock()
            self._evict(now)
            silence = (
                now - self._last_error_ts if self._last_error_ts > 0 else float("inf")
            )

            if self._state == SystemState.RECOVERY:
                if (now - self._recovery_started) >= self._stability_s:
                    self._set_state(SystemState.NORMAL, now)

            elif self._state in (SystemState.DEGRADED, SystemState.CRITICAL):
                if len(self._errors) == 0 and silence >= self._silence_s:
                    self._set_state(SystemState.RECOVERY, now)
                    self._recovery_started = now

            elif self._state == SystemState.SAFE_MODE:
                # SAFE_MODE exige le double du silence standard
                if len(self._errors) == 0 and silence >= self._silence_s * 2:
                    self._set_state(SystemState.RECOVERY, now)
                    self._recovery_started = now

            return self._state

    def force_safe_mode(self, reason: str = "manual") -> None:
        """Override manuel → SAFE_MODE immédiat."""
        with self._lock:
            _log.critical("[RSM] SAFE_MODE forcé — %s", reason)
            self._set_state(SystemState.SAFE_MODE, self._clock())

    def force_recovery(self) -> None:
        """Override manuel → RECOVERY immédiat (suppose incidents résolus)."""
        with self._lock:
            now = self._clock()
            self._errors.clear()
            self._last_error_ts = 0.0
            self._set_state(SystemState.RECOVERY, now)
            self._recovery_started = now

    def reset(self) -> None:
        """Remet tout à zéro → NORMAL. Utile pour les tests."""
        with self._lock:
            self._errors.clear()
            self._last_error_ts = 0.0
            self._recovery_started = 0.0
            self._fault_counts.clear()
            self._state = SystemState.NORMAL

    def snapshot(self) -> dict:
        with self._lock:
            now = self._clock()
            self._evict(now)
            return {
                "state": self._state.value,
                "can_trade": _POLICIES[self._state][0],
                "can_fetch_data": _POLICIES[self._state][1],
                "size_factor": _POLICIES[self._state][2],
                "error_count_window": len(self._errors),
                "fault_counts": dict(self._fault_counts),
                "last_error_ago_s": (
                    round(now - self._last_error_ts, 1) if self._last_error_ts else None
                ),
            }

    # ── Internals ──────────────────────────────────────────────────────────────

    def _evict(self, now: float) -> None:
        cutoff = now - self._window_s
        while self._errors and self._errors[0] < cutoff:
            self._errors.popleft()

    def _evaluate_degradation(self, now: float) -> None:
        """Calcule la transition montante (vers plus dégradé). Appelé sous lock."""
        count = len(self._errors)

        if count >= self._thr_safe:
            if self._state != SystemState.SAFE_MODE:
                self._set_state(SystemState.SAFE_MODE, now)
        elif count >= self._thr_critical:
            if self._state not in (SystemState.CRITICAL, SystemState.SAFE_MODE):
                self._set_state(SystemState.CRITICAL, now)
        elif count >= self._thr_degraded:
            if self._state in (SystemState.NORMAL, SystemState.RECOVERY):
                self._set_state(SystemState.DEGRADED, now)

    def _set_state(self, new: SystemState, now: float) -> None:
        old = self._state
        if old == new:
            return
        self._state = new
        _log.warning(
            "[RSM] %s → %s (errors_in_window=%d)",
            old.value,
            new.value,
            len(self._errors),
        )
        for cb in self._callbacks:
            try:
                cb(old, new)
            except Exception:
                pass
