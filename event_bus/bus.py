"""
EventBus — bus d'événements central, singleton thread-safe avec support async.

Usage:
    bus = EventBus.get()

    # Abonnement synchrone
    bus.subscribe(OrderFilledEvent, lambda e: print(e.symbol))

    # Abonnement asynchrone
    bus.subscribe_async(TrendChangeEvent, my_async_handler)

    # Wildcard (tout reçoit)
    bus.subscribe_all(audit_logger)

    # Émission
    bus.emit(OrderFilledEvent(symbol="BTC/USDT", side="buy", size=0.01))

    # Replay des 50 derniers CrashEvent
    crashes = bus.replay(CrashEvent, last_n=50)

    # Stats
    print(bus.stats())   # {"OrderFilledEvent": 42, "TrendChangeEvent": 7, ...}
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict, deque
from pathlib import Path
from typing import Callable, Coroutine, TypeVar

from event_bus.events import BaseEvent
from observability.json_logger import get_logger

_log = get_logger("event_bus.bus")
E = TypeVar("E", bound=BaseEvent)

_REPLAY_BUFFER_SIZE = 2000


class EventBus:
    """Bus d'événements central — singleton thread-safe."""

    _instance: EventBus | None = None
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._sync_handlers: dict[type, list[Callable]] = defaultdict(list)
        self._async_handlers: dict[type, list[Callable]] = defaultdict(list)
        self._wildcard_sync: list[Callable] = []
        self._wildcard_async: list[Callable] = []
        self._replay: deque[BaseEvent] = deque(maxlen=_REPLAY_BUFFER_SIZE)
        self._stats: dict[str, int] = defaultdict(int)
        self._dead_letters: list[BaseEvent] = []
        self._rw_lock = threading.RLock()
        self._audit_path: Path | None = None

    # ── Singleton ─────────────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> EventBus:
        """Retourne l'instance singleton (thread-safe, double-check locking)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Recrée l'instance — réservé aux tests."""
        with cls._instance_lock:
            cls._instance = None

    # ── Configuration ─────────────────────────────────────────────────────────

    def configure_audit(self, path: Path | str) -> None:
        """Active la persistance JSONL (une ligne JSON par événement)."""
        self._audit_path = Path(path)
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        _log.info("EventBus: audit activé → %s", self._audit_path)

    # ── Abonnements ───────────────────────────────────────────────────────────

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """Abonne un handler synchrone à un type d'événement précis."""
        with self._rw_lock:
            handlers = self._sync_handlers[event_type]
            if handler not in handlers:
                handlers.append(handler)
                _log.debug(
                    "EventBus.subscribe: %s → %s",
                    event_type.__name__,
                    getattr(handler, "__name__", repr(handler)),
                )

    def subscribe_async(
        self, event_type: type[E], handler: Callable[[E], Coroutine]
    ) -> None:
        """Abonne un handler asynchrone (coroutine) à un type d'événement."""
        with self._rw_lock:
            handlers = self._async_handlers[event_type]
            if handler not in handlers:
                handlers.append(handler)

    def subscribe_all(self, handler: Callable[[BaseEvent], None]) -> None:
        """Wildcard sync — reçoit TOUS les événements (idéal pour audit, logging)."""
        with self._rw_lock:
            if handler not in self._wildcard_sync:
                self._wildcard_sync.append(handler)

    def subscribe_all_async(self, handler: Callable[[BaseEvent], Coroutine]) -> None:
        """Wildcard async — reçoit TOUS les événements de façon asynchrone."""
        with self._rw_lock:
            if handler not in self._wildcard_async:
                self._wildcard_async.append(handler)

    def unsubscribe(self, event_type: type[E], handler: Callable) -> None:
        """Désabonne un handler d'un type d'événement."""
        with self._rw_lock:
            self._sync_handlers[event_type] = [
                h for h in self._sync_handlers[event_type] if h is not handler
            ]
            self._async_handlers[event_type] = [
                h for h in self._async_handlers[event_type] if h is not handler
            ]

    # ── Émission ──────────────────────────────────────────────────────────────

    def emit(self, event: BaseEvent) -> None:
        """
        Émet un événement vers tous les abonnés.

        Thread-safe. Les handlers sync sont appelés immédiatement.
        Les handlers async sont schedulés sur la loop asyncio active si présente.
        """
        event_type = type(event)

        with self._rw_lock:
            sync_h = list(self._sync_handlers.get(event_type, []))
            async_h = list(self._async_handlers.get(event_type, []))
            wildcards = list(self._wildcard_sync)
            async_wildcards = list(self._wildcard_async)

        # Buffer replay + stats (avant dispatch pour être disponibles même si handler crash)
        self._replay.append(event)
        self._stats[event_type.__name__] += 1

        # Handlers synchrones
        for handler in sync_h + wildcards:
            try:
                handler(event)
            except Exception as exc:
                _log.error(
                    "EventBus handler %s a crashé sur %s: %s",
                    getattr(handler, "__name__", "?"),
                    event_type.__name__,
                    exc,
                )

        # Handlers asynchrones — schedule sur la loop active si dispo
        if async_h or async_wildcards:
            try:
                loop = asyncio.get_running_loop()
                for handler in async_h + async_wildcards:
                    loop.create_task(
                        _safe_async_call(handler, event),
                        name=f"event_{event_type.__name__}",
                    )
            except RuntimeError:
                pass  # Pas de loop active — les handlers async sont ignorés

        # Dead letter: personne n'écoutait
        if not sync_h and not async_h and not wildcards and not async_wildcards:
            self._dead_letters.append(event)
            _log.debug("EventBus dead letter: %s", event_type.__name__)

        # Audit JSONL
        if self._audit_path:
            self._write_audit(event)

    async def emit_async(self, event: BaseEvent) -> None:
        """
        Version async de emit — attend la completion des handlers async.
        Utiliser dans les contextes asyncio quand on veut attendre les résultats.
        """
        event_type = type(event)

        with self._rw_lock:
            sync_h = list(self._sync_handlers.get(event_type, []))
            async_h = list(self._async_handlers.get(event_type, []))
            wildcards = list(self._wildcard_sync)
            async_wildcards = list(self._wildcard_async)

        self._replay.append(event)
        self._stats[event_type.__name__] += 1

        for handler in sync_h + wildcards:
            try:
                handler(event)
            except Exception as exc:
                _log.error("EventBus sync handler: %s", exc)

        coros = [_safe_async_call(h, event) for h in async_h + async_wildcards]
        if coros:
            await asyncio.gather(*coros)

        if self._audit_path:
            self._write_audit(event)

    # ── Replay & inspection ───────────────────────────────────────────────────

    def replay(
        self,
        event_type: type[E] | None = None,
        last_n: int = 100,
    ) -> list[BaseEvent]:
        """Retourne les N derniers événements, filtrés par type optionnel."""
        events = list(self._replay)
        if event_type is not None:
            events = [e for e in events if isinstance(e, event_type)]
        return events[-last_n:]

    def stats(self) -> dict[str, int]:
        """Nombre d'émissions par type d'événement."""
        return dict(self._stats)

    def dead_letters(self) -> list[BaseEvent]:
        """Événements émis sans aucun abonné."""
        return list(self._dead_letters)

    def subscriber_count(self, event_type: type | None = None) -> int:
        """Nombre d'abonnés pour un type, ou total."""
        with self._rw_lock:
            if event_type is not None:
                return len(self._sync_handlers.get(event_type, [])) + len(
                    self._async_handlers.get(event_type, [])
                )
            total = sum(len(v) for v in self._sync_handlers.values()) + sum(
                len(v) for v in self._async_handlers.values()
            )
            return total + len(self._wildcard_sync) + len(self._wildcard_async)

    def clear_dead_letters(self) -> int:
        n = len(self._dead_letters)
        self._dead_letters.clear()
        return n

    # ── Audit ─────────────────────────────────────────────────────────────────

    def _write_audit(self, event: BaseEvent) -> None:
        try:
            line = json.dumps(event.to_dict(), ensure_ascii=False, default=str) + "\n"
            with open(self._audit_path, "a", encoding="utf-8") as f:  # type: ignore[arg-type]
                f.write(line)
        except Exception as exc:
            _log.debug("EventBus audit write failed: %s", exc)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _safe_async_call(handler: Callable, event: BaseEvent) -> None:
    try:
        await handler(event)
    except Exception as exc:
        _log.error(
            "EventBus async handler %s a crashé: %s",
            getattr(handler, "__name__", "?"),
            exc,
        )
