"""FIN-01 deterministic mark valuation over explicit observations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from financial_institute.models import PositionValuation, ValuationObservation
from financial_institute.semantics import (
    ValuationStatus,
    canonical_decimal,
    canonical_identity_hash,
    linear_price_pnl,
)
from paper_trading.paper_portfolio_ledger import PaperPortfolioState


class ValuationError(ValueError):
    """Valuation evidence violates the FIN-00 contract."""


@dataclass(frozen=True)
class ValuationSet:
    valuations: tuple[PositionValuation, ...]
    valuation_set_digest: str
    known_unrealized_pnl: Decimal
    unrealized_pnl: Decimal | None
    statuses: tuple[ValuationStatus, ...]


def _canonical_decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def evaluate_valuations(
    state: PaperPortfolioState,
    observations: Sequence[ValuationObservation],
    *,
    valuation_as_of: Decimal,
    max_age_s: Decimal,
) -> ValuationSet:
    """Value every open position with no wall-clock reads or fallback marks."""

    as_of = canonical_decimal("valuation_as_of", valuation_as_of)
    max_age = canonical_decimal("max_age_s", max_age_s)
    if max_age < 0:
        raise ValuationError("max_age_s must be >= 0")

    by_trade: dict[str, ValuationObservation] = {}
    for observation in observations:
        if observation.trade_id in by_trade:
            raise ValuationError(
                f"duplicate valuation observation for trade_id={observation.trade_id!r}"
            )
        by_trade[observation.trade_id] = observation

    unknown_trade_ids = set(by_trade) - set(state.open_positions)
    if unknown_trade_ids:
        raise ValuationError(
            f"valuation observations reference non-open trades: "
            f"{sorted(unknown_trade_ids)}"
        )

    valuations: list[PositionValuation] = []
    known_unrealized = Decimal("0")

    for trade_id in sorted(state.open_positions):
        position = state.open_positions[trade_id]
        observation = by_trade.get(trade_id)

        if observation is None:
            valuations.append(
                PositionValuation(
                    trade_id=trade_id,
                    symbol=position.symbol,
                    status=ValuationStatus.UNAVAILABLE,
                    price=None,
                    source_id=None,
                    venue=None,
                    market_type=None,
                    source_timestamp=None,
                    age_s=None,
                    unrealized_pnl=None,
                )
            )
            continue

        if observation.symbol != position.symbol:
            raise ValuationError(
                f"valuation symbol mismatch for trade_id={trade_id!r}: "
                f"{observation.symbol!r} != {position.symbol!r}"
            )

        price = (
            canonical_decimal("valuation.price", observation.price)
            if observation.price is not None
            else None
        )
        source_timestamp = (
            canonical_decimal(
                "valuation.source_timestamp", observation.source_timestamp
            )
            if observation.source_timestamp is not None
            else None
        )

        if price is None or source_timestamp is None or price <= 0:
            status = ValuationStatus.UNAVAILABLE
            age = None
            pnl = None
        else:
            age = as_of - source_timestamp
            if age < 0:
                status = ValuationStatus.UNAVAILABLE
                pnl = None
            else:
                status = (
                    ValuationStatus.LIVE
                    if age <= max_age
                    else ValuationStatus.STALE
                )
                pnl = linear_price_pnl(
                    principal=position.principal,
                    side=position.side.value,
                    entry_price=position.entry_price,
                    mark_or_exit_price=price,
                )
                known_unrealized += pnl

        valuations.append(
            PositionValuation(
                trade_id=trade_id,
                symbol=position.symbol,
                status=status,
                price=price,
                source_id=observation.source_id,
                venue=observation.venue,
                market_type=observation.market_type,
                source_timestamp=source_timestamp,
                age_s=age,
                unrealized_pnl=pnl,
            )
        )

    statuses = tuple(item.status for item in valuations)
    all_live = all(status is ValuationStatus.LIVE for status in statuses)
    complete_unrealized = known_unrealized if all_live else None

    digest_fields: dict[str, object] = {
        "valuation_as_of": _canonical_decimal_text(as_of),
        "max_age_s": _canonical_decimal_text(max_age),
        "positions": [
            {
                "trade_id": item.trade_id,
                "symbol": item.symbol,
                "status": item.status.value,
                "price": _canonical_decimal_text(item.price),
                "source_id": item.source_id,
                "venue": item.venue,
                "market_type": item.market_type,
                "source_timestamp": _canonical_decimal_text(
                    item.source_timestamp
                ),
                "age_s": _canonical_decimal_text(item.age_s),
                "unrealized_pnl": _canonical_decimal_text(
                    item.unrealized_pnl
                ),
            }
            for item in valuations
        ],
    }
    digest = canonical_identity_hash("FIN_VALUATION_SET_V1", digest_fields)

    return ValuationSet(
        valuations=tuple(valuations),
        valuation_set_digest=digest,
        known_unrealized_pnl=known_unrealized,
        unrealized_pnl=complete_unrealized,
        statuses=statuses,
    )
