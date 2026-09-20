"""FIN-00 — canonical financial semantics.

This module is deliberately pure and runtime-independent.  It formalizes the
vocabulary and invariants that FIN-01 must implement, but it does not consume
PPL, mutate PAPER state, write an exchange, value a live portfolio, or become a
runtime authority.

Money-like values are normalized to Decimal from their textual representation.
There is no hidden epsilon and no implicit rounding policy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Iterable, Mapping, Optional, Sequence, Union

Numberish = Union[Decimal, int, float, str]


class FinancialContractError(ValueError):
    """A FIN semantic invariant was violated."""


class PostingSide(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class AccountKind(str, Enum):
    ASSET = "ASSET"
    EQUITY = "EQUITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class FinancialAccount(str, Enum):
    """FIN-00 PAPER v1 chart of accounts.

    CAPITAL_RESERVED is the historical principal/cost-basis bucket for live
    PAPER positions. CAPITAL_UNRESOLVED segregates historical principal whose
    settlement cannot be established. Neither is a market valuation.
    """

    CASH_AVAILABLE = "CASH_AVAILABLE"
    CAPITAL_RESERVED = "CAPITAL_RESERVED"
    CAPITAL_UNRESOLVED = "CAPITAL_UNRESOLVED"
    EPOCH_CAPITAL = "EPOCH_CAPITAL"
    REALIZED_TRADING_PNL = "REALIZED_TRADING_PNL"
    FEES_EXPENSE = "FEES_EXPENSE"
    FUNDING_PNL = "FUNDING_PNL"


ACCOUNT_KINDS = {
    FinancialAccount.CASH_AVAILABLE: AccountKind.ASSET,
    FinancialAccount.CAPITAL_RESERVED: AccountKind.ASSET,
    FinancialAccount.CAPITAL_UNRESOLVED: AccountKind.ASSET,
    FinancialAccount.EPOCH_CAPITAL: AccountKind.EQUITY,
    FinancialAccount.REALIZED_TRADING_PNL: AccountKind.INCOME,
    FinancialAccount.FEES_EXPENSE: AccountKind.EXPENSE,
    FinancialAccount.FUNDING_PNL: AccountKind.INCOME,
}


class EvidenceStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ValuationStatus(str, Enum):
    LIVE = "LIVE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class ReconciliationStatus(str, Enum):
    EXACT = "EXACT"
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    DIVERGENT = "DIVERGENT"
    UNRESOLVED = "UNRESOLVED"



def canonical_identity_hash(namespace: str, fields: Mapping[str, object]) -> str:
    """Return the FIN-00 canonical identity hash.

    Identity input is UTF-8 canonical JSON with sorted keys, compact separators,
    no NaN/Infinity, and a versioned namespace prefix. Values must already be
    normalized semantic scalars; FIN-01 must not hash presentation formatting.
    """

    if not namespace:
        raise FinancialContractError("identity namespace must be non-empty")
    try:
        payload = json.dumps(
            dict(fields),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise FinancialContractError("identity fields are not canonically serializable") from exc
    material = f"{namespace}\n{payload}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def derive_financial_event_id(
    *,
    source_domain: str,
    source_authority: str,
    source_event_id: str,
    paper_epoch_id: str,
    source_sequence: int,
    schema_version: int,
) -> str:
    """Deterministic FIN event identity derived from immutable source identity."""

    identity = FinancialEventIdentity(
        financial_event_id="pending",
        source_domain=source_domain,
        source_authority=source_authority,
        source_event_id=source_event_id,
        paper_epoch_id=paper_epoch_id,
        source_sequence=source_sequence,
        schema_version=schema_version,
        code_sha="identity-only",
        config_hash="identity-only",
    )
    return canonical_identity_hash(
        "FIN_EVENT_ID_V1",
        {
            "source_domain": identity.source_domain,
            "source_authority": identity.source_authority,
            "source_event_id": identity.source_event_id,
            "paper_epoch_id": identity.paper_epoch_id,
            "source_sequence": identity.source_sequence,
            "schema_version": identity.schema_version,
        },
    )


def derive_financial_snapshot_id(
    *,
    paper_epoch_id: str,
    last_source_sequence: int,
    source_stream_digest: str,
    schema_version: int,
    code_sha: str,
    config_hash: str,
    valuation_set_digest: str,
    valuation_as_of: str,
) -> str:
    """Deterministic immutable FinancialSnapshot identity contract."""

    for name, value in (
        ("paper_epoch_id", paper_epoch_id),
        ("source_stream_digest", source_stream_digest),
        ("code_sha", code_sha),
        ("config_hash", config_hash),
        ("valuation_set_digest", valuation_set_digest),
        ("valuation_as_of", valuation_as_of),
    ):
        if not value:
            raise FinancialContractError(f"{name} must be non-empty")
    if (
        not isinstance(last_source_sequence, int)
        or isinstance(last_source_sequence, bool)
        or last_source_sequence < 1
    ):
        raise FinancialContractError("last_source_sequence must be an integer >= 1")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version < 1
    ):
        raise FinancialContractError("schema_version must be an integer >= 1")

    return canonical_identity_hash(
        "FIN_SNAPSHOT_ID_V1",
        {
            "paper_epoch_id": paper_epoch_id,
            "last_source_sequence": last_source_sequence,
            "source_stream_digest": source_stream_digest,
            "schema_version": schema_version,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "valuation_set_digest": valuation_set_digest,
            "valuation_as_of": valuation_as_of,
        },
    )


def canonical_decimal(name: str, value: Numberish) -> Decimal:
    """Normalize a financial scalar without silently rounding it."""

    if isinstance(value, bool):
        raise FinancialContractError(f"{name} must be numeric, got bool")
    try:
        normalized = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FinancialContractError(f"{name} is not a valid decimal: {value!r}") from exc
    if not normalized.is_finite():
        raise FinancialContractError(f"{name} must be finite, got {value!r}")
    return normalized


@dataclass(frozen=True)
class FinancialEventIdentity:
    """Minimum provenance required for a FIN event derived from source facts."""

    financial_event_id: str
    source_domain: str
    source_authority: str
    source_event_id: str
    paper_epoch_id: str
    source_sequence: int
    schema_version: int
    code_sha: str
    config_hash: str

    def __post_init__(self) -> None:
        for name in (
            "financial_event_id",
            "source_domain",
            "source_authority",
            "source_event_id",
            "paper_epoch_id",
            "code_sha",
            "config_hash",
        ):
            if not getattr(self, name):
                raise FinancialContractError(f"{name} must be non-empty")
        if (
            not isinstance(self.source_sequence, int)
            or isinstance(self.source_sequence, bool)
            or self.source_sequence < 1
        ):
            raise FinancialContractError("source_sequence must be an integer >= 1")
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version < 1
        ):
            raise FinancialContractError("schema_version must be an integer >= 1")


@dataclass(frozen=True)
class LedgerPosting:
    """One side of a double-entry FIN journal event."""

    posting_id: str
    financial_event_id: str
    account: FinancialAccount
    side: PostingSide
    asset: str
    amount: Decimal
    paper_epoch_id: str

    def __post_init__(self) -> None:
        for name in ("posting_id", "financial_event_id", "asset", "paper_epoch_id"):
            if not getattr(self, name):
                raise FinancialContractError(f"{name} must be non-empty")
        amount = canonical_decimal("amount", self.amount)
        if amount <= 0:
            raise FinancialContractError("posting amount must be > 0")
        object.__setattr__(self, "amount", amount)


def assert_balanced_postings(postings: Iterable[LedgerPosting]) -> None:
    """Require exact debit == credit for one FinancialEvent."""

    materialized = tuple(postings)
    if not materialized:
        raise FinancialContractError("a financial event must contain postings")
    event_ids = {posting.financial_event_id for posting in materialized}
    epochs = {posting.paper_epoch_id for posting in materialized}
    assets = {posting.asset for posting in materialized}
    if len(event_ids) != 1:
        raise FinancialContractError("postings span multiple financial_event_id values")
    if len(epochs) != 1:
        raise FinancialContractError("postings span multiple paper_epoch_id values")
    if len(assets) != 1:
        raise FinancialContractError(
            "FIN-00 PAPER v1 postings must balance within one asset"
        )

    debit = sum(
        (posting.amount for posting in materialized if posting.side is PostingSide.DEBIT),
        Decimal("0"),
    )
    credit = sum(
        (posting.amount for posting in materialized if posting.side is PostingSide.CREDIT),
        Decimal("0"),
    )
    if debit != credit:
        raise FinancialContractError(
            f"unbalanced financial event: debit={debit} credit={credit}"
        )


def _positive(name: str, value: Numberish) -> Decimal:
    normalized = canonical_decimal(name, value)
    if normalized <= 0:
        raise FinancialContractError(f"{name} must be > 0")
    return normalized


def _non_negative(name: str, value: Numberish) -> Decimal:
    normalized = canonical_decimal(name, value)
    if normalized < 0:
        raise FinancialContractError(f"{name} must be >= 0")
    return normalized


def linear_price_pnl(
    *,
    principal: Numberish,
    side: str,
    entry_price: Numberish,
    mark_or_exit_price: Numberish,
) -> Decimal:
    """Price PnL for the current PPL linear principal model.

    This intentionally mirrors the certified PPL price-return convention.
    It is not a generic futures multiplier/leverage formula.
    """

    p = _positive("principal", principal)
    entry = _positive("entry_price", entry_price)
    current = _positive("mark_or_exit_price", mark_or_exit_price)
    canonical_side = str(side).strip().upper()

    if canonical_side == "LONG":
        return p * (current - entry) / entry
    if canonical_side == "SHORT":
        return p * (entry - current) / entry
    raise FinancialContractError("side must be LONG or SHORT")


def realized_pnl_to_date(
    *,
    gross_realized_price_pnl: Numberish,
    fees_paid: Numberish,
    funding_net: Numberish,
) -> Decimal:
    """Canonical FIN realized PnL recognized to date.

    Fees are realized expenses when charged. Funding is signed: positive when
    received and negative when paid. This differs intentionally from the
    lifecycle-oriented PPL projection field that recognizes a trade-level net
    result only when a position closes.
    """

    gross = canonical_decimal("gross_realized_price_pnl", gross_realized_price_pnl)
    fees = _non_negative("fees_paid", fees_paid)
    funding = canonical_decimal("funding_net", funding_net)
    return gross + funding - fees


def book_equity_at_cost(
    *,
    cash_available: Numberish,
    capital_reserved: Numberish,
    capital_unresolved: Numberish,
) -> Decimal:
    """Historical-cost asset total before mark-to-market."""

    cash = _non_negative("cash_available", cash_available)
    reserved = _non_negative("capital_reserved", capital_reserved)
    unresolved = _non_negative("capital_unresolved", capital_unresolved)
    return cash + reserved + unresolved


def certified_equity(
    *,
    cash_available: Numberish,
    capital_reserved: Numberish,
    unrealized_pnl: Numberish,
    capital_unresolved: Numberish,
    open_position_count: int,
    valuation_statuses: Sequence[ValuationStatus],
) -> Optional[Decimal]:
    """Return certified mark-to-market equity or None when evidence is unsafe.

    CAPITAL_RESERVED is carried at historical principal and unrealized_pnl is
    the mark-to-market adjustment. Unresolved capital or any non-LIVE mark
    makes certified equity unavailable; UNKNOWN is never substituted with zero.
    """

    cash = _non_negative("cash_available", cash_available)
    reserved = _non_negative("capital_reserved", capital_reserved)
    unresolved = _non_negative("capital_unresolved", capital_unresolved)
    unrealized = canonical_decimal("unrealized_pnl", unrealized_pnl)

    if (
        not isinstance(open_position_count, int)
        or isinstance(open_position_count, bool)
        or open_position_count < 0
    ):
        raise FinancialContractError("open_position_count must be an integer >= 0")
    if unresolved != 0:
        return None
    if (reserved == 0) != (open_position_count == 0):
        raise FinancialContractError(
            "capital_reserved and open_position_count disagree about open exposure"
        )
    if len(valuation_statuses) != open_position_count:
        return None
    if any(status is not ValuationStatus.LIVE for status in valuation_statuses):
        return None
    return cash + reserved + unrealized


def within_reconciliation_tolerance(
    *,
    projected: Numberish,
    observed: Numberish,
    absolute_tolerance: Numberish,
    relative_tolerance: Numberish,
) -> bool:
    """Explicit reconciliation comparison with no hidden epsilon."""

    p = canonical_decimal("projected", projected)
    o = canonical_decimal("observed", observed)
    abs_tol = _non_negative("absolute_tolerance", absolute_tolerance)
    rel_tol = _non_negative("relative_tolerance", relative_tolerance)

    delta = abs(o - p)
    scale = max(abs(o), abs(p))
    return delta <= max(abs_tol, rel_tol * scale)
