"""
dip/core/types.py — Types fondamentaux partagés par tous les modules DIP.

Principes:
  - Tous les dataclasses sont frozen=True (immuabilité)
  - Les timestamps sont en microsecondes UTC (int)
  - Les scores/forces sont dans [0.0, 1.0]
  - Aucune référence aux objets du moteur de décision

Input principal: DecisionObservation (observability.decision_observation)
Le DIP consomme le bus existant tel quel — pas d'événements per-layer requis.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

# ── Enums ─────────────────────────────────────────────────────────────────────


class DecisionStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


class LayerStatus(str, Enum):
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    UNKNOWN = "UNKNOWN"


class CausalType(str, Enum):
    TRANSFORM = "TRANSFORM"  # couche modifie le score
    GATE = "GATE"  # couche bloque ou laisse passer
    AMPLIFY = "AMPLIFY"  # couche amplifie le signal
    REDUCE = "REDUCE"  # couche réduit le signal


class TrendDirection(str, Enum):
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    STABLE = "STABLE"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


class InsightType(str, Enum):
    HOT_SPOT = "HOT_SPOT"
    COLD_SPOT = "COLD_SPOT"
    ANOMALY = "ANOMALY"
    TREND_SHIFT = "TREND_SHIFT"


class KnowledgeType(str, Enum):
    REJECTION_CLUSTER = "REJECTION_CLUSTER"
    APPROVAL_PATTERN = "APPROVAL_PATTERN"
    TEMPORAL_PATTERN = "TEMPORAL_PATTERN"
    REGIME_PATTERN = "REGIME_PATTERN"


class ScenarioType(str, Enum):
    LAYER_REMOVAL = "LAYER_REMOVAL"
    THRESHOLD_CHANGE = "THRESHOLD_CHANGE"
    CONTEXT_OVERRIDE = "CONTEXT_OVERRIDE"


class HeatmapType(str, Enum):
    SYMBOL_LAYER = "SYMBOL_LAYER"
    REGIME_LAYER = "REGIME_LAYER"
    HOURLY_LAYER = "HOURLY_LAYER"
    LAYER_REJECTION = "LAYER_REJECTION"


class SankeyNodeType(str, Enum):
    SOURCE = "SOURCE"
    LAYER = "LAYER"
    REJECTION = "REJECTION"
    SINK = "SINK"


class ReplayStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StepStatus(str, Enum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    INCOMPLETE = "INCOMPLETE"


# ── Couches canoniques (dans l'ordre d'évaluation) ────────────────────────────

LAYER_ORDER: list[str] = [
    "authority",
    "meta_strategy",
    "gate",
    "awareness",
    "conviction",
    "no_trade",
    "portfolio",
    "capital_allocation",
    "mistake_memory",
    "executive_override",
    "threat_radar",
    "arbitrator",
]

LAYER_DISPLAY: dict[str, str] = {
    "authority": "Authority",
    "meta_strategy": "MetaStrategy",
    "gate": "Gate",
    "awareness": "SelfAwareness",
    "conviction": "ConvictionEngine",
    "no_trade": "NoTradeLayer",
    "portfolio": "PortfolioBrain",
    "capital_allocation": "CapitalAllocation",
    "mistake_memory": "MistakeMemory",
    "executive_override": "ExecutiveOverride",
    "threat_radar": "ThreatRadar",
    "arbitrator": "Arbitrator",
}


# ── TimeRange ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TimeRange:
    start_us: int
    end_us: int

    def duration_us(self) -> int:
        return self.end_us - self.start_us

    @staticmethod
    def last_hours(n: int) -> "TimeRange":
        now = int(time.time() * 1_000_000)
        return TimeRange(start_us=now - n * 3_600_000_000, end_us=now)


# ── Intégrité ──────────────────────────────────────────────────────────────────


def compute_hash(data: Any) -> str:
    """SHA-256 du contenu JSON sérialisé."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def now_us() -> int:
    """Timestamp courant en microsecondes UTC."""
    return int(time.time() * 1_000_000)
