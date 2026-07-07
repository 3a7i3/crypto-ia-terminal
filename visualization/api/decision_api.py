"""Decision API — expose DecisionTraceService à la SDOS Data API.

Adaptateur mince : toute la logique d'agrégation et de reconstruction causale
vit dans visualization/decision_trace_service.py (partagée avec
tools/decision_trace.py).
"""

from __future__ import annotations

from typing import Optional

from visualization.decision_trace_service import (
    DecisionTrace,
    DecisionTraceService,
    RejectionsSnapshot,
)

_service = DecisionTraceService()


def load_rejections_snapshot(days: int = 1, limit: int = 20) -> RejectionsSnapshot:
    return _service.rejections(days=days, limit=limit)


def load_decision_packet(packet_id: str, days: int = 7) -> Optional[DecisionTrace]:
    return _service.trace(packet_id, days=days)
