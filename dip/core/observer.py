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

from observability.json_logger import get_logger

if TYPE_CHECKING:
    from observability.decision_observation import DecisionObservation


_log = get_logger("dip.core.observer")

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
        # S-03B-R1: observations à provenance invalide (packet_id vide ou
        # provenance_valid=False) ne sont jamais distribuées aux modules DIP
        # (dip/modules/decision_graph.py dérive graph_id=f"graph_{packet_id}",
        # non joignable si packet_id est vide) — comptées séparément pour
        # S-03C.
        self._skipped_invalid_provenance = 0

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
        # S-03B-R1: garde de provenance à l'ingress DIP — miroir de
        # RejectionStore/RegretScheduler.on_observation. AVANT (blocker MASTER
        # S-03B-R1 §3) : une observation à packet_id vide était quand même
        # distribuée aux handlers DIP, qui en dérivent des identités de graphe
        # non joignables (graph_{packet_id} -> "graph_"). APRÈS : jamais
        # distribuée, comptée séparément. Ne redesigne pas DIP, ne touche pas
        # l'isolation try/except par handler ci-dessous.
        if not getattr(obs, "packet_id", "") or not getattr(
            obs, "provenance_valid", True
        ):
            with self._hlock:
                self._skipped_invalid_provenance += 1
            _log.warning(
                "[DIPObserver] Skip — provenance invalide (packet_id=%r, "
                "observation_id=%s, symbol=%s, cycle=%s)",
                getattr(obs, "packet_id", ""),
                getattr(obs, "observation_id", ""),
                getattr(obs, "symbol", ""),
                getattr(obs, "cycle", ""),
            )
            return

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

    def get_stats(self) -> dict:
        """Compteurs observables S-03B-R1 (S-03C)."""
        with self._hlock:
            return {
                "handler_count": len(self._handlers),
                "skipped_invalid_provenance": self._skipped_invalid_provenance,
            }
