"""
system_state_bus.py — Bus d'événements interne (B-04)

Tous les composants publient leur état et s'abonnent aux états des autres.
Thread-safe. Garantie de livraison best-effort : une exception dans un handler
n'empêche pas la livraison aux autres handlers (dead letter queue).
Saturation détectée si _message_counts[channel] > _MAX_QUEUE_SIZE.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("runtime.system_state_bus")

_MAX_QUEUE_SIZE = int(os.getenv("P10_BUS_MAX_QUEUE", "1000"))

# ── Canaux standards ──────────────────────────────────────────────────────────

CHANNEL_SYSTEM_BOOT = "system:boot"
CHANNEL_SYSTEM_CYCLE = "system:cycle"
CHANNEL_SYSTEM_SHUTDOWN = "system:shutdown"
CHANNEL_RISK_STATE_CHANGE = "risk:state_change"
CHANNEL_RISK_THRESHOLD = "risk:threshold_breach"
CHANNEL_REGIME_TRANSITION = "regime:transition"
CHANNEL_REGIME_PREDICTION = "regime:new_prediction"
CHANNEL_ORDER_SENT = "execution:order_sent"
CHANNEL_ORDER_FILLED = "execution:order_filled"
CHANNEL_ANOMALY_SUSPECTED = "anomaly:suspected"
CHANNEL_ANOMALY_CONFIRMED = "anomaly:confirmed"

STANDARD_CHANNELS: frozenset[str] = frozenset(
    {
        CHANNEL_SYSTEM_BOOT,
        CHANNEL_SYSTEM_CYCLE,
        CHANNEL_SYSTEM_SHUTDOWN,
        CHANNEL_RISK_STATE_CHANGE,
        CHANNEL_RISK_THRESHOLD,
        CHANNEL_REGIME_TRANSITION,
        CHANNEL_REGIME_PREDICTION,
        CHANNEL_ORDER_SENT,
        CHANNEL_ORDER_FILLED,
        CHANNEL_ANOMALY_SUSPECTED,
        CHANNEL_ANOMALY_CONFIRMED,
    }
)


class _DeadLetterEntry:
    __slots__ = ("channel", "message", "handler_name", "error", "ts")

    def __init__(
        self, channel: str, message: dict, handler_name: str, error: str
    ) -> None:
        self.channel = channel
        self.message = message
        self.handler_name = handler_name
        self.error = error
        self.ts = time.time()

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "handler": self.handler_name,
            "error": self.error,
            "ts": round(self.ts, 3),
        }


class SystemStateBus:
    """
    Bus d'événements interne pub/sub.

    - Thread-safe via verrou interne.
    - Garantie de livraison best-effort : tous les handlers reçoivent le message
      même si l'un d'eux lève une exception.
    - Dead letter queue (100 dernières erreurs).
    - Détection saturation par canal.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._last_state: dict[str, dict] = {}
        self._message_counts: dict[str, int] = defaultdict(int)
        self._dead_letters: deque[_DeadLetterEntry] = deque(maxlen=100)
        self._total_published: int = 0

    # ── API publique ──────────────────────────────────────────────────────────

    def publish(self, channel: str, message: dict) -> int:
        """
        Publie un message sur un canal.
        Retourne le nombre de handlers notifiés avec succès.
        Émet un warning si le canal est saturé (> _MAX_QUEUE_SIZE messages).
        """
        enriched = {**message, "_channel": channel, "_ts": time.time()}

        with self._lock:
            handlers = list(self._subscribers.get(channel, []))
            self._last_state[channel] = enriched
            self._message_counts[channel] += 1
            count = self._message_counts[channel]
            self._total_published += 1

        if count > _MAX_QUEUE_SIZE:
            _log.warning(
                "[Bus] saturation canal=%s — %d messages cumulés (max %d)",
                channel,
                count,
                _MAX_QUEUE_SIZE,
            )

        delivered = 0
        for handler in handlers:
            try:
                handler(enriched)
                delivered += 1
            except Exception as exc:
                entry = _DeadLetterEntry(
                    channel=channel,
                    message=enriched,
                    handler_name=getattr(handler, "__name__", repr(handler)),
                    error=str(exc),
                )
                with self._lock:
                    self._dead_letters.append(entry)
                _log.warning(
                    "[Bus] handler %s sur %s a échoué: %s",
                    entry.handler_name,
                    channel,
                    exc,
                )

        return delivered

    def subscribe(self, channel: str, handler: Callable) -> None:
        """Abonne un handler à un canal (idempotent)."""
        with self._lock:
            if handler not in self._subscribers[channel]:
                self._subscribers[channel].append(handler)

    def unsubscribe(self, channel: str, handler: Callable) -> bool:
        """Désabonne un handler. Retourne False si le handler n'était pas abonné."""
        with self._lock:
            try:
                self._subscribers[channel].remove(handler)
                return True
            except ValueError:
                return False

    def state(self, channel: str) -> Optional[dict]:
        """Retourne le dernier message connu d'un canal (None si jamais publié)."""
        with self._lock:
            return self._last_state.get(channel)

    def is_silent(self, channel: str, since_s: float = 60.0) -> bool:
        """True si aucun message depuis since_s secondes (ou jamais publié)."""
        last = self.state(channel)
        if last is None:
            return True
        return time.time() - last.get("_ts", 0.0) > since_s

    def subscriber_count(self, channel: str) -> int:
        with self._lock:
            return len(self._subscribers.get(channel, []))

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_published": self._total_published,
                "channels": dict(self._message_counts),
                "dead_letters": len(self._dead_letters),
                "subscribers": {
                    ch: len(hs) for ch, hs in self._subscribers.items() if hs
                },
            }

    def dead_letters(self) -> list[dict]:
        with self._lock:
            return [e.to_dict() for e in self._dead_letters]

    def reset(self) -> None:
        """Remet le bus à zéro (utile pour les tests)."""
        with self._lock:
            self._subscribers.clear()
            self._last_state.clear()
            self._message_counts.clear()
            self._dead_letters.clear()
            self._total_published = 0
