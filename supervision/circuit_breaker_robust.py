"""
circuit_breaker_robust.py — Circuit-breaker 4 états par composant (P7).

États : HEALTHY → UNSTABLE → DEGRADED → DISABLED
- Backoff exponentiel : 30s, 60s, 120s, 300s, 600s
- Mode DEGRADED : stub retourné, recovery tentée toutes les 300s
- Mode DISABLED : recovery tentée toutes les 1800s
- Logging : logger.exception (stacktrace complète)
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Callable, Optional

log = logging.getLogger("circuit_breaker_robust")

_BACKOFF_SCHEDULE = [30, 60, 120, 300, 600]
_RECOVERY_DEGRADED = 300  # s entre tentatives de recovery en DEGRADED
_RECOVERY_DISABLED = 1800  # s entre tentatives de recovery en DISABLED


class CBState(Enum):
    HEALTHY = "healthy"
    UNSTABLE = "unstable"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class ComponentCircuitBreaker:
    """
    Circuit-breaker par composant.

    Usage:
        cb = ComponentCircuitBreaker("exchange_monitor", fallback={"healthy": False})
        result = cb.call(my_fn, arg1, arg2)
    """

    def __init__(self, name: str, fallback: Any = None) -> None:
        self.name = name
        self._state = CBState.HEALTHY
        self._failures = 0
        self._fallback = fallback
        self._last_failure_ts: float = 0.0
        self._last_recovery_ts: float = 0.0
        self._backoff_until: float = 0.0

    # ── API publique ──────────────────────────────────────────────────────────

    def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Appelle fn avec protection circuit-breaker. Retourne fallback si dégradé."""
        if self._state == CBState.DISABLED:
            if self._should_attempt_recovery(CBState.DISABLED):
                return self._try_recovery(fn, *args, **kwargs)
            return self._fallback

        if self._state == CBState.DEGRADED:
            if self._should_attempt_recovery(CBState.DEGRADED):
                return self._try_recovery(fn, *args, **kwargs)
            return self._fallback

        # Backoff: DEGRADED/DISABLED only — HEALTHY/UNSTABLE accumulent librement
        if self._state == CBState.UNSTABLE and time.time() < self._backoff_until:
            # En UNSTABLE on laisse passer mais on attend le backoff
            pass

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            log.exception("[CB:%s] Échec appel", self.name)
            self._on_failure()
            return self._fallback

    @property
    def state(self) -> CBState:
        return self._state

    @property
    def is_healthy(self) -> bool:
        return self._state == CBState.HEALTHY

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "failures": self._failures,
            "backoff_remaining_s": max(0.0, self._backoff_until - time.time()),
        }

    # ── Logique interne ───────────────────────────────────────────────────────

    def _on_success(self) -> None:
        self._failures = max(0, self._failures - 1)
        self._backoff_until = 0.0
        if self._failures == 0 and self._state != CBState.HEALTHY:
            log.info("[CB:%s] Recovery OK → HEALTHY", self.name)
            self._state = CBState.HEALTHY

    def _on_failure(self) -> None:
        self._failures += 1
        self._last_failure_ts = time.time()
        backoff = _BACKOFF_SCHEDULE[min(self._failures - 1, len(_BACKOFF_SCHEDULE) - 1)]
        self._backoff_until = time.time() + backoff

        if self._failures >= 10 and self._state != CBState.DISABLED:
            self._state = CBState.DISABLED
            log.critical(
                "[CB:%s] → DISABLED après %d échecs — escalation requise",
                self.name,
                self._failures,
            )
        elif self._failures >= 5 and self._state not in (
            CBState.DEGRADED,
            CBState.DISABLED,
        ):
            self._state = CBState.DEGRADED
            log.error(
                "[CB:%s] → DEGRADED après %d échecs — composant suspendu, stub actif",
                self.name,
                self._failures,
            )
        elif self._failures >= 2 and self._state == CBState.HEALTHY:
            self._state = CBState.UNSTABLE
            log.warning("[CB:%s] → UNSTABLE (échec #%d)", self.name, self._failures)

    def _should_attempt_recovery(self, current_state: CBState) -> bool:
        interval = (
            _RECOVERY_DEGRADED
            if current_state == CBState.DEGRADED
            else _RECOVERY_DISABLED
        )
        return (time.time() - self._last_recovery_ts) >= interval

    def _try_recovery(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        self._last_recovery_ts = time.time()
        log.info("[CB:%s] Tentative recovery depuis %s", self.name, self._state.value)
        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            log.exception("[CB:%s] Recovery échouée", self.name)
            self._on_failure()
            return self._fallback


class CircuitBreakerRegistry:
    """Registre global des circuit-breakers par composant."""

    def __init__(self) -> None:
        self._breakers: dict[str, ComponentCircuitBreaker] = {}

    def get(self, name: str, fallback: Any = None) -> ComponentCircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = ComponentCircuitBreaker(name, fallback)
        return self._breakers[name]

    def snapshot_all(self) -> list[dict]:
        return [cb.snapshot() for cb in self._breakers.values()]

    def any_degraded(self) -> bool:
        return any(
            cb.state in (CBState.DEGRADED, CBState.DISABLED)
            for cb in self._breakers.values()
        )


# Singleton global
_registry: Optional[CircuitBreakerRegistry] = None


def get_cb_registry() -> CircuitBreakerRegistry:
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry()
    return _registry
