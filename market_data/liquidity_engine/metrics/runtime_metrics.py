from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class RuntimeMetrics:
    messages_received: int = 0
    messages_processed: int = 0
    messages_rejected: int = 0
    big_trades_detected: int = 0
    reconnect_count: int = 0
    websocket_latency_ms: deque[float] = field(default_factory=lambda: deque(maxlen=5000))
    processing_latency_ms: deque[float] = field(default_factory=lambda: deque(maxlen=5000))
    queue_depth: int = 0
    dropped_events: int = 0
    dropped_noncritical_events: int = 0
    dropped_critical_events: int = 0

    def record_ws_latency(self, latency_ms: float) -> None:
        if latency_ms >= 0:
            self.websocket_latency_ms.append(latency_ms)

    def record_processing_latency(self, latency_ms: float) -> None:
        if latency_ms >= 0:
            self.processing_latency_ms.append(latency_ms)

    @property
    def websocket_latency_avg(self) -> float:
        if not self.websocket_latency_ms:
            return 0.0
        return sum(self.websocket_latency_ms) / len(self.websocket_latency_ms)

    @property
    def processing_latency_avg(self) -> float:
        if not self.processing_latency_ms:
            return 0.0
        return sum(self.processing_latency_ms) / len(self.processing_latency_ms)

    def as_dict(self) -> dict:
        return {
            "messages_received": self.messages_received,
            "messages_processed": self.messages_processed,
            "messages_rejected": self.messages_rejected,
            "big_trades_detected": self.big_trades_detected,
            "reconnect_count": self.reconnect_count,
            "websocket_latency_avg": round(self.websocket_latency_avg, 3),
            "processing_latency_avg": round(self.processing_latency_avg, 3),
            "queue_depth": self.queue_depth,
            "dropped_events": self.dropped_events,
            "dropped_noncritical_events": self.dropped_noncritical_events,
            "dropped_critical_events": self.dropped_critical_events,
        }
