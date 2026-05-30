"""
event_journal.py — Journal d'événements append-only, léger et thread-safe.

Capture les transitions critiques du runtime (ordres, états, décisions) avec
un séquençage monotone. Stockage in-memory (ring buffer) + flush optionnel JSONL.

Ce n'est pas de l'event sourcing enterprise. C'est l'outil minimal pour :
  - rejouer un incident post-mortem,
  - auditer une décision controversée,
  - tester la reproductibilité d'un état.

Usage :
    journal = EventJournal(max_memory=500)
    journal.record("order_placed", symbol="BTC/USDT", action="BUY", size=0.1)
    journal.record("state_transition", old="NORMAL", new="DEGRADED")

    for ev in journal.since(ts):
        replay_handler(ev)
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from observability.json_logger import get_logger

_log = get_logger("quant_hedge_ai.runtime.event_journal")


@dataclass
class JournalEvent:
    event_type: str
    data: dict
    timestamp: float = field(default_factory=time.time)
    seq: int = 0

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "data": self.data,
        }


class EventJournal:
    """
    Ring buffer + fichier JSONL pour les événements critiques.

    Thread-safe. Séquence monotone globale.
    Les événements plus anciens que `max_memory` sont évincés du buffer
    mais restent dans le fichier (si persist=True).
    """

    def __init__(
        self,
        max_memory: int = 1_000,
        persist: bool = False,
        path: Path | None = None,
        _clock: Callable[[], float] | None = None,
    ) -> None:
        self._buf: deque[JournalEvent] = deque(maxlen=max_memory)
        self._seq: int = 0
        self._lock = threading.Lock()
        self._clock = _clock or time.time
        self._persist = persist
        self._path = path or Path("databases/events/journal.jsonl")
        if persist:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Écriture ───────────────────────────────────────────────────────────────

    def record(self, event_type: str, **data) -> JournalEvent:
        """Enregistre un événement. Retourne l'événement créé."""
        with self._lock:
            self._seq += 1
            ev = JournalEvent(
                event_type=event_type,
                data=data,
                timestamp=self._clock(),
                seq=self._seq,
            )
            self._buf.append(ev)
            if self._persist:
                self._flush_one(ev)
            return ev

    # ── Lecture ────────────────────────────────────────────────────────────────

    def since(self, ts: float) -> list[JournalEvent]:
        """Retourne tous les événements avec timestamp >= ts (ordre chrono)."""
        with self._lock:
            return [e for e in self._buf if e.timestamp >= ts]

    def latest(self, n: int = 10) -> list[JournalEvent]:
        """Retourne les N événements les plus récents."""
        with self._lock:
            events = list(self._buf)
            return events[-n:]

    def by_type(self, event_type: str) -> list[JournalEvent]:
        """Retourne tous les événements d'un type donné."""
        with self._lock:
            return [e for e in self._buf if e.event_type == event_type]

    def replay_since(self, ts: float, handler: Callable[[JournalEvent], None]) -> int:
        """
        Rejoue les événements depuis ts en appelant handler sur chacun.
        Retourne le nombre d'événements rejoués.
        Thread-safe : snapshot pris sous lock, replay hors lock.
        """
        events = self.since(ts)
        for ev in events:
            handler(ev)
        return len(events)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buf)

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _flush_one(self, ev: JournalEvent) -> None:
        """Append d'une ligne JSONL. Appelé sous lock."""
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev.as_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            _log.error("[Journal] flush échoué: %s", exc)

    def load_from_file(self) -> int:
        """
        Recharge les événements depuis le fichier JSONL dans le buffer.
        Utile au démarrage pour rejouer l'état. Retourne le nombre chargé.
        """
        if not self._path.exists():
            return 0
        loaded = 0
        with self._lock:
            try:
                with self._path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        d = json.loads(line)
                        ev = JournalEvent(
                            event_type=d["event_type"],
                            data=d.get("data", {}),
                            timestamp=d["timestamp"],
                            seq=d["seq"],
                        )
                        self._buf.append(ev)
                        self._seq = max(self._seq, ev.seq)
                        loaded += 1
            except (OSError, json.JSONDecodeError) as exc:
                _log.error("[Journal] load échoué: %s", exc)
        return loaded
