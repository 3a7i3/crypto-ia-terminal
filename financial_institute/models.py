"""FIN-01 immutable PAPER Financial Institute models."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from financial_institute.semantics import (
    EvidenceStatus,
    FinancialModel,
    LedgerPosting,
    ReconciliationStatus,
    ValuationStatus,
    canonical_decimal,
    canonical_identity_hash,
)

FIN_SCHEMA_VERSION = 1
PAPER_LINEAR_FUNDING_EVIDENCE_REF = (
    "FIN-00:PAPER_LINEAR_PRINCIPAL_V1:FUNDING_NOT_MODELED"
)


@dataclass(frozen=True)
class FinancialContext:
    """Explicit non-inferred context for one FIN projection."""

    fin_code_sha: str
    asset: str = "USDT"
    source_authority: str = "PPL_AUTHORITY"
    financial_model: FinancialModel = FinancialModel.PAPER_LINEAR_PRINCIPAL_V1
    funding_status: EvidenceStatus = EvidenceStatus.UNRESOLVED
    funding_evidence_ref: Optional[str] = None
    strategy_id: Optional[str] = None
    strategy_version: Optional[str] = None
    experiment_id: Optional[str] = None
    venue: Optional[str] = None
    market_type: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.fin_code_sha, str) or not self.fin_code_sha:
            raise ValueError("fin_code_sha must be a non-empty string")
        if not isinstance(self.asset, str) or not self.asset:
            raise ValueError("asset must be a non-empty string")
        if self.asset != "USDT":
            raise ValueError("FIN-01 PAPER v1 supports asset=USDT only")
        if not isinstance(self.financial_model, FinancialModel):
            raise ValueError("financial_model must be a FinancialModel")
        if not isinstance(self.funding_status, EvidenceStatus):
            raise ValueError("funding_status must be an EvidenceStatus")
        if self.source_authority != "PPL_AUTHORITY":
            raise ValueError("FIN-01 requires source_authority=PPL_AUTHORITY")
        if self.financial_model is not FinancialModel.PAPER_LINEAR_PRINCIPAL_V1:
            raise ValueError("FIN-01 supports only PAPER_LINEAR_PRINCIPAL_V1")
        if self.funding_status not in {
            EvidenceStatus.UNRESOLVED,
            EvidenceStatus.NOT_APPLICABLE,
        }:
            raise ValueError(
                "PPL-only FIN-01 cannot claim COMPLETE/PARTIAL funding evidence"
            )
        if self.funding_status is EvidenceStatus.NOT_APPLICABLE:
            if (
                self.funding_evidence_ref
                != PAPER_LINEAR_FUNDING_EVIDENCE_REF
            ):
                raise ValueError(
                    "NOT_APPLICABLE funding requires certified "
                    "funding_evidence_ref for PAPER_LINEAR_PRINCIPAL_V1"
                )
        for name in (
            "funding_evidence_ref",
            "strategy_id",
            "strategy_version",
            "experiment_id",
            "venue",
            "market_type",
        ):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str) or not value
            ):
                raise ValueError(f"{name} must be a non-empty string or null")
        if self.strategy_version and not self.strategy_id:
            raise ValueError("strategy_version requires strategy_id")


def financial_context_digest(context: FinancialContext) -> str:
    """Deterministic digest of every semantic input not carried by PPL."""

    return canonical_identity_hash(
        "FIN_CONTEXT_V1",
        {
            "asset": context.asset,
            "source_authority": context.source_authority,
            "financial_model": context.financial_model.value,
            "funding_status": context.funding_status.value,
            "funding_evidence_ref": context.funding_evidence_ref,
            "strategy_id": context.strategy_id,
            "strategy_version": context.strategy_version,
            "experiment_id": context.experiment_id,
            "venue": context.venue,
            "market_type": context.market_type,
        },
    )


@dataclass(frozen=True)
class FinancialEvent:
    financial_event_id: str
    paper_epoch_id: str
    source_event_id: str
    source_sequence: int
    source_event_type: str
    source_schema_version: int
    timestamp: Decimal
    trade_id: Optional[str]
    decision_id: Optional[str]
    fin_schema_version: int
    semantic_context_digest: str
    fin_code_sha: str
    config_hash: str
    postings: Tuple[LedgerPosting, ...]

    def __post_init__(self) -> None:
        for name in (
            "financial_event_id",
            "paper_epoch_id",
            "source_event_id",
            "source_event_type",
            "semantic_context_digest",
            "fin_code_sha",
            "config_hash",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if (
            not isinstance(self.source_sequence, int)
            or isinstance(self.source_sequence, bool)
            or self.source_sequence < 1
        ):
            raise ValueError("source_sequence must be an integer >= 1")
        if (
            not isinstance(self.source_schema_version, int)
            or isinstance(self.source_schema_version, bool)
            or self.source_schema_version < 1
        ):
            raise ValueError("source_schema_version must be an integer >= 1")
        if (
            not isinstance(self.fin_schema_version, int)
            or isinstance(self.fin_schema_version, bool)
            or self.fin_schema_version < 1
        ):
            raise ValueError("fin_schema_version must be an integer >= 1")
        for name in ("trade_id", "decision_id"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str) or not value
            ):
                raise ValueError(f"{name} must be a non-empty string or null")

        timestamp = canonical_decimal("timestamp", self.timestamp)
        postings = tuple(self.postings)
        if not postings:
            raise ValueError("FinancialEvent must contain postings")
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "postings", postings)


@dataclass(frozen=True)
class FinancialLedgerState:
    paper_epoch_id: str
    asset: str
    balances: Mapping[str, Decimal] = field(default_factory=dict)
    applied_financial_event_ids: frozenset[str] = field(default_factory=frozenset)
    last_source_sequence: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "balances",
            MappingProxyType(dict(self.balances)),
        )
        object.__setattr__(
            self,
            "applied_financial_event_ids",
            frozenset(self.applied_financial_event_ids),
        )


@dataclass(frozen=True)
class TreasuryView:
    paper_epoch_id: str
    asset: str
    financial_model: FinancialModel
    initial_epoch_capital: Decimal
    cash_available: Decimal
    capital_reserved: Decimal
    capital_deployed: Decimal
    capital_unresolved: Decimal
    gross_realized_price_pnl: Decimal
    fees_paid: Decimal
    funding_net: Optional[Decimal]
    funding_status: EvidenceStatus
    funding_evidence_ref: Optional[str]
    realized_pnl: Optional[Decimal]


@dataclass(frozen=True)
class ValuationObservation:
    trade_id: str
    symbol: str
    source_id: str
    venue: str
    market_type: str
    price: Optional[Decimal]
    source_timestamp: Optional[Decimal]

    def __post_init__(self) -> None:
        for name in ("trade_id", "symbol", "source_id", "venue", "market_type"):
            if not getattr(self, name):
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True)
class PositionValuation:
    trade_id: str
    symbol: str
    status: ValuationStatus
    price: Optional[Decimal]
    source_id: Optional[str]
    venue: Optional[str]
    market_type: Optional[str]
    source_timestamp: Optional[Decimal]
    age_s: Optional[Decimal]
    unrealized_pnl: Optional[Decimal]


@dataclass(frozen=True)
class FinancialSnapshot:
    snapshot_id: str
    paper_epoch_id: str
    source_authority: str
    source_stream_digest: str
    last_source_sequence: int
    fin_schema_version: int
    semantic_context_digest: str
    fin_code_sha: str
    source_code_sha: str
    config_hash: str
    financial_model: FinancialModel
    asset: str
    initial_epoch_capital: Decimal
    cash_available: Decimal
    capital_reserved: Decimal
    capital_deployed: Decimal
    capital_unresolved: Decimal
    gross_realized_price_pnl: Decimal
    fees_paid: Decimal
    funding_net: Optional[Decimal]
    funding_status: EvidenceStatus
    funding_evidence_ref: Optional[str]
    realized_pnl: Optional[Decimal]
    known_unrealized_pnl: Decimal
    unrealized_pnl: Optional[Decimal]
    certified_equity: Optional[Decimal]
    valuation_as_of: Decimal
    valuation_set_digest: str
    valuations: Tuple[PositionValuation, ...]
    valuation_statuses: Tuple[ValuationStatus, ...]
    open_position_count: int
    settled_position_count: int
    unresolved_position_count: int
    evidence_status: EvidenceStatus
    reconciliation_status: ReconciliationStatus
    strategy_id: Optional[str]
    strategy_version: Optional[str]
    strategy_attribution_status: EvidenceStatus
    experiment_id: Optional[str]
    experiment_attribution_status: EvidenceStatus
    venue: Optional[str]
    market_type: Optional[str]

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise ValueError("snapshot_id must be non-empty")
        if not self.paper_epoch_id:
            raise ValueError("paper_epoch_id must be non-empty")
        if not self.semantic_context_digest:
            raise ValueError("semantic_context_digest must be non-empty")
        for name in (
            "open_position_count",
            "settled_position_count",
            "unresolved_position_count",
            "last_source_sequence",
            "fin_schema_version",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError(f"{name} must be an integer >= 0")
        if self.last_source_sequence < 1:
            raise ValueError("last_source_sequence must be >= 1")
        if self.fin_schema_version < 1:
            raise ValueError("fin_schema_version must be >= 1")

        valuations = tuple(self.valuations)
        statuses = tuple(self.valuation_statuses)
        if len(valuations) != self.open_position_count:
            raise ValueError(
                "valuations count must equal open_position_count"
            )
        if len(statuses) != self.open_position_count:
            raise ValueError(
                "valuation_statuses count must equal open_position_count"
            )
        if any(
            valuation.status is not status
            for valuation, status in zip(valuations, statuses)
        ):
            raise ValueError(
                "valuation_statuses must match PositionValuation.status"
            )

        object.__setattr__(self, "valuations", valuations)
        object.__setattr__(self, "valuation_statuses", statuses)
