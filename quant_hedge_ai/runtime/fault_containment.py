"""
fault_containment.py — Zones d'isolation entre composants du runtime.

Garantit qu'une panne dans une zone basse ne peut jamais bloquer une zone haute.

Zones (priorité décroissante) :
    EXECUTION   timeout=200ms  échec → reject silencieux
    RISK        timeout=100ms  échec → ordre rejeté
    AI_SCORING  timeout=500ms  échec → fallback retourné
    MONITORING  timeout=2s     échec → silencieux
    DASHBOARD   timeout=5s     échec → totalement ignoré

Usage :
    # Décorateur
    @contained(zone=Zone.MONITORING, timeout_s=1.0)
    def push_metric(name: str, value: float) -> None:
        ...

    # Context manager avec fallback
    with ContainmentZone(Zone.AI_SCORING, timeout_s=0.5, fallback="HOLD") as zone:
        signal = engine.evaluate(symbol)
        zone.result = signal
    final_signal = zone.result  # "HOLD" si timeout/crash

    # Intégration state machine
    guard = ContainmentGuard(state_machine)
    result = guard.run(Zone.RISK, my_risk_fn, arg1, arg2, fallback=False)
"""

from __future__ import annotations

import functools
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, TypeVar

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.runtime.fault_containment")
_F = TypeVar("_F", bound=Callable[..., Any])


class Zone(str, Enum):
    EXECUTION = "EXECUTION"  # chemin critique absolu
    RISK = "RISK"  # checks de risque
    AI_SCORING = "AI_SCORING"  # scoring signal / régime
    MONITORING = "MONITORING"  # métriques / journal
    DASHBOARD = "DASHBOARD"  # UI / Telegram


# Timeouts par zone (secondes).
# EXECUTION est le plus court : chemin purement interne (pas d'I/O exchange).
# Les appels réseau vers l'exchange ont leurs propres timeouts en dehors de cette zone.
_ZONE_TIMEOUTS: dict[Zone, float] = {
    Zone.EXECUTION: 0.050,  # 50ms — interne uniquement
    Zone.RISK: 0.100,  # 100ms — calculs en mémoire
    Zone.AI_SCORING: 0.500,  # 500ms — inférence modèle
    Zone.MONITORING: 2.000,  # 2s — métriques / journal
    Zone.DASHBOARD: 5.000,  # 5s — UI / Telegram
}

# Priorité numérique (plus bas = plus critique)
_ZONE_PRIORITY: dict[Zone, int] = {
    Zone.EXECUTION: 0,
    Zone.RISK: 1,
    Zone.AI_SCORING: 2,
    Zone.MONITORING: 3,
    Zone.DASHBOARD: 4,
}


@dataclass
class ContainmentResult:
    zone: Zone
    success: bool
    value: Any
    elapsed_ms: float
    error: str | None = None  # message d'erreur si success=False
    timed_out: bool = False


def _run_with_timeout(
    fn: Callable,
    timeout_s: float,
    args: tuple,
    kwargs: dict,
) -> tuple[bool, Any, float, str | None, bool]:
    """
    Exécute fn(*args, **kwargs) dans un thread avec timeout.
    Retourne (success, result, elapsed_ms, error_msg, timed_out).
    """
    result: list[Any] = [None]
    exc: list[BaseException | None] = [None]

    def _worker() -> None:
        try:
            result[0] = fn(*args, **kwargs)
        except Exception as e:
            exc[0] = e

    t0 = time.perf_counter()
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    if t.is_alive():
        return False, None, elapsed_ms, f"timeout after {timeout_s:.3f}s", True
    if exc[0] is not None:
        return False, None, elapsed_ms, str(exc[0]), False
    return True, result[0], elapsed_ms, None, False


# ── API principale ─────────────────────────────────────────────────────────────


