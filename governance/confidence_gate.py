"""
Confidence Gate — first filter in the decision pipeline.

Rejects signals that don't meet minimum confidence thresholds.
Thresholds are dynamic: tighter during RISK_OFF/DEGRADED, relaxed in READY.

Usage:
    from governance.confidence_gate import confidence_gate, ConfidenceLevel

    result = confidence_gate.check(signal_confidence=0.72, market_regime="trending")
    if not result.passed:
        return  # signal rejected, reason in result.reason
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from system.state_manager import SystemState, state_manager


class ConfidenceLevel(Enum):
    """Named bands used throughout the system."""

    VERY_LOW = 1  # < 0.40 — never trade
    LOW = 2  # 0.40–0.55 — only in ideal conditions
    MEDIUM = 3  # 0.55–0.70 — standard
    HIGH = 4  # 0.70–0.85 — preferred
    VERY_HIGH = 5  # > 0.85 — maximum conviction

    @staticmethod
    def from_score(score: float) -> "ConfidenceLevel":
        if score >= 0.85:
            return ConfidenceLevel.VERY_HIGH
        if score >= 0.70:
            return ConfidenceLevel.HIGH
        if score >= 0.55:
            return ConfidenceLevel.MEDIUM
        if score >= 0.40:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.VERY_LOW


# Minimum confidence per system state
_STATE_THRESHOLDS: dict[SystemState, float] = {
    SystemState.TRADING: 0.55,  # normal operations
    SystemState.READY: 0.60,  # slightly more cautious before confirmed trading
    SystemState.RISK_OFF: 0.80,  # almost no new entries allowed
    SystemState.DEGRADED: 0.80,
    SystemState.RECOVERY: 0.75,
}

# Adjustment per market regime (additive on top of state threshold)
_REGIME_ADJUSTMENT: dict[str, float] = {
    "trending": -0.05,  # trending market → slightly easier
    "range": 0.00,
    "volatile": +0.10,  # volatile → require more conviction
    "unknown": +0.05,
}

# Position size multiplier per confidence level (used by upstream sizing)
CONFIDENCE_SIZE_MULTIPLIER: dict[ConfidenceLevel, float] = {
    ConfidenceLevel.VERY_LOW: 0.00,
    ConfidenceLevel.LOW: 0.25,
    ConfidenceLevel.MEDIUM: 0.50,
    ConfidenceLevel.HIGH: 0.80,
    ConfidenceLevel.VERY_HIGH: 1.00,
}


@dataclass
class GateResult:
    passed: bool
    score: float
    level: ConfidenceLevel
    threshold: float
    reason: str
    size_multiplier: float


class ConfidenceGate:
    """
    Stateless first filter. Every signal must pass before entering the pipeline.
    """

    def check(
        self,
        signal_confidence: float,
        market_regime: str = "unknown",
        override_threshold: Optional[float] = None,
    ) -> GateResult:
        level = ConfidenceLevel.from_score(signal_confidence)
        threshold = self._threshold(market_regime, override_threshold)
        passed = signal_confidence >= threshold
        multiplier = CONFIDENCE_SIZE_MULTIPLIER[level] if passed else 0.0

        reason = (
            f"confidence {signal_confidence:.3f} >= {threshold:.3f} [{level.name}]"
            if passed
            else f"confidence {signal_confidence:.3f} < {threshold:.3f} [{level.name}] — rejected"
        )

        return GateResult(
            passed=passed,
            score=signal_confidence,
            level=level,
            threshold=threshold,
            reason=reason,
            size_multiplier=multiplier,
        )

    def _threshold(self, regime: str, override: Optional[float]) -> float:
        if override is not None:
            return override
        state = state_manager.state
        base = _STATE_THRESHOLDS.get(state, 0.70)  # safe default for unknown states
        adj = _REGIME_ADJUSTMENT.get(regime.lower(), 0.0)
        return min(max(base + adj, 0.0), 1.0)

    def current_threshold(self, regime: str = "unknown") -> float:
        return self._threshold(regime, None)


# Singleton
confidence_gate = ConfidenceGate()
