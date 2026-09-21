"""FIN-01 immutable FinancialSnapshot construction."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from financial_institute.ledger import project_financial_ledger, treasury_view
from financial_institute.models import (
    FIN_SCHEMA_VERSION,
    FinancialContext,
    FinancialSnapshot,
    ValuationObservation,
)
from financial_institute.ppl_adapter import adapt_ppl_stream
from financial_institute.semantics import (
    EvidenceStatus,
    ReconciliationStatus,
    ValuationStatus,
    canonical_decimal,
    certified_equity,
    derive_financial_snapshot_id,
)
from financial_institute.valuation import evaluate_valuations
from paper_trading.ledger_events import LedgerEvent, LedgerEventType
from paper_trading.paper_portfolio_ledger import project


class FinancialSnapshotError(ValueError):
    """FIN snapshot cannot be certified from the supplied evidence."""


def _attribution_status(value: str | None) -> EvidenceStatus:
    return EvidenceStatus.COMPLETE if value else EvidenceStatus.UNRESOLVED


def _evidence_status(
    *,
    capital_unresolved: Decimal,
    funding_status: EvidenceStatus,
    valuation_statuses: Sequence[ValuationStatus],
) -> EvidenceStatus:
    if capital_unresolved != 0:
        return EvidenceStatus.UNRESOLVED
    if funding_status is EvidenceStatus.UNRESOLVED:
        return EvidenceStatus.UNRESOLVED
    if any(status is ValuationStatus.UNAVAILABLE for status in valuation_statuses):
        return EvidenceStatus.UNRESOLVED
    if any(status is ValuationStatus.STALE for status in valuation_statuses):
        return EvidenceStatus.PARTIAL
    return EvidenceStatus.COMPLETE


def build_financial_snapshot(
    events: Sequence[LedgerEvent],
    context: FinancialContext,
    observations: Sequence[ValuationObservation],
    *,
    valuation_as_of: Decimal,
    max_mark_age_s: Decimal,
) -> FinancialSnapshot:
    """Build the same immutable FIN state from the same explicit inputs."""

    if not events:
        raise FinancialSnapshotError("PPL stream must not be empty")

    ppl_state = project(events)
    if ppl_state.epoch is None:
        raise FinancialSnapshotError("PPL stream has no epoch")

    adapted = adapt_ppl_stream(events, context)
    ledger = project_financial_ledger(
        adapted.financial_events,
        asset=context.asset,
    )
    treasury = treasury_view(ledger, context)

    valuation_as_of_value = canonical_decimal(
        "valuation_as_of", valuation_as_of
    )
    valuation_set = evaluate_valuations(
        ppl_state,
        observations,
        valuation_as_of=valuation_as_of_value,
        max_age_s=max_mark_age_s,
    )

    unrealized_for_equity = (
        valuation_set.unrealized_pnl
        if valuation_set.unrealized_pnl is not None
        else valuation_set.known_unrealized_pnl
    )
    equity = certified_equity(
        cash_available=treasury.cash_available,
        capital_reserved=treasury.capital_reserved,
        unrealized_pnl=unrealized_for_equity,
        capital_unresolved=treasury.capital_unresolved,
        open_position_count=len(ppl_state.open_positions),
        valuation_statuses=valuation_set.statuses,
        funding_status=treasury.funding_status,
    )

    evidence = _evidence_status(
        capital_unresolved=treasury.capital_unresolved,
        funding_status=treasury.funding_status,
        valuation_statuses=valuation_set.statuses,
    )

    settled_count = sum(
        1
        for event in events
        if event.event_type is LedgerEventType.POSITION_CLOSED
    )
    unresolved_count = sum(
        1
        for event in events
        if event.event_type is LedgerEventType.POSITION_UNRESOLVED
    )

    context_digest = adapted.semantic_context_digest
    reconciliation_status = ReconciliationStatus.UNRESOLVED

    snapshot_id = derive_financial_snapshot_id(
        paper_epoch_id=adapted.paper_epoch_id,
        last_source_sequence=adapted.last_source_sequence,
        source_stream_digest=adapted.source_stream_digest,
        schema_version=FIN_SCHEMA_VERSION,
        code_sha=context.fin_code_sha,
        config_hash=adapted.config_hash,
        semantic_context_digest=context_digest,
        valuation_set_digest=valuation_set.valuation_set_digest,
        valuation_as_of=format(valuation_as_of_value, "f"),
        evidence_status=evidence.value,
        reconciliation_status=reconciliation_status.value,
    )

    return FinancialSnapshot(
        snapshot_id=snapshot_id,
        paper_epoch_id=adapted.paper_epoch_id,
        source_authority=context.source_authority,
        source_stream_digest=adapted.source_stream_digest,
        last_source_sequence=adapted.last_source_sequence,
        fin_schema_version=FIN_SCHEMA_VERSION,
        semantic_context_digest=context_digest,
        fin_code_sha=context.fin_code_sha,
        source_code_sha=adapted.source_code_sha,
        config_hash=adapted.config_hash,
        financial_model=context.financial_model,
        asset=context.asset,
        initial_epoch_capital=treasury.initial_epoch_capital,
        cash_available=treasury.cash_available,
        capital_reserved=treasury.capital_reserved,
        capital_deployed=treasury.capital_deployed,
        capital_unresolved=treasury.capital_unresolved,
        gross_realized_price_pnl=treasury.gross_realized_price_pnl,
        fees_paid=treasury.fees_paid,
        funding_net=treasury.funding_net,
        funding_status=treasury.funding_status,
        realized_pnl=treasury.realized_pnl,
        known_unrealized_pnl=valuation_set.known_unrealized_pnl,
        unrealized_pnl=valuation_set.unrealized_pnl,
        certified_equity=equity,
        valuation_as_of=valuation_as_of_value,
        valuation_set_digest=valuation_set.valuation_set_digest,
        valuations=valuation_set.valuations,
        valuation_statuses=valuation_set.statuses,
        open_position_count=len(ppl_state.open_positions),
        settled_position_count=settled_count,
        unresolved_position_count=unresolved_count,
        evidence_status=evidence,
        reconciliation_status=reconciliation_status,
        strategy_id=context.strategy_id,
        strategy_version=context.strategy_version,
        strategy_attribution_status=_attribution_status(
            context.strategy_id
        ),
        experiment_id=context.experiment_id,
        experiment_attribution_status=_attribution_status(
            context.experiment_id
        ),
        venue=context.venue,
        market_type=context.market_type,
    )
