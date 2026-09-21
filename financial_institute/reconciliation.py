"""FIN-02 — deterministic reconciliation over FIN-01 financial truth.

This module is pure and read-only.  It compares a certified FIN-01
FinancialSnapshot with explicit observations from PPL, the PAPER simulator and,
when applicable, an external read-only account observation.

Reconciliation is evidence.  It never mutates FIN, PPL, simulator state or an
exchange.  Unknown, stale and semantically non-equivalent facts remain explicit
instead of being coerced to zero or silently corrected.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Mapping, Optional, Sequence

from financial_institute.models import FinancialSnapshot
from financial_institute.semantics import (
    ReconciliationStatus,
    canonical_decimal,
    canonical_identity_hash,
    reconciliation_delta,
    unreconciled_capital,
    within_reconciliation_tolerance,
)
from paper_trading.ledger_events import LedgerEvent
from paper_trading.paper_portfolio_ledger import project
from financial_institute.ppl_adapter import ppl_stream_digest


FIN_RECONCILIATION_SCHEMA_VERSION = 1


class ReconciliationSourceKind(str, Enum):
    PPL = "PPL"
    SIMULATOR = "SIMULATOR"
    EXCHANGE_READ_ONLY = "EXCHANGE_READ_ONLY"


class ObservationFreshness(str, Enum):
    LIVE = "LIVE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Comparability(str, Enum):
    COMPARABLE = "COMPARABLE"
    NON_COMPARABLE = "NON_COMPARABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ReconciliationPolicy:
    absolute_tolerance: Decimal
    relative_tolerance: Decimal
    stale_after_s: Decimal

    def __post_init__(self) -> None:
        absolute = canonical_decimal(
            "absolute_tolerance", self.absolute_tolerance
        )
        relative = canonical_decimal(
            "relative_tolerance", self.relative_tolerance
        )
        stale = canonical_decimal("stale_after_s", self.stale_after_s)
        if absolute < 0 or relative < 0 or stale < 0:
            raise ValueError("reconciliation tolerances/TTL must be >= 0")
        object.__setattr__(self, "absolute_tolerance", absolute)
        object.__setattr__(self, "relative_tolerance", relative)
        object.__setattr__(self, "stale_after_s", stale)


@dataclass(frozen=True)
class PPLFinancialObservation:
    paper_epoch_id: str
    source_stream_digest: str
    last_sequence: int
    observed_at: Decimal
    cash_available: Decimal
    capital_reserved: Decimal
    capital_unresolved: Decimal
    lifecycle_realized_pnl: Decimal
    fees_paid: Decimal
    open_position_ids: tuple[str, ...]
    closed_trade_ids: tuple[str, ...]
    unresolved_position_ids: tuple[str, ...]
    provenance: str = "PPL durable replay"

    def __post_init__(self) -> None:
        if not self.paper_epoch_id or not self.source_stream_digest:
            raise ValueError("PPL observation identity must be non-empty")
        if (
            not isinstance(self.last_sequence, int)
            or isinstance(self.last_sequence, bool)
            or self.last_sequence < 1
        ):
            raise ValueError("last_sequence must be an integer >= 1")
        for name in (
            "observed_at",
            "cash_available",
            "capital_reserved",
            "capital_unresolved",
            "lifecycle_realized_pnl",
            "fees_paid",
        ):
            object.__setattr__(
                self,
                name,
                canonical_decimal(name, getattr(self, name)),
            )
        for name in (
            "open_position_ids",
            "closed_trade_ids",
            "unresolved_position_ids",
        ):
            values = tuple(str(value) for value in getattr(self, name))
            if len(values) != len(set(values)):
                raise ValueError(f"{name} contains duplicate identities")
            object.__setattr__(self, name, tuple(sorted(values)))


@dataclass(frozen=True)
class SimulatorFinancialObservation:
    observed_at: Decimal
    cash_available: Optional[Decimal]
    capital_reserved: Optional[Decimal]
    open_position_ids: Optional[tuple[str, ...]]
    lifecycle_transitions_in_flight: Optional[int]
    pending_order_count: Optional[int]
    source_id: str = "MEXC_SIM"
    provenance: str = "read-only simulator snapshot"

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("simulator source_id must be non-empty")
        object.__setattr__(
            self,
            "observed_at",
            canonical_decimal("observed_at", self.observed_at),
        )
        for name in ("cash_available", "capital_reserved"):
            value = getattr(self, name)
            if value is not None:
                normalized = canonical_decimal(name, value)
                if normalized < 0:
                    raise ValueError(f"{name} must be >= 0")
                object.__setattr__(self, name, normalized)
        if self.open_position_ids is not None:
            values = tuple(sorted(str(v) for v in self.open_position_ids))
            if len(values) != len(set(values)):
                raise ValueError("open_position_ids contains duplicates")
            object.__setattr__(self, "open_position_ids", values)
        for name in (
            "lifecycle_transitions_in_flight",
            "pending_order_count",
        ):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError(f"{name} must be an integer >= 0 or null")


@dataclass(frozen=True)
class ExternalFinancialObservation:
    observed_at: Decimal
    source_id: str
    asset: str
    free_cash: Optional[Decimal] = None
    equity: Optional[Decimal] = None
    applicability: ObservationFreshness = ObservationFreshness.NOT_APPLICABLE
    provenance: str = "exchange/API read-only observation"

    def __post_init__(self) -> None:
        if not self.source_id or not self.asset:
            raise ValueError("external observation source_id/asset must be non-empty")
        object.__setattr__(
            self,
            "observed_at",
            canonical_decimal("observed_at", self.observed_at),
        )
        if not isinstance(self.applicability, ObservationFreshness):
            raise ValueError("applicability must be an ObservationFreshness")
        for name in ("free_cash", "equity"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self,
                    name,
                    canonical_decimal(name, value),
                )


@dataclass(frozen=True)
class ReconciliationRecord:
    record_id: str
    source_kind: ReconciliationSourceKind
    source_id: str
    field: str
    projected_value: Optional[Decimal]
    observed_value: Optional[Decimal]
    delta_observed_minus_projected: Optional[Decimal]
    unreconciled_amount: Optional[Decimal]
    status: ReconciliationStatus
    comparability: Comparability
    freshness: ObservationFreshness
    observed_at: Decimal
    projected_provenance: str
    observed_provenance: str
    note: Optional[str] = None


@dataclass(frozen=True)
class FinancialReconciliationSnapshot:
    reconciliation_id: str
    schema_version: int
    paper_epoch_id: str
    financial_snapshot_id: str
    source_stream_digest: str
    last_source_sequence: int
    as_of: Decimal
    policy: ReconciliationPolicy
    overall_status: ReconciliationStatus
    unresolved_capital: Decimal
    unreconciled_capital: Optional[Decimal]
    records: tuple[ReconciliationRecord, ...]
    ppl_observation_digest: str
    simulator_observation_digest: Optional[str]
    external_observation_digest: Optional[str]


def _decimal_text(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else format(value, "f")


def _freshness(
    *,
    observed_at: Decimal,
    as_of: Decimal,
    stale_after_s: Decimal,
) -> ObservationFreshness:
    age = as_of - observed_at
    if age < 0:
        return ObservationFreshness.UNAVAILABLE
    if age > stale_after_s:
        return ObservationFreshness.STALE
    return ObservationFreshness.LIVE


def _observation_digest(namespace: str, fields: Mapping[str, object]) -> str:
    return canonical_identity_hash(namespace, fields)


def ppl_observation_from_events(
    events: Sequence[LedgerEvent],
    *,
    observed_at: Decimal,
) -> PPLFinancialObservation:
    """Build a PPL observation only from the durable event population."""

    state = project(events)
    if state.epoch is None:
        raise ValueError("PPL stream has no epoch")
    return PPLFinancialObservation(
        paper_epoch_id=state.paper_epoch_id,
        source_stream_digest=ppl_stream_digest(events),
        last_sequence=state.last_sequence,
        observed_at=observed_at,
        cash_available=Decimal(str(state.available_cash)),
        capital_reserved=Decimal(str(state.reserved_principal)),
        capital_unresolved=Decimal(str(state.unresolved_capital)),
        lifecycle_realized_pnl=Decimal(str(state.realized_pnl)),
        fees_paid=Decimal(str(state.fees_paid)),
        open_position_ids=tuple(state.open_positions),
        closed_trade_ids=tuple(state.closed_trade_ids),
        unresolved_position_ids=tuple(state.unresolved_positions),
    )


def _ppl_digest(observation: PPLFinancialObservation) -> str:
    return _observation_digest(
        "FIN02_PPL_OBSERVATION_V1",
        {
            "paper_epoch_id": observation.paper_epoch_id,
            "source_stream_digest": observation.source_stream_digest,
            "last_sequence": observation.last_sequence,
            "observed_at": _decimal_text(observation.observed_at),
            "cash_available": _decimal_text(observation.cash_available),
            "capital_reserved": _decimal_text(observation.capital_reserved),
            "capital_unresolved": _decimal_text(observation.capital_unresolved),
            "lifecycle_realized_pnl": _decimal_text(
                observation.lifecycle_realized_pnl
            ),
            "fees_paid": _decimal_text(observation.fees_paid),
            "open_position_ids": list(observation.open_position_ids),
            "closed_trade_ids": list(observation.closed_trade_ids),
            "unresolved_position_ids": list(
                observation.unresolved_position_ids
            ),
            "provenance": observation.provenance,
        },
    )


def _simulator_digest(
    observation: SimulatorFinancialObservation,
) -> str:
    return _observation_digest(
        "FIN02_SIMULATOR_OBSERVATION_V1",
        {
            "source_id": observation.source_id,
            "observed_at": _decimal_text(observation.observed_at),
            "cash_available": _decimal_text(observation.cash_available),
            "capital_reserved": _decimal_text(observation.capital_reserved),
            "open_position_ids": (
                None
                if observation.open_position_ids is None
                else list(observation.open_position_ids)
            ),
            "lifecycle_transitions_in_flight": (
                observation.lifecycle_transitions_in_flight
            ),
            "pending_order_count": observation.pending_order_count,
            "provenance": observation.provenance,
        },
    )


def _external_digest(
    observation: ExternalFinancialObservation,
) -> str:
    return _observation_digest(
        "FIN02_EXTERNAL_OBSERVATION_V1",
        {
            "source_id": observation.source_id,
            "observed_at": _decimal_text(observation.observed_at),
            "asset": observation.asset,
            "free_cash": _decimal_text(observation.free_cash),
            "equity": _decimal_text(observation.equity),
            "applicability": observation.applicability.value,
            "provenance": observation.provenance,
        },
    )


def _record_id(
    *,
    financial_snapshot_id: str,
    source_kind: ReconciliationSourceKind,
    source_id: str,
    field: str,
) -> str:
    return canonical_identity_hash(
        "FIN02_RECONCILIATION_RECORD_V1",
        {
            "financial_snapshot_id": financial_snapshot_id,
            "source_kind": source_kind.value,
            "source_id": source_id,
            "field": field,
        },
    )


def _numeric_record(
    *,
    snapshot: FinancialSnapshot,
    policy: ReconciliationPolicy,
    as_of: Decimal,
    source_kind: ReconciliationSourceKind,
    source_id: str,
    field: str,
    projected: Optional[Decimal],
    observed: Optional[Decimal],
    observed_at: Decimal,
    projected_provenance: str,
    observed_provenance: str,
    comparability: Comparability = Comparability.COMPARABLE,
    note: Optional[str] = None,
) -> ReconciliationRecord:
    freshness = _freshness(
        observed_at=observed_at,
        as_of=as_of,
        stale_after_s=policy.stale_after_s,
    )
    delta: Optional[Decimal] = None
    amount: Optional[Decimal] = None

    if comparability is not Comparability.COMPARABLE:
        status = ReconciliationStatus.UNRESOLVED
    elif projected is None or observed is None:
        comparability = Comparability.UNAVAILABLE
        status = ReconciliationStatus.UNRESOLVED
    else:
        p = canonical_decimal("projected", projected)
        o = canonical_decimal("observed", observed)
        delta = reconciliation_delta(projected=p, observed=o)
        amount = unreconciled_capital(projected=p, observed=o)

        if freshness is not ObservationFreshness.LIVE:
            status = ReconciliationStatus.UNRESOLVED
        elif delta == 0:
            status = ReconciliationStatus.EXACT
        elif within_reconciliation_tolerance(
            projected=p,
            observed=o,
            absolute_tolerance=policy.absolute_tolerance,
            relative_tolerance=policy.relative_tolerance,
        ):
            status = ReconciliationStatus.WITHIN_TOLERANCE
        else:
            status = ReconciliationStatus.DIVERGENT

    return ReconciliationRecord(
        record_id=_record_id(
            financial_snapshot_id=snapshot.snapshot_id,
            source_kind=source_kind,
            source_id=source_id,
            field=field,
        ),
        source_kind=source_kind,
        source_id=source_id,
        field=field,
        projected_value=projected,
        observed_value=observed,
        delta_observed_minus_projected=delta,
        unreconciled_amount=amount,
        status=status,
        comparability=comparability,
        freshness=freshness,
        observed_at=observed_at,
        projected_provenance=projected_provenance,
        observed_provenance=observed_provenance,
        note=note,
    )


def _count_record(
    *,
    snapshot: FinancialSnapshot,
    policy: ReconciliationPolicy,
    as_of: Decimal,
    source_kind: ReconciliationSourceKind,
    source_id: str,
    field: str,
    projected: int,
    observed: Optional[int],
    observed_at: Decimal,
    observed_provenance: str,
) -> ReconciliationRecord:
    return _numeric_record(
        snapshot=snapshot,
        policy=policy,
        as_of=as_of,
        source_kind=source_kind,
        source_id=source_id,
        field=field,
        projected=Decimal(projected),
        observed=None if observed is None else Decimal(observed),
        observed_at=observed_at,
        projected_provenance="FIN-01 FinancialSnapshot",
        observed_provenance=observed_provenance,
    )


def _identity_set_record(
    *,
    snapshot: FinancialSnapshot,
    policy: ReconciliationPolicy,
    as_of: Decimal,
    source_kind: ReconciliationSourceKind,
    source_id: str,
    field: str,
    projected: Sequence[str],
    observed: Optional[Sequence[str]],
    observed_at: Decimal,
    observed_provenance: str,
) -> ReconciliationRecord:
    freshness = _freshness(
        observed_at=observed_at,
        as_of=as_of,
        stale_after_s=policy.stale_after_s,
    )
    if observed is None:
        status = ReconciliationStatus.UNRESOLVED
        comparability = Comparability.UNAVAILABLE
        observed_count = None
        delta = None
        amount = None
    else:
        left = tuple(sorted(str(value) for value in projected))
        right = tuple(sorted(str(value) for value in observed))
        observed_count = Decimal(len(right))
        delta = Decimal(len(right) - len(left))
        amount = abs(delta)
        comparability = Comparability.COMPARABLE
        if freshness is not ObservationFreshness.LIVE:
            status = ReconciliationStatus.UNRESOLVED
        elif left == right:
            status = ReconciliationStatus.EXACT
        else:
            status = ReconciliationStatus.DIVERGENT

    return ReconciliationRecord(
        record_id=_record_id(
            financial_snapshot_id=snapshot.snapshot_id,
            source_kind=source_kind,
            source_id=source_id,
            field=field,
        ),
        source_kind=source_kind,
        source_id=source_id,
        field=field,
        projected_value=Decimal(len(tuple(projected))),
        observed_value=observed_count,
        delta_observed_minus_projected=delta,
        unreconciled_amount=amount,
        status=status,
        comparability=comparability,
        freshness=freshness,
        observed_at=observed_at,
        projected_provenance="FIN/PPL exact trade identities",
        observed_provenance=observed_provenance,
        note="Record compares the exact identity set; numeric value is set cardinality.",
    )


def _overall_status(
    records: Sequence[ReconciliationRecord],
) -> ReconciliationStatus:
    material = [
        record
        for record in records
        if record.comparability
        in {Comparability.COMPARABLE, Comparability.UNAVAILABLE}
    ]
    if not material:
        return ReconciliationStatus.UNRESOLVED
    statuses = {record.status for record in material}
    if ReconciliationStatus.DIVERGENT in statuses:
        return ReconciliationStatus.DIVERGENT
    if ReconciliationStatus.UNRESOLVED in statuses:
        return ReconciliationStatus.UNRESOLVED
    if ReconciliationStatus.WITHIN_TOLERANCE in statuses:
        return ReconciliationStatus.WITHIN_TOLERANCE
    return ReconciliationStatus.EXACT


def reconcile_financial_snapshot(
    snapshot: FinancialSnapshot,
    ppl: PPLFinancialObservation,
    *,
    policy: ReconciliationPolicy,
    as_of: Decimal,
    simulator: Optional[SimulatorFinancialObservation] = None,
    external: Optional[ExternalFinancialObservation] = None,
) -> FinancialReconciliationSnapshot:
    """Compare FIN truth against explicit observations without correction."""

    as_of_value = canonical_decimal("as_of", as_of)
    if snapshot.paper_epoch_id != ppl.paper_epoch_id:
        raise ValueError("FIN/PPL paper_epoch_id mismatch")
    if snapshot.source_stream_digest != ppl.source_stream_digest:
        raise ValueError("FIN/PPL source stream digest mismatch")
    if snapshot.last_source_sequence != ppl.last_sequence:
        raise ValueError("FIN/PPL last source sequence mismatch")

    records: list[ReconciliationRecord] = []

    ppl_source_id = "PPL_AUTHORITY"
    records.extend(
        [
            _numeric_record(
                snapshot=snapshot,
                policy=policy,
                as_of=as_of_value,
                source_kind=ReconciliationSourceKind.PPL,
                source_id=ppl_source_id,
                field="cash_available",
                projected=snapshot.cash_available,
                observed=ppl.cash_available,
                observed_at=ppl.observed_at,
                projected_provenance="FIN-01 Treasury.cash_available",
                observed_provenance="PPL.projection.available_cash",
            ),
            _numeric_record(
                snapshot=snapshot,
                policy=policy,
                as_of=as_of_value,
                source_kind=ReconciliationSourceKind.PPL,
                source_id=ppl_source_id,
                field="capital_reserved",
                projected=snapshot.capital_reserved,
                observed=ppl.capital_reserved,
                observed_at=ppl.observed_at,
                projected_provenance="FIN-01 Treasury.capital_reserved",
                observed_provenance="PPL.projection.reserved_principal",
            ),
            _numeric_record(
                snapshot=snapshot,
                policy=policy,
                as_of=as_of_value,
                source_kind=ReconciliationSourceKind.PPL,
                source_id=ppl_source_id,
                field="capital_unresolved",
                projected=snapshot.capital_unresolved,
                observed=ppl.capital_unresolved,
                observed_at=ppl.observed_at,
                projected_provenance="FIN-01 Treasury.capital_unresolved",
                observed_provenance="PPL.projection.unresolved_capital",
            ),
            _numeric_record(
                snapshot=snapshot,
                policy=policy,
                as_of=as_of_value,
                source_kind=ReconciliationSourceKind.PPL,
                source_id=ppl_source_id,
                field="fees_paid",
                projected=snapshot.fees_paid,
                observed=ppl.fees_paid,
                observed_at=ppl.observed_at,
                projected_provenance="FIN-01 Treasury.fees_paid",
                observed_provenance="PPL.projection.fees_paid",
            ),
            _numeric_record(
                snapshot=snapshot,
                policy=policy,
                as_of=as_of_value,
                source_kind=ReconciliationSourceKind.PPL,
                source_id=ppl_source_id,
                field="realized_pnl",
                projected=snapshot.realized_pnl,
                observed=ppl.lifecycle_realized_pnl,
                observed_at=ppl.observed_at,
                projected_provenance="FIN-01 realized PnL to date",
                observed_provenance="PPL lifecycle realized PnL",
                comparability=Comparability.NON_COMPARABLE,
                note=(
                    "FIN recognizes charged fees immediately; PPL lifecycle "
                    "realized_pnl recognizes trade-level net result at close. "
                    "Raw values are visible but no divergence is asserted."
                ),
            ),
            _count_record(
                snapshot=snapshot,
                policy=policy,
                as_of=as_of_value,
                source_kind=ReconciliationSourceKind.PPL,
                source_id=ppl_source_id,
                field="open_position_count",
                projected=snapshot.open_position_count,
                observed=len(ppl.open_position_ids),
                observed_at=ppl.observed_at,
                observed_provenance="PPL.projection.open_positions",
            ),
            _count_record(
                snapshot=snapshot,
                policy=policy,
                as_of=as_of_value,
                source_kind=ReconciliationSourceKind.PPL,
                source_id=ppl_source_id,
                field="settled_position_count",
                projected=snapshot.settled_position_count,
                observed=len(ppl.closed_trade_ids),
                observed_at=ppl.observed_at,
                observed_provenance="PPL.projection.closed_trade_ids",
            ),
            _count_record(
                snapshot=snapshot,
                policy=policy,
                as_of=as_of_value,
                source_kind=ReconciliationSourceKind.PPL,
                source_id=ppl_source_id,
                field="unresolved_position_count",
                projected=snapshot.unresolved_position_count,
                observed=len(ppl.unresolved_position_ids),
                observed_at=ppl.observed_at,
                observed_provenance="PPL.projection.unresolved_positions",
            ),
        ]
    )

    simulator_digest: Optional[str] = None
    capital_reconciliation: Optional[Decimal] = None

    if simulator is not None:
        simulator_digest = _simulator_digest(simulator)
        records.extend(
            [
                _numeric_record(
                    snapshot=snapshot,
                    policy=policy,
                    as_of=as_of_value,
                    source_kind=ReconciliationSourceKind.SIMULATOR,
                    source_id=simulator.source_id,
                    field="cash_available",
                    projected=snapshot.cash_available,
                    observed=simulator.cash_available,
                    observed_at=simulator.observed_at,
                    projected_provenance="FIN-01 Treasury.cash_available",
                    observed_provenance=(
                        f"{simulator.provenance}: cash_available"
                    ),
                ),
                _numeric_record(
                    snapshot=snapshot,
                    policy=policy,
                    as_of=as_of_value,
                    source_kind=ReconciliationSourceKind.SIMULATOR,
                    source_id=simulator.source_id,
                    field="capital_reserved",
                    projected=snapshot.capital_reserved,
                    observed=simulator.capital_reserved,
                    observed_at=simulator.observed_at,
                    projected_provenance="FIN-01 Treasury.capital_reserved",
                    observed_provenance=(
                        f"{simulator.provenance}: reserved principal"
                    ),
                ),
                _count_record(
                    snapshot=snapshot,
                    policy=policy,
                    as_of=as_of_value,
                    source_kind=ReconciliationSourceKind.SIMULATOR,
                    source_id=simulator.source_id,
                    field="open_position_count",
                    projected=snapshot.open_position_count,
                    observed=(
                        None
                        if simulator.open_position_ids is None
                        else len(simulator.open_position_ids)
                    ),
                    observed_at=simulator.observed_at,
                    observed_provenance=(
                        f"{simulator.provenance}: open position identities"
                    ),
                ),
                _identity_set_record(
                    snapshot=snapshot,
                    policy=policy,
                    as_of=as_of_value,
                    source_kind=ReconciliationSourceKind.SIMULATOR,
                    source_id=simulator.source_id,
                    field="open_position_identity_set",
                    projected=ppl.open_position_ids,
                    observed=simulator.open_position_ids,
                    observed_at=simulator.observed_at,
                    observed_provenance=(
                        f"{simulator.provenance}: exact trade ids"
                    ),
                ),
            ]
        )

        fin_book = (
            snapshot.cash_available
            + snapshot.capital_reserved
            + snapshot.capital_unresolved
        )
        simulator_book = (
            None
            if (
                simulator.cash_available is None
                or simulator.capital_reserved is None
                or snapshot.capital_unresolved != 0
            )
            else simulator.cash_available + simulator.capital_reserved
        )
        book_record = _numeric_record(
            snapshot=snapshot,
            policy=policy,
            as_of=as_of_value,
            source_kind=ReconciliationSourceKind.SIMULATOR,
            source_id=simulator.source_id,
            field="book_capital_at_cost",
            projected=fin_book,
            observed=simulator_book,
            observed_at=simulator.observed_at,
            projected_provenance=(
                "FIN cash_available + capital_reserved + capital_unresolved"
            ),
            observed_provenance=(
                f"{simulator.provenance}: cash + reserved principal"
            ),
            note=(
                "This is the single designated PAPER capital reconciliation "
                "metric. It is not mark-to-market equity."
            ),
        )
        records.append(book_record)
        if (
            book_record.comparability is Comparability.COMPARABLE
            and book_record.freshness is ObservationFreshness.LIVE
            and book_record.unreconciled_amount is not None
        ):
            capital_reconciliation = book_record.unreconciled_amount

        quiescence_observed = (
            None
            if (
                simulator.lifecycle_transitions_in_flight is None
                or simulator.pending_order_count is None
            )
            else Decimal(
                simulator.lifecycle_transitions_in_flight
                + simulator.pending_order_count
            )
        )
        records.append(
            _numeric_record(
                snapshot=snapshot,
                policy=policy,
                as_of=as_of_value,
                source_kind=ReconciliationSourceKind.SIMULATOR,
                source_id=simulator.source_id,
                field="quiescence",
                projected=Decimal("0"),
                observed=quiescence_observed,
                observed_at=simulator.observed_at,
                projected_provenance="FIN-02 coherent-capture requirement",
                observed_provenance=simulator.provenance,
                note=(
                    "Zero requires both in-flight transitions and pending "
                    "orders to be explicitly observed. Missing evidence "
                    "remains UNRESOLVED; non-zero is a visible divergence."
                ),
            )
        )

    external_digest: Optional[str] = None
    if external is not None:
        external_digest = _external_digest(external)
        external_freshness = external.applicability
        records.append(
            ReconciliationRecord(
                record_id=_record_id(
                    financial_snapshot_id=snapshot.snapshot_id,
                    source_kind=ReconciliationSourceKind.EXCHANGE_READ_ONLY,
                    source_id=external.source_id,
                    field="paper_vs_external_account",
                ),
                source_kind=ReconciliationSourceKind.EXCHANGE_READ_ONLY,
                source_id=external.source_id,
                field="paper_vs_external_account",
                projected_value=snapshot.certified_equity,
                observed_value=external.equity,
                delta_observed_minus_projected=None,
                unreconciled_amount=None,
                status=ReconciliationStatus.UNRESOLVED,
                comparability=Comparability.NOT_APPLICABLE,
                freshness=external_freshness,
                observed_at=external.observed_at,
                projected_provenance="FIN-01 PAPER FinancialSnapshot",
                observed_provenance=external.provenance,
                note=(
                    "PAPER capital and a real exchange account are separate "
                    "accounting scopes. FIN-02 displays the observation but "
                    "does not subtract one from the other."
                ),
            )
        )

    overall = _overall_status(records)
    ppl_digest = _ppl_digest(ppl)

    reconciliation_id = canonical_identity_hash(
        "FIN02_RECONCILIATION_SNAPSHOT_V1",
        {
            "schema_version": FIN_RECONCILIATION_SCHEMA_VERSION,
            "paper_epoch_id": snapshot.paper_epoch_id,
            "financial_snapshot_id": snapshot.snapshot_id,
            "source_stream_digest": snapshot.source_stream_digest,
            "last_source_sequence": snapshot.last_source_sequence,
            "as_of": _decimal_text(as_of_value),
            "absolute_tolerance": _decimal_text(policy.absolute_tolerance),
            "relative_tolerance": _decimal_text(policy.relative_tolerance),
            "stale_after_s": _decimal_text(policy.stale_after_s),
            "overall_status": overall.value,
            "unresolved_capital": _decimal_text(snapshot.capital_unresolved),
            "unreconciled_capital": _decimal_text(capital_reconciliation),
            "ppl_observation_digest": ppl_digest,
            "simulator_observation_digest": simulator_digest,
            "external_observation_digest": external_digest,
            "record_ids": [record.record_id for record in records],
            "record_statuses": [record.status.value for record in records],
        },
    )

    return FinancialReconciliationSnapshot(
        reconciliation_id=reconciliation_id,
        schema_version=FIN_RECONCILIATION_SCHEMA_VERSION,
        paper_epoch_id=snapshot.paper_epoch_id,
        financial_snapshot_id=snapshot.snapshot_id,
        source_stream_digest=snapshot.source_stream_digest,
        last_source_sequence=snapshot.last_source_sequence,
        as_of=as_of_value,
        policy=policy,
        overall_status=overall,
        unresolved_capital=snapshot.capital_unresolved,
        unreconciled_capital=capital_reconciliation,
        records=tuple(records),
        ppl_observation_digest=ppl_digest,
        simulator_observation_digest=simulator_digest,
        external_observation_digest=external_digest,
    )


__all__ = [
    "Comparability",
    "ExternalFinancialObservation",
    "FIN_RECONCILIATION_SCHEMA_VERSION",
    "FinancialReconciliationSnapshot",
    "ObservationFreshness",
    "PPLFinancialObservation",
    "ReconciliationPolicy",
    "ReconciliationRecord",
    "ReconciliationSourceKind",
    "SimulatorFinancialObservation",
    "ppl_observation_from_events",
    "reconcile_financial_snapshot",
]
