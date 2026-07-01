"""
dip/core/observer.py — Abonnement DIP au DecisionEventBus existant.

Le DIP s'abonne au bus en lecture seule via DecisionEventBus.subscribe().
Chaque DecisionObservation reçue est distribuée à tous les modules DIP actifs.
Aucune écriture dans le moteur de décision — conforme ADR-0007.

Usage:
    from dip.core.observer import DIPObserver
    obs = DIPObserver.instance()
    obs.start()       # s'abonne au bus
    obs.register(module)  # enregistre un module DIP
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from observability.decision_observation import DecisionObservation


# Type des handlers de module DIP
DIPHandler = Callable[["DecisionObservation"], None]


class DIPObserver:
    """
    Observateur central DIP. Subscribe au bus, distribue aux modules.

    Singleton. Thread-safe. Non-bloquant (le bus dispatch déjà en thread pool).
    """

    _instance: Optional["DIPObserver"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._handlers: list[DIPHandler] = []
        self._started = False
        self._hlock = threading.Lock()

    @classmethod
    def instance(cls) -> "DIPObserver":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def register(self, handler: DIPHandler) -> None:
        """Enregistre un module DIP pour recevoir les observations."""
        with self._hlock:
            if handler not in self._handlers:
                self._handlers.append(handler)

    def unregister(self, handler: DIPHandler) -> None:
        with self._hlock:
            try:
                self._handlers.remove(handler)
            except ValueError:
                pass

    def start(self) -> None:
        """Abonne le DIP au DecisionEventBus. Idempotent."""
        if self._started:
            return
        try:
            from observability.decision_event_bus import get_bus

            bus = get_bus()
            bus.subscribe(self._on_observation)
            self._started = True
        except ImportError:
            pass  # Bus indisponible (tests unitaires)

    def stop(self) -> None:
        if not self._started:
            return
        try:
            from observability.decision_event_bus import get_bus

            bus = get_bus()
            bus.unsubscribe(self._on_observation)
            self._started = False
        except ImportError:
            pass

    def _on_observation(self, obs: "DecisionObservation") -> None:
        """Callback reçu du bus. Distribue aux modules DIP."""
        with self._hlock:
            handlers = list(self._handlers)
        for handler in handlers:
            try:
                handler(obs)
            except Exception:
                pass  # module défaillant n'impacte pas les autres

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def handler_count(self) -> int:
        with self._hlock:
            return len(self._handlers)
