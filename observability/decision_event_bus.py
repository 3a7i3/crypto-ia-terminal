"""
observability/decision_event_bus.py — Bus pub/sub pour DecisionObservation.

Le moteur de trading publie une DecisionObservation après chaque cycle d'analyse.
Les observateurs (Telegram, RejectionStore, RegretScheduler, ACE futur) s'abonnent
au démarrage. Le moteur ne connaît aucun observateur — il publie seulement.

Dispatch asynchrone via ThreadPoolExecutor — les listeners ne bloquent jamais
le cycle de trading. Les erreurs de listener sont capturées silencieusement.

Usage:
    from observability.decision_event_bus import get_bus

    # Au démarrage
    bus = get_bus()
    bus.subscribe(telegram_listener)
    bus.subscribe(rejection_store.on_observation)

    # Dans la boucle (advisor_loop)
    bus.publish(observation)
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional

from observability.json_logger import get_logger

_log = get_logger("observability.decision_event_bus")

# Type alias pour la clarté
Listener = Callable[["DecisionObservation"], None]  # type: ignore[name-defined]


class DecisionEventBus:
    """
    Bus pub/sub léger pour DecisionObservation.

    Propriétés garanties :
    - Les listeners ne bloquent jamais le thread appelant
    - Les erreurs de listener sont capturées et loguées (jamais propagées)
    - Thread-safe pour subscribe/publish simultanés
    - Dégradation silencieuse si le pool est saturé (log warning, pas d'exception)
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._listeners: List[Listener] = []
        self._lock = threading.Lock()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._max_workers = max_workers
        self._active = False

    def start(self) -> None:
        """Démarre le pool. Appelé une fois au démarrage du moteur."""
        with self._lock:
            if not self._active:
                self._executor = ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix="obs_bus",
                )
                self._active = True
                _log.info("[EventBus] Démarré (%d workers)", self._max_workers)

    def stop(self) -> None:
        """Arrêt propre — attend la fin des listeners en cours."""
        with self._lock:
            if self._executor and self._active:
                self._executor.shutdown(wait=True)
                self._active = False
                _log.info("[EventBus] Arrêté")

    def subscribe(self, listener: Listener) -> None:
        """
        Abonne un listener. Thread-safe.
        Le listener sera appelé dans un thread séparé pour chaque observation.
        """
        name = getattr(listener, "__name__", repr(listener))
        with self._lock:
            self._listeners.append(listener)
        _log.info("[EventBus] Listener abonné: %s", name)

    def unsubscribe(self, listener: Listener) -> bool:
        """Désabonne un listener. Retourne True si trouvé et supprimé."""
        with self._lock:
            try:
                self._listeners.remove(listener)
                return True
            except ValueError:
                return False

    def publish(self, observation: "DecisionObservation") -> None:  # type: ignore
        """
        Publie une observation vers tous les listeners.

        Non-bloquant : chaque listener est exécuté dans le ThreadPoolExecutor.
        Si le bus n'est pas démarré, démarre automatiquement (lazy init).
        """
        if not self._listeners:
            return

        if not self._active:
            self.start()

        with self._lock:
            listeners = list(self._listeners)
            executor = self._executor

        if executor is None:
            return

        for listener in listeners:
            try:
                executor.submit(self._safe_call, listener, observation)
            except RuntimeError:
                # Pool shutdown en cours
                _log.debug("[EventBus] Pool fermé, observation ignorée")
                break

    def _safe_call(
        self,
        listener: Listener,
        observation: "DecisionObservation",  # type: ignore[name-defined]
    ) -> None:
        """Appel protégé — capture toute exception du listener."""
        name = getattr(listener, "__name__", repr(listener))
        try:
            listener(observation)
        except Exception as exc:
            _log.warning("[EventBus] Listener '%s' a échoué: %s", name, exc)

    @property
    def listener_count(self) -> int:
        with self._lock:
            return len(self._listeners)

    def __repr__(self) -> str:
        return (
            f"DecisionEventBus(listeners={self.listener_count}, "
            f"active={self._active})"
        )


# ── Singleton module-level ────────────────────────────────────────────────────
# Un seul bus par processus. Partagé entre advisor_loop et les listeners.

_bus: Optional[DecisionEventBus] = None
_bus_lock = threading.Lock()


def get_bus(max_workers: int = 4) -> DecisionEventBus:
    """
    Retourne le singleton DecisionEventBus.
    Crée et démarre le bus au premier appel.
    """
    global _bus
    with _bus_lock:
        if _bus is None:
            _bus = DecisionEventBus(max_workers=max_workers)
            _bus.start()
    return _bus


# Import différé pour éviter les imports circulaires dans le builder
try:
    from observability.decision_observation import DecisionObservation  # noqa: F401
except ImportError:
    pass
