"""
Risk Authorizer — validates a proposed trade against all active risk limits
before it reaches execution approval.

Checks (in order):
  1. System state allows execution
  2. Drawdown limit not breached
  3. Daily loss limit not breached
  4. Position concentration within bounds
  5. Correlation / portfolio exposure within bounds
  6. Leverage within limits
  7. Volatility threshold not exceeded

Each check is independent. All failures are collected and returned together.

Usage:
    from governance.risk_authorizer import risk_authorizer, RiskContext

    ctx = RiskContext(
        symbol="BTCUSDT",
        side="long",
        size_usd=500.0,
        current_drawdown=0.02,
        daily_pnl=-150.0,
        portfolio_exposure_pct=0.35,
        leverage=2.0,
        volatility_24h=0.04,
    )
    auth = risk_authorizer.authorize(ctx)
    if not auth.approved:
        logger.warning("Trade blocked", reasons=auth.violations)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from observability.metrics_bus import metrics_bus
from system.state_manager import SystemState, state_manager


@dataclass
class RiskContext:
    """All inputs needed to authorize a trade."""

    symbol: str
    side: str  # "long" | "short"
    size_usd: float
    current_drawdown: float  # 0.0–1.0  e.g. 0.03 = 3%
    daily_pnl: float  # negative = loss
    portfolio_exposure_pct: float  # 0.0–1.0  total capital at risk
    leverage: float = 1.0
    volatility_24h: float = 0.0  # 0.0–1.0  annualized or daily %
    correlation_score: float = 0.0  # 0.0–1.0  with existing positions
    trace_id: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthorizationResult:
    approved: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    risk_score: float = 0.0  # 0.0 = safe, 1.0 = maximum risk
    trace_id: str = ""

    def summary(self) -> str:
        if self.approved:
            return f"APPROVED (risk_score={self.risk_score:.2f})"
        return f"REJECTED: {'; '.join(self.violations)}"


# ------------------------------------------------------------------
# Risk limits (all overrideable at runtime via set_limit())
# ------------------------------------------------------------------

_DEFAULT_LIMITS: Dict[str, float] = {
    "max_drawdown": 0.05,  # 5% max portfolio drawdown
    "max_daily_loss_usd": 500.0,  # $500 daily loss cap
    "max_position_usd": 2000.0,  # max single position size
    "max_portfolio_exposure": 0.80,  # 80% capital deployed at once
    "max_leverage": 5.0,
    "max_volatility": 0.08,  # 8% daily vol → halt new entries
    "max_correlation": 0.80,  # highly correlated positions blocked
}

# Tighter limits during degraded/risk_off states
_STATE_MULTIPLIERS: Dict[SystemState, float] = {
    SystemState.RISK_OFF: 0.50,
    SystemState.DEGRADED: 0.60,
    SystemState.RECOVERY: 0.70,
    SystemState.TRADING: 1.00,
    SystemState.READY: 0.90,
}


class RiskAuthorizer:
    """
    Validates a proposed trade against all risk limits.
    All checks run; violations are accumulated (fail-all, not fail-fast).
    """

    def __init__(self) -> None:
        self._limits: Dict[str, float] = dict(_DEFAULT_LIMITS)

    def set_limit(self, name: str, value: float) -> None:
        self._limits[name] = value

    def get_limit(self, name: str) -> float:
        multiplier = _STATE_MULTIPLIERS.get(state_manager.state, 1.0)
        return self._limits.get(name, 0.0) * multiplier

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def authorize(self, ctx: RiskContext) -> AuthorizationResult:
        violations: List[str] = []
        warnings: List[str] = []

        # 0. State gate
        if not state_manager.is_execution_allowed:
            return AuthorizationResult(
                approved=False,
                violations=[
                    f"execution not allowed in state {state_manager.state.name}"
                ],
                trace_id=ctx.trace_id,
            )

        # 1. Drawdown
        max_dd = self.get_limit("max_drawdown")
        if ctx.current_drawdown >= max_dd:
            violations.append(
                f"drawdown {ctx.current_drawdown:.2%} >= limit {max_dd:.2%}"
            )
        elif ctx.current_drawdown >= max_dd * 0.85:
            warnings.append(
                f"drawdown {ctx.current_drawdown:.2%} near limit ({max_dd:.2%})"
            )

        # 2. Daily loss
        max_loss = self.get_limit("max_daily_loss_usd")
        if ctx.daily_pnl <= -max_loss:
            violations.append(
                f"daily loss ${-ctx.daily_pnl:.0f} >= limit ${max_loss:.0f}"
            )
        elif ctx.daily_pnl <= -max_loss * 0.80:
            warnings.append(
                f"daily loss ${-ctx.daily_pnl:.0f} approaching limit ${max_loss:.0f}"
            )

        # 3. Position size
        max_pos = self.get_limit("max_position_usd")
        if ctx.size_usd > max_pos:
            violations.append(
                f"position size ${ctx.size_usd:.0f} > limit ${max_pos:.0f}"
            )

        # 4. Portfolio exposure
        max_exp = self.get_limit("max_portfolio_exposure")
        if ctx.portfolio_exposure_pct >= max_exp:
            violations.append(
                f"portfolio exposure {ctx.portfolio_exposure_pct:.1%} >= limit {max_exp:.1%}"
            )
        elif ctx.portfolio_exposure_pct >= max_exp * 0.90:
            warnings.append(
                f"portfolio exposure {ctx.portfolio_exposure_pct:.1%} near limit"
            )

        # 5. Leverage
        max_lev = self.get_limit("max_leverage")
        if ctx.leverage > max_lev:
            violations.append(f"leverage {ctx.leverage:.1f}x > limit {max_lev:.1f}x")

        # 6. Volatility
        max_vol = self.get_limit("max_volatility")
        if max_vol > 0 and ctx.volatility_24h > max_vol:
            violations.append(
                f"volatility {ctx.volatility_24h:.2%} > limit {max_vol:.2%}"
            )

        # 7. Correlation
        max_corr = self.get_limit("max_correlation")
        if max_corr > 0 and ctx.correlation_score > max_corr:
            violations.append(
                f"correlation {ctx.correlation_score:.2f} > limit {max_corr:.2f}"
            )

        # Risk score (heuristic: fraction of limits consumed)
        risk_score = self._compute_risk_score(ctx)
        approved = len(violations) == 0

        result = AuthorizationResult(
            approved=approved,
            violations=violations,
            warnings=warnings,
            risk_score=risk_score,
            trace_id=ctx.trace_id,
        )

        # Emit metrics
        metrics_bus.increment("risk_authorizer", "authorizations_total")
        if approved:
            metrics_bus.increment("risk_authorizer", "authorizations_approved")
        else:
            metrics_bus.increment("risk_authorizer", "authorizations_rejected")
        metrics_bus.gauge("risk_authorizer", "last_risk_score", risk_score)

        return result

    def _compute_risk_score(self, ctx: RiskContext) -> float:
        scores = [
            ctx.current_drawdown / max(self.get_limit("max_drawdown"), 1e-9),
            max(0.0, -ctx.daily_pnl) / max(self.get_limit("max_daily_loss_usd"), 1.0),
            ctx.portfolio_exposure_pct
            / max(self.get_limit("max_portfolio_exposure"), 1e-9),
            ctx.leverage / max(self.get_limit("max_leverage"), 1.0),
            ctx.volatility_24h / max(self.get_limit("max_volatility"), 1e-9),
        ]
        return min(max(sum(scores) / len(scores), 0.0), 1.0)

    def snapshot(self) -> Dict[str, Any]:
        state = state_manager.state
        mult = _STATE_MULTIPLIERS.get(state, 1.0)
        return {
            "system_state": state.name,
            "state_multiplier": mult,
            "effective_limits": {k: v * mult for k, v in self._limits.items()},
            "raw_limits": dict(self._limits),
        }


# Singleton
risk_authorizer = RiskAuthorizer()
