"""Financial Institute domain contracts.

FIN-00 defines semantics only. Importing this package must not grant runtime,
execution, capital-allocation, or exchange-write authority.
"""

from .semantics import (
    AccountKind,
    EvidenceStatus,
    FinancialAccount,
    FinancialContractError,
    FinancialEventIdentity,
    FinancialModel,
    LedgerPosting,
    PostingSide,
    ReconciliationStatus,
    ValuationStatus,
    assert_balanced_postings,
    book_equity_at_cost,
    canonical_decimal,
    canonical_identity_hash,
    certified_equity,
    derive_financial_event_id,
    derive_financial_snapshot_id,
    linear_price_pnl,
    realized_pnl_to_date,
    reconciliation_delta,
    unreconciled_capital,
    within_reconciliation_tolerance,
)

__all__ = [
    "AccountKind",
    "EvidenceStatus",
    "FinancialAccount",
    "FinancialContractError",
    "FinancialEventIdentity",
    "FinancialModel",
    "LedgerPosting",
    "PostingSide",
    "ReconciliationStatus",
    "ValuationStatus",
    "assert_balanced_postings",
    "book_equity_at_cost",
    "canonical_decimal",
    "canonical_identity_hash",
    "certified_equity",
    "derive_financial_event_id",
    "derive_financial_snapshot_id",
    "linear_price_pnl",
    "realized_pnl_to_date",
    "reconciliation_delta",
    "unreconciled_capital",
    "within_reconciliation_tolerance",
]


from .models import (
    FIN_SCHEMA_VERSION,
    PAPER_LINEAR_FUNDING_EVIDENCE_REF,
    FinancialContext,
    FinancialEvent,
    FinancialLedgerState,
    FinancialSnapshot,
    PositionValuation,
    financial_context_digest,
    TreasuryView,
    ValuationObservation,
)
from .ppl_adapter import AdaptedPPLStream, adapt_ppl_stream, ppl_stream_digest
from .snapshot import build_financial_snapshot

__all__ += [
    "FIN_SCHEMA_VERSION",
    "PAPER_LINEAR_FUNDING_EVIDENCE_REF",
    "FinancialContext",
    "FinancialEvent",
    "FinancialLedgerState",
    "FinancialSnapshot",
    "PositionValuation",
    "financial_context_digest",
    "TreasuryView",
    "ValuationObservation",
    "AdaptedPPLStream",
    "adapt_ppl_stream",
    "ppl_stream_digest",
    "build_financial_snapshot",
]
