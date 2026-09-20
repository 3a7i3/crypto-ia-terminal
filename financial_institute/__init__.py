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
