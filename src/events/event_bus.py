"""
SimEventBus — bus d'événements local pour le stack backtest/simulation.

Cycle de vie : instancié par run, jamais partagé entre runs.
Ne pas utiliser dans le runtime live — voir event_bus/bus.py (singleton thread-safe).
"""

from typing import Callable


class SimEventBus:
    """Bus d'événements local, dict-based, pour le backtest et la simulation CMVK.

    Isolation garantie : chaque instance est indépendante.
    Événements transmis comme dicts : {"type": "TRADE_OPENED", ...}
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, fn: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(fn)

    def unsubscribe(self, event_type: str, fn: Callable) -> None:
        bucket = self._subscribers.get(event_type, [])
        if fn in bucket:
            bucket.remove(fn)

    def emit(self, event: dict) -> None:
        for fn in self._subscribers.get(event.get("type", ""), []):
            fn(event)

    def clear(self) -> None:
        self._subscribers.clear()