def contained(
    zone: Zone,
    timeout_s: float | None = None,
    fallback: Any = None,
    state_machine=None,
) -> Callable[[_F], _F]:
    """
    Décorateur : enveloppe une fonction dans sa zone d'isolation.

    Args:
        zone:         Zone d'isolation de la fonction.
        timeout_s:    Override du timeout par défaut de la zone.
        fallback:     Valeur retournée si timeout ou exception.
        state_machine: RuntimeStateMachine optionnel (reçoit report_error si échec).
    """
    _timeout = timeout_s or _ZONE_TIMEOUTS[zone]

    def decorator(fn: _F) -> _F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            success, value, elapsed_ms, error, timed_out = _run_with_timeout(
                fn, _timeout, args, kwargs
            )
            if not success:
                _log.warning(
                    "[Containment/%s] %s échec en %.1fms — %s",
                    zone.value,
                    fn.__qualname__,
                    elapsed_ms,
                    error,
                )
                if state_machine is not None:
                    state_machine.report_error(f"containment_{zone.value.lower()}")
                return fallback
            return value

        return wrapper  # type: ignore[return-value]

    return decorator


class ContainmentZone:
    """
    Context manager pour exécuter un bloc de code dans une zone d'isolation.

    Usage :
        with ContainmentZone(Zone.AI_SCORING, timeout_s=0.5, fallback="HOLD") as z:
            z.result = engine.evaluate(symbol)
        signal = z.result   # "HOLD" si timeout ou exception
    """

    def __init__(
        self,
        zone: Zone,
        timeout_s: float | None = None,
        fallback: Any = None,
        state_machine=None,
    ) -> None:
        self.zone = zone
        self._timeout = timeout_s or _ZONE_TIMEOUTS[zone]
        self.fallback = fallback
        self._sm = state_machine
        self.result: Any = fallback
        self.success: bool = True
        self.error: str | None = None
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "ContainmentZone":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.elapsed_ms = (time.perf_counter() - self._t0) * 1000.0
        if exc_type is not None:
            self.success = False
            self.error = str(exc_val)
            self.result = self.fallback
            _log.warning(
                "[Containment/%s] Exception absorbée en %.1fms: %s",
                self.zone.value,
                self.elapsed_ms,
                exc_val,
            )
            if self._sm is not None:
                self._sm.report_error(f"containment_{self.zone.value.lower()}")
            return True  # supprime l'exception
        return False


class ContainmentGuard:
    """
    Façade combinant zones + state machine : exécute une fonction dans sa zone
    et reporte automatiquement les pannes à la state machine.

    Usage :
        guard = ContainmentGuard(state_machine)
        signal = guard.run(Zone.AI_SCORING, engine.evaluate, symbol, fallback="HOLD")
    """

    def __init__(self, state_machine) -> None:
        self._sm = state_machine

    def run(
        self,
        zone: Zone,
        fn: Callable,
        *args,
        timeout_s: float | None = None,
        fallback: Any = None,
        **kwargs,
    ) -> Any:
        """
        Exécute fn(*args, **kwargs) dans la zone.
        Reporte l'erreur à la state machine si échec.
        Retourne `fallback` en cas de timeout ou exception.
        """
        _timeout = timeout_s or _ZONE_TIMEOUTS[zone]
        success, value, elapsed_ms, error, timed_out = _run_with_timeout(
            fn, _timeout, args, kwargs
        )
        if not success:
            _log.warning(
                "[Guard/%s] %s — %.1fms — %s",
                zone.value,
                fn.__qualname__,
                elapsed_ms,
                error,
            )
            self._sm.report_error(f"containment_{zone.value.lower()}")
            return fallback
        return value

    def result_for(
        self, zone: Zone, fn: Callable, *args, **kwargs
    ) -> ContainmentResult:
        """Comme run() mais retourne un ContainmentResult complet (pour métriques)."""
        _timeout = _ZONE_TIMEOUTS[zone]
        success, value, elapsed_ms, error, timed_out = _run_with_timeout(
            fn, _timeout, args, kwargs
        )
        if not success:
            self._sm.report_error(f"containment_{zone.value.lower()}")
        return ContainmentResult(
            zone=zone,
            success=success,
            value=value if success else None,
            elapsed_ms=elapsed_ms,
            error=error,
            timed_out=timed_out,
        )


# ── Utilitaires ────────────────────────────────────────────────────────────────


def zone_timeout(zone: Zone) -> float:
    """Retourne le timeout par défaut de la zone en secondes."""
    return _ZONE_TIMEOUTS[zone]


def is_higher_priority(zone_a: Zone, zone_b: Zone) -> bool:
    """Retourne True si zone_a est plus prioritaire (plus critique) que zone_b."""
    return _ZONE_PRIORITY[zone_a] < _ZONE_PRIORITY[zone_b]
