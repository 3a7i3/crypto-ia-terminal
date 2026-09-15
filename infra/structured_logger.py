"""Logger structuré JSON — chaque événement critique est traçable."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional


class StructuredLogger:
    """Logger produisant des événements JSON standardisés."""

    def __init__(self, name: str = "crypto_ai"):
        self._logger = logging.getLogger(name)

    def log_event(self, event: dict[str, Any]) -> None:
        """Émettre un événement structuré.

        Format attendu:
        {
            "trace_id": "...",
            "decision_id": "...",
            "symbol": "BTCUSDT",
            "regime": "TRENDING",
            "signal_direction": "LONG",
            "confidence": 0.82,
            "risk_state": "APPROVED",
            "execution_status": "SENT",
            "timestamp": "2026-05-28T04:00:00Z",
            "module": "GlobalRiskGate",
            "duration_ms": 45,
        }
        """
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._logger.info(json.dumps(event, default=str))

    def decision_created(self, packet) -> None:
        self.log_event({
            "event_type": "DECISION_CREATED",
            "trace_id": packet.trace_id,
            "symbol": packet.symbol,
            "direction": packet.direction,
            "confidence": packet.confidence,
        })

    def decision_approved(self, packet, module: str) -> None:
        self.log_event({
            "event_type": "DECISION_APPROVED",
            "trace_id": packet.trace_id,
            "symbol": packet.symbol,
            "approved_by": module,
            "duration_ms": packet.duration_ms,
        })

    def decision_rejected(self, packet, module: str, reason: str) -> None:
        self.log_event({
            "event_type": "DECISION_REJECTED",
            "trace_id": packet.trace_id,
            "symbol": packet.symbol,
            "rejected_by": module,
            "reason": reason,
        })

    def order_executed(self, order, packet) -> None:
        self.log_event({
            "event_type": "ORDER_EXECUTED",
            "trace_id": packet.trace_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "price": order.price,
            "fee": order.fee,
        })
