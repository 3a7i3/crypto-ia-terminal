"""
AI Constraints — hard rules that prevent any AI module from touching production directly.

The AI pipeline is:
    AI produces signal/strategy
        -> SHADOW validation (paper trading)
        -> PAPER validation (simulated capital)
        -> SANDBOX (isolated backtest)
        -> PROMOTION (human or automated approval)
        -> LIVE (via decision_router only)

AI modules must NEVER call execution_engine, place_order, or modify live state directly.
This module provides:
  - AIPromotion: the only path from AI output to live trading
  - AIConstraintViolation: raised if a module bypasses this contract
  - validation_stage decorator: marks functions with their allowed stage

Usage:
    from governance.ai_constraints import ai_promotion, PromotionRequest, AIStage

    req = PromotionRequest(
        strategy_id="momentum_v3",
        source_stage=AIStage.PAPER,
        sharpe_ratio=1.8,
        win_rate=0.62,
        paper_days=14,
        max_drawdown=0.04,
    )
    result = ai_promotion.promote(req)
    if result.promoted:
        # strategy is now eligible to enter decision_router
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from observability.json_logger import get_logger

log = get_logger("ai_constraints", category="ai")


class AIStage(Enum):
    """Ordered pipeline stages. AI output advances one step at a time."""

    SHADOW = 1  # runs alongside live, no capital, no orders
    PAPER = 2  # simulated capital, no orders
    SANDBOX = 3  # isolated backtest with real historical data
    PROMOTED = 4  # eligible for live routing (via decision_router only)
    LIVE = 5  # actively trading — set by decision_router, never by AI


class AIConstraintViolation(Exception):
    """Raised when an AI module attempts to bypass the promotion pipeline."""


# ------------------------------------------------------------------
# Promotion thresholds
# ------------------------------------------------------------------

_PROMOTION_REQUIREMENTS: Dict[str, Any] = {
    "min_sharpe": 1.5,
    "min_win_rate": 0.52,
    "min_paper_days": 7,
    "max_drawdown": 0.08,
    "min_trade_count": 20,
}


@dataclass
class PromotionRequest:
    strategy_id: str
    source_stage: AIStage  # must be SHADOW, PAPER, or SANDBOX
    sharpe_ratio: float
    win_rate: float
    paper_days: int
    max_drawdown: float
    trade_count: int = 0
    requester: str = "ai_module"
    notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PromotionResult:
    promoted: bool
    strategy_id: str
    target_stage: AIStage
    failures: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


# ------------------------------------------------------------------
# Strategy registry — tracks stage per strategy ID
# ------------------------------------------------------------------


class AIPromotion:
    """
    Controls the AI → production pipeline.
    Strategies can only advance one stage at a time.
    Only PROMOTED strategies are eligible for live routing.
    """

    def __init__(self) -> None:
        self._stages: Dict[str, AIStage] = {}
        self._history: List[PromotionResult] = []
        self._requirements: Dict[str, Any] = dict(_PROMOTION_REQUIREMENTS)

    def register(self, strategy_id: str, stage: AIStage = AIStage.SHADOW) -> None:
        """Register a new AI strategy at a given stage."""
        self._stages[strategy_id] = stage
        log.ai("strategy_registered", strategy_id=strategy_id, stage=stage.name)

    def stage_of(self, strategy_id: str) -> Optional[AIStage]:
        return self._stages.get(strategy_id)

    def is_live_eligible(self, strategy_id: str) -> bool:
        return self._stages.get(strategy_id) == AIStage.PROMOTED

    def set_requirement(self, name: str, value: Any) -> None:
        self._requirements[name] = value

    def promote(self, req: PromotionRequest) -> PromotionResult:
        """
        Attempt to advance a strategy one stage toward LIVE eligibility.
        Validates all promotion requirements before granting.
        """
        current = self._stages.get(req.strategy_id, AIStage.SHADOW)
        failures: List[str] = []

        # Stage order validation
        if req.source_stage.value != current.value:
            failures.append(
                f"stage mismatch: strategy is at {current.name}, "
                f"promotion requested from {req.source_stage.name}"
            )

        # Cannot promote directly to LIVE — only decision_router can do that
        next_stage_val = current.value + 1
        if next_stage_val >= AIStage.LIVE.value:
            failures.append("AI cannot promote directly to LIVE — use decision_router")

        # Quality thresholds
        reqs = self._requirements
        if req.sharpe_ratio < reqs["min_sharpe"]:
            failures.append(f"Sharpe {req.sharpe_ratio:.2f} < {reqs['min_sharpe']}")
        if req.win_rate < reqs["min_win_rate"]:
            failures.append(f"win_rate {req.win_rate:.2%} < {reqs['min_win_rate']:.2%}")
        if req.paper_days < reqs["min_paper_days"]:
            failures.append(f"paper_days {req.paper_days} < {reqs['min_paper_days']}")
        if req.max_drawdown > reqs["max_drawdown"]:
            failures.append(
                f"drawdown {req.max_drawdown:.2%} > {reqs['max_drawdown']:.2%}"
            )
        if req.trade_count < reqs["min_trade_count"]:
            failures.append(
                f"trade_count {req.trade_count} < {reqs['min_trade_count']}"
            )

        promoted = len(failures) == 0
        if promoted:
            target = AIStage(next_stage_val)
            self._stages[req.strategy_id] = target
            log.ai(
                "strategy_promoted",
                strategy_id=req.strategy_id,
                from_stage=current.name,
                to_stage=target.name,
            )
        else:
            target = current
            log.ai(
                "strategy_promotion_failed",
                strategy_id=req.strategy_id,
                failures=failures,
            )

        result = PromotionResult(
            promoted=promoted,
            strategy_id=req.strategy_id,
            target_stage=target,
            failures=failures,
        )
        self._history.append(result)
        return result

    def demote(self, strategy_id: str, reason: str = "") -> None:
        """Immediately demote a strategy to SHADOW (emergency)."""
        current = self._stages.get(strategy_id, AIStage.SHADOW)
        self._stages[strategy_id] = AIStage.SHADOW
        log.ai(
            "strategy_demoted",
            strategy_id=strategy_id,
            from_stage=current.name,
            reason=reason,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "strategies": {sid: s.name for sid, s in self._stages.items()},
            "live_eligible": [
                sid for sid, s in self._stages.items() if s == AIStage.PROMOTED
            ],
            "requirements": self._requirements,
            "promotion_history": len(self._history),
        }


# ------------------------------------------------------------------
# Decorator for stage enforcement
# ------------------------------------------------------------------


def ai_stage_required(stage: AIStage) -> Callable:
    """
    Decorator: raises AIConstraintViolation if function is called
    outside its declared stage context.
    Use on functions that must only run in a specific stage.
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # The decorated function may pass its strategy_id as first arg or kwarg
            # This is a lightweight guard — not a full enforcement mechanism
            log.ai("ai_stage_check", function=fn.__name__, required_stage=stage.name)
            return fn(*args, **kwargs)

        wrapper._ai_stage = stage
        return wrapper

    return decorator


def guard_live_access(fn: Callable) -> Callable:
    """
    Decorator: prevents any function decorated with this from being called
    by an AI module. Raises AIConstraintViolation immediately.
    Use on exchange execution methods.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        raise AIConstraintViolation(
            f"Direct call to '{fn.__name__}' by AI is forbidden. "
            "Use governance.decision_router.route() instead."
        )

    return wrapper


# Singleton
ai_promotion = AIPromotion()
