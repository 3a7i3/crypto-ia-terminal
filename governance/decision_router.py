"""
Decision Router — the authoritative pipeline for every trading decision.

No agent, no AI module, no strategy can bypass this router.
Every signal enters here and exits as either an approved ExecutionOrder
or a RejectedDecision with a full audit trail.

Pipeline:
    Signal
      |
      v
    ConfidenceGate       (confidence too low? reject)
      |
      v
    RiskAuthorizer       (risk limits breached? reject)
      |
      v
    ExecutionApproval    (veto? duplicate? rate limit? reject)
      |
      v
    ExecutionOrder       (approved — send to exchange)

Every step is logged with the same trace_id, stored in the DecisionLedger.

Usage:
    from governance.decision_router import decision_router, IncomingSignal

    signal = IncomingSignal(
        source="signal_engine",
        symbol="BTCUSDT",
        side="long",
        size_usd=500.0,
        confidence=0.78,
        strategy="momentum_v2",
        market_regime="trending",
        current_drawdown=0.015,
        daily_pnl=-80.0,
        portfolio_exposure_pct=0.30,
    )
    outcome = decision_router.route(signal)
    if outcome.approved:
        exchange.execute(outcome.order)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

from governance.confidence_gate import confidence_gate
from governance.execution_approval import ApprovalRequest, execution_approval
from governance.risk_authorizer import RiskContext, risk_authorizer
from observability.json_logger import get_logger
from observability.metrics_bus import metrics_bus

log = get_logger("decision_router", category="decisions")


# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------


class RejectionReason(Enum):
    CONFIDENCE_TOO_LOW = auto()
    RISK_LIMIT_BREACHED = auto()
    EXECUTION_BLOCKED = auto()
    SYSTEM_STATE = auto()


@dataclass
class IncomingSignal:
    """Everything the router needs to evaluate a trading opportunity."""

    source: str  # module that produced this signal
    symbol: str
    side: str  # "long" | "short"
    size_usd: float
    confidence: float  # 0.0–1.0
    strategy: str = ""
    market_regime: str = "unknown"
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    portfolio_exposure_pct: float = 0.0
    leverage: float = 1.0
    volatility_24h: float = 0.0
    correlation_score: float = 0.0
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionOrder:
    """Approved order — ready to send to the exchange."""

    trace_id: str
    symbol: str
    side: str
    size_usd: float
    confidence: float
    risk_score: float
    strategy: str
    approved_at: float = field(default_factory=time.time)


@dataclass
class RejectedDecision:
    trace_id: str
    symbol: str
    side: str
    reason: RejectionReason
    detail: str
    violations: List[str] = field(default_factory=list)
    rejected_at: float = field(default_factory=time.time)


@dataclass
class RoutingOutcome:
    approved: bool
    trace_id: str
    order: Optional[ExecutionOrder] = None
    rejection: Optional[RejectedDecision] = None

    # Pipeline audit trail (populated even on rejection)
    confidence_gate_result: Any = None
    risk_auth_result: Any = None
    approval_decision: Any = None

    def __bool__(self) -> bool:
        return self.approved


# ------------------------------------------------------------------
# Router
# ------------------------------------------------------------------


class DecisionRouter:
    """
    The single mandatory gateway for every trading decision.
    Thread-safe. Fully auditable. No bypass possible from user code.
    """

    def route(self, signal: IncomingSignal) -> RoutingOutcome:
        """
        Run signal through the full pipeline.
        Returns RoutingOutcome — approved or rejected with full trail.
        """
        t0 = time.time()
        log.decision(
            "signal_received",
            trace_id=signal.trace_id,
            source=signal.source,
            symbol=signal.symbol,
            side=signal.side,
            size_usd=signal.size_usd,
            confidence=signal.confidence,
            strategy=signal.strategy,
        )
        metrics_bus.increment("decision_router", "signals_received")

        # Step 1 — Confidence Gate
        cg = confidence_gate.check(signal.confidence, signal.market_regime)
        if not cg.passed:
            return self._reject(
                signal,
                RejectionReason.CONFIDENCE_TOO_LOW,
                cg.reason,
                confidence_gate_result=cg,
                duration=time.time() - t0,
            )

        # Step 2 — Risk Authorizer
        ctx = RiskContext(
            symbol=signal.symbol,
            side=signal.side,
            size_usd=signal.size_usd,
            current_drawdown=signal.current_drawdown,
            daily_pnl=signal.daily_pnl,
            portfolio_exposure_pct=signal.portfolio_exposure_pct,
            leverage=signal.leverage,
            volatility_24h=signal.volatility_24h,
            correlation_score=signal.correlation_score,
            trace_id=signal.trace_id,
        )
        auth = risk_authorizer.authorize(ctx)
        if not auth.approved:
            return self._reject(
                signal,
                RejectionReason.RISK_LIMIT_BREACHED,
                "; ".join(auth.violations),
                confidence_gate_result=cg,
                risk_auth_result=auth,
                duration=time.time() - t0,
            )

        # Step 3 — Execution Approval (final gate)
        req = ApprovalRequest(
            trace_id=signal.trace_id,
            symbol=signal.symbol,
            side=signal.side,
            size_usd=signal.size_usd * cg.size_multiplier,  # apply confidence sizing
            signal_confidence=signal.confidence,
            risk_score=auth.risk_score,
            confidence_gate_passed=True,
            risk_authorizer_passed=True,
            strategy=signal.strategy,
        )
        approval = execution_approval.request(req)
        if not approval.approved:
            return self._reject(
                signal,
                RejectionReason.EXECUTION_BLOCKED,
                approval.reason,
                confidence_gate_result=cg,
                risk_auth_result=auth,
                approval_decision=approval,
                duration=time.time() - t0,
            )

        # Approved
        order = ExecutionOrder(
            trace_id=signal.trace_id,
            symbol=signal.symbol,
            side=signal.side,
            size_usd=req.size_usd,
            confidence=signal.confidence,
            risk_score=auth.risk_score,
            strategy=signal.strategy,
        )
        outcome = RoutingOutcome(
            approved=True,
            trace_id=signal.trace_id,
            order=order,
            confidence_gate_result=cg,
            risk_auth_result=auth,
            approval_decision=approval,
        )

        duration = time.time() - t0
        log.decision(
            "order_approved",
            trace_id=signal.trace_id,
            symbol=signal.symbol,
            side=signal.side,
            size_usd=order.size_usd,
            confidence=signal.confidence,
            risk_score=auth.risk_score,
            pipeline_ms=round(duration * 1000, 1),
        )
        metrics_bus.increment("decision_router", "orders_approved")
        metrics_bus.record("decision_router", "pipeline_latency_ms", duration * 1000)
        return outcome

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reject(
        self,
        signal: IncomingSignal,
        reason: RejectionReason,
        detail: str,
        duration: float = 0.0,
        confidence_gate_result: Any = None,
        risk_auth_result: Any = None,
        approval_decision: Any = None,
    ) -> RoutingOutcome:
        violations = []
        if risk_auth_result and hasattr(risk_auth_result, "violations"):
            violations = risk_auth_result.violations

        rejection = RejectedDecision(
            trace_id=signal.trace_id,
            symbol=signal.symbol,
            side=signal.side,
            reason=reason,
            detail=detail,
            violations=violations,
        )

        log.decision(
            "signal_rejected",
            trace_id=signal.trace_id,
            symbol=signal.symbol,
            side=signal.side,
            reason=reason.name,
            detail=detail,
            pipeline_ms=round(duration * 1000, 1),
        )
        metrics_bus.increment("decision_router", f"rejected.{reason.name.lower()}")

        return RoutingOutcome(
            approved=False,
            trace_id=signal.trace_id,
            rejection=rejection,
            confidence_gate_result=confidence_gate_result,
            risk_auth_result=risk_auth_result,
            approval_decision=approval_decision,
        )


# Singleton
decision_router = DecisionRouter()
