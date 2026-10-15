"""Garde de risque du LAB : règles explicites, verdict motivé, jamais assoupli."""

from __future__ import annotations

from dataclasses import dataclass

from lab01.strategy import Signal


@dataclass(frozen=True)
class RiskLimits:
    capital_usd: float = 10_000.0
    risk_per_trade_pct: float = 0.10
    max_notional_pct: float = 15.0
    min_confidence: float = 55.0
    min_r_multiple: float = 1.5
    max_realized_vol_bps: float = 60.0


@dataclass(frozen=True)
class RiskCheck:
    code: str
    passed: bool
    observed: float
    limit: float
    comparison: str  # ">=" ou "<="
    justification: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass(frozen=True)
class RiskVerdict:
    approved: bool
    reason_code: str
    size: float
    notional_usd: float
    checks: tuple[RiskCheck, ...]

    def as_dict(self) -> dict:
        return {
            "approved": self.approved,
            "reason_code": self.reason_code,
            "size": self.size,
            "notional_usd": self.notional_usd,
            "checks": [c.as_dict() for c in self.checks],
        }


def evaluate(sig: Signal, lim: RiskLimits) -> RiskVerdict:
    stop_dist = sig.price - sig.stop_loss
    r_multiple = (sig.take_profit - sig.price) / stop_dist if stop_dist > 0 else 0.0
    risk_usd = lim.capital_usd * lim.risk_per_trade_pct / 100.0
    size = round(risk_usd / stop_dist, 6) if stop_dist > 0 else 0.0
    notional = round(size * sig.price, 4)
    notional_pct = notional / lim.capital_usd * 100.0

    def chk(code, observed, limit, cmp, text):
        ok = observed >= limit if cmp == ">=" else observed <= limit
        return RiskCheck(code, ok, round(observed, 4), limit, cmp, text)

    checks = (
        chk(
            "CONFIDENCE_BELOW_MIN",
            sig.confidence,
            lim.min_confidence,
            ">=",
            "confiance du signal au moins égale au minimum",
        ),
        chk(
            "R_MULTIPLE_BELOW_MIN",
            r_multiple,
            lim.min_r_multiple,
            ">=",
            "rapport gain/risque attendu au moins égal au minimum",
        ),
        chk(
            "VOLATILITY_ABOVE_LIMIT",
            sig.realized_vol_bps,
            lim.max_realized_vol_bps,
            "<=",
            "volatilité réalisée (bps/barre) sous le plafond",
        ),
        chk(
            "MAX_NOTIONAL_EXCEEDED",
            notional_pct,
            lim.max_notional_pct,
            "<=",
            "notionnel de l'ordre (% du capital) sous le plafond",
        ),
    )
    failed = next((c for c in checks if not c.passed), None)
    return RiskVerdict(
        approved=failed is None,
        reason_code="APPROVED" if failed is None else failed.code,
        size=size,
        notional_usd=notional,
        checks=checks,
    )
