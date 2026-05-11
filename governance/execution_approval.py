"""
Execution Approval — final gate before any order reaches the exchange.

This is the last line of defense. Nothing executes without passing through here.

Rules enforced:
  - System must be in TRADING state
  - Signal must have passed ConfidenceGate
  - Trade must have passed RiskAuthorizer
  - No duplicate orders (deduplication by signal fingerprint)
  - Rate limiter: max N approvals per minute
  - Operator VETO: manual override to block all execution

Usage:
    from governance.execution_approval import execution_approval, ApprovalRequest

    req = ApprovalRequest(
        trace_id=trace_id,
        symbol="BTCUSDT",
        side="long",
        size_usd=500.0,
        signal_confidence=0.78,
        risk_score=0.31,
        confidence_gate_passed=True,
        risk_authorizer_passed=True,
    )
    decision = execution_approval.request(req)
    if decision.approved:
        # send to exchange
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict

from observability.metrics_bus import metrics_bus
from system.state_manager import SystemState, state_manager


@dataclass
class ApprovalRequest:
    trace_id: str
    symbol: str
    side: str  # "long" | "short"
    size_usd: float
    signal_confidence: float
    risk_score: float
    confidence_gate_passed: bool
    risk_authorizer_passed: bool
    strategy: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalDecision:
    approved: bool
    trace_id: str
    reason: str
    timestamp: float = field(default_factory=time.time)

    def __bool__(self) -> bool:
        return self.approved


class ExecutionApproval:
    """
    Immutable final gate. Returns ApprovalDecision.
    Maintains deduplication cache and rate limiter.
    """

    MAX_PER_MINUTE = 30  # max approved orders per 60s rolling window
    DEDUP_TTL_SEC = 10.0  # identical signal fingerprints blocked for N seconds

    def __init__(self) -> None:
        self._veto_active = False
        self._veto_reason = ""
        self._lock = threading.Lock()
        # Rate limiter: timestamps of recent approvals
        self._approval_timestamps: deque[float] = deque()
        # Dedup: fingerprint -> expires_at
        self._seen_fingerprints: Dict[str, float] = {}
        self._approved_count = 0
        self._rejected_count = 0

    # ------------------------------------------------------------------
    # Operator controls
    # ------------------------------------------------------------------

    def activate_veto(self, reason: str = "operator veto") -> None:
        """Block all execution immediately."""
        with self._lock:
            self._veto_active = True
            self._veto_reason = reason

    def deactivate_veto(self) -> None:
        with self._lock:
            self._veto_active = False
            self._veto_reason = ""

    @property
    def is_vetoed(self) -> bool:
        return self._veto_active

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def request(self, req: ApprovalRequest) -> ApprovalDecision:
        with self._lock:
            decision = self._evaluate(req)
            if decision.approved:
                self._approved_count += 1
                self._approval_timestamps.append(time.time())
                metrics_bus.increment("execution_approval", "approved")
            else:
                self._rejected_count += 1
                metrics_bus.increment("execution_approval", "rejected")
            return decision

    def _evaluate(self, req: ApprovalRequest) -> ApprovalDecision:
        # 1. Operator VETO
        if self._veto_active:
            return self._reject(req, f"operator veto: {self._veto_reason}")

        # 2. System state
        if state_manager.state != SystemState.TRADING:
            return self._reject(
                req, f"system not in TRADING state ({state_manager.state.name})"
            )

        # 3. Upstream gates must have passed
        if not req.confidence_gate_passed:
            return self._reject(req, "confidence gate not passed")
        if not req.risk_authorizer_passed:
            return self._reject(req, "risk authorizer not passed")

        # 4. Deduplication
        fingerprint = self._fingerprint(req)
        now = time.time()
        self._evict_stale_fingerprints(now)
        if fingerprint in self._seen_fingerprints:
            return self._reject(
                req, f"duplicate signal (fingerprint={fingerprint[:8]})"
            )
        self._seen_fingerprints[fingerprint] = now + self.DEDUP_TTL_SEC

        # 5. Rate limiter
        self._evict_old_approvals(now)
        if len(self._approval_timestamps) >= self.MAX_PER_MINUTE:
            return self._reject(
                req, f"rate limit: {self.MAX_PER_MINUTE} approvals/min exceeded"
            )

        # 6. Sanity checks
        if req.size_usd <= 0:
            return self._reject(req, f"invalid size_usd={req.size_usd}")
        if req.side not in {"long", "short"}:
            return self._reject(req, f"invalid side '{req.side}'")

        return ApprovalDecision(
            approved=True,
            trace_id=req.trace_id,
            reason=f"approved | confidence={req.signal_confidence:.2f} risk={req.risk_score:.2f}",
        )

    def _reject(self, req: ApprovalRequest, reason: str) -> ApprovalDecision:
        return ApprovalDecision(approved=False, trace_id=req.trace_id, reason=reason)

    def _fingerprint(self, req: ApprovalRequest) -> str:
        raw = f"{req.symbol}|{req.side}|{req.size_usd:.2f}|{req.strategy}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _evict_stale_fingerprints(self, now: float) -> None:
        expired = [k for k, exp in self._seen_fingerprints.items() if exp < now]
        for k in expired:
            del self._seen_fingerprints[k]

    def _evict_old_approvals(self, now: float) -> None:
        cutoff = now - 60.0
        while self._approval_timestamps and self._approval_timestamps[0] < cutoff:
            self._approval_timestamps.popleft()

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            self._evict_old_approvals(time.time())
            return {
                "veto_active": self._veto_active,
                "veto_reason": self._veto_reason,
                "approvals_last_60s": len(self._approval_timestamps),
                "rate_limit_per_min": self.MAX_PER_MINUTE,
                "dedup_cache_size": len(self._seen_fingerprints),
                "total_approved": self._approved_count,
                "total_rejected": self._rejected_count,
            }


# Singleton
execution_approval = ExecutionApproval()
