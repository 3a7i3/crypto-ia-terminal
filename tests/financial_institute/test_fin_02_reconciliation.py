from __future__ import annotations

from decimal import Decimal

import pytest

from financial_institute.models import (
    PAPER_LINEAR_FUNDING_EVIDENCE_REF,
    FinancialContext,
)
from financial_institute.reconciliation import (
    Comparability,
    ExternalFinancialObservation,
    ObservationFreshness,
    ReconciliationPolicy,
    ReconciliationSourceKind,
    SimulatorFinancialObservation,
    ppl_observation_from_events,
    reconcile_financial_snapshot,
)
from financial_institute.semantics import EvidenceStatus, ReconciliationStatus
from financial_institute.snapshot import build_financial_snapshot
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
)
from paper_trading.paper_portfolio_ledger import project


EPOCH = "FIN02-TEST-EPOCH"


def _context() -> FinancialContext:
    return FinancialContext(
        fin_code_sha="fin02-code",
        funding_status=EvidenceStatus.NOT_APPLICABLE,
        funding_evidence_ref=PAPER_LINEAR_FUNDING_EVIDENCE_REF,
        experiment_id="FIN02-TEST",
        venue="MEXC_SIM",
        market_type="PAPER_LINEAR",
    )


def _events():
    return (
        make_epoch_created_event(
            event_id="e1",
            paper_epoch_id=EPOCH,
            sequence=1,
            timestamp=1.0,
            initial_virtual_capital=1000.0,
            code_sha="source-sha",
            config_snapshot_hash="cfg",
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="e2",
            paper_epoch_id=EPOCH,
            sequence=2,
            timestamp=2.0,
            trade_id="closed-trade",
            symbol="BTC/USDT",
            side="LONG",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.1,
            decision_id="d1",
            schema_version=2,
            tp_price=110.0,
            sl_price=90.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        ),
        make_position_closed_event(
            event_id="e3",
            paper_epoch_id=EPOCH,
            sequence=3,
            timestamp=3.0,
            trade_id="closed-trade",
            exit_price=110.0,
            exit_fee=0.2,
            decision_id="d1",
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="e4",
            paper_epoch_id=EPOCH,
            sequence=4,
            timestamp=4.0,
            trade_id="open-trade",
            symbol="ETH/USDT",
            side="LONG",
            principal=20.0,
            entry_price=2000.0,
            entry_fee=0.3,
            decision_id="d2",
            schema_version=2,
            tp_price=2200.0,
            sl_price=1900.0,
            timeout_at=40.0,
            recovery_eligible_until=50.0,
        ),
    )


def _snapshot(events=None):
    events = _events() if events is None else events
    return build_financial_snapshot(
        events,
        _context(),
        [],
        valuation_as_of=Decimal("10"),
        max_mark_age_s=Decimal("5"),
    )


def _policy(
    *,
    abs_tol: str = "0.000000000001",
    rel_tol: str = "0",
    stale_after: str = "30",
) -> ReconciliationPolicy:
    return ReconciliationPolicy(
        absolute_tolerance=Decimal(abs_tol),
        relative_tolerance=Decimal(rel_tol),
        stale_after_s=Decimal(stale_after),
    )


def _simulator(events=None, *, cash_delta: str = "0"):
    events = _events() if events is None else events
    state = project(events)
    return SimulatorFinancialObservation(
        observed_at=Decimal("10"),
        cash_available=Decimal(str(state.available_cash))
        + Decimal(cash_delta),
        capital_reserved=Decimal(str(state.reserved_principal)),
        open_position_ids=tuple(state.open_positions),
        lifecycle_transitions_in_flight=0,
        pending_order_count=0,
    )


def _record(result, source_kind, field):
    return next(
        row
        for row in result.records
        if row.source_kind is source_kind and row.field == field
    )


def test_exact_or_explicit_tolerance_reconciliation_without_silent_correction():
    events = _events()
    snapshot = _snapshot(events)
    ppl = ppl_observation_from_events(events, observed_at=Decimal("10"))

    result = reconcile_financial_snapshot(
        snapshot,
        ppl,
        reconciliation_code_sha="fin02-reconciliation-code",
        policy=_policy(),
        as_of=Decimal("10"),
        simulator=_simulator(events),
    )

    assert result.overall_status in {
        ReconciliationStatus.EXACT,
        ReconciliationStatus.WITHIN_TOLERANCE,
    }
    assert result.unreconciled_capital is not None
    assert result.unreconciled_capital <= Decimal("0.000000000001")

    realized = _record(
        result,
        ReconciliationSourceKind.PPL,
        "realized_pnl",
    )
    assert realized.comparability is Comparability.NON_COMPARABLE
    assert realized.status is ReconciliationStatus.UNRESOLVED
    assert realized.projected_value != realized.observed_value
    assert "recognizes charged fees immediately" in (realized.note or "")

    book = _record(
        result,
        ReconciliationSourceKind.SIMULATOR,
        "book_capital_at_cost",
    )
    assert book.comparability is Comparability.COMPARABLE
    assert book.unreconciled_amount is not None


def test_known_simulator_capital_divergence_is_visible_and_not_applied():
    events = _events()
    snapshot = _snapshot(events)
    ppl = ppl_observation_from_events(events, observed_at=Decimal("10"))

    result = reconcile_financial_snapshot(
        snapshot,
        ppl,
        reconciliation_code_sha="fin02-reconciliation-code",
        policy=_policy(abs_tol="0"),
        as_of=Decimal("10"),
        simulator=_simulator(events, cash_delta="1"),
    )

    assert result.overall_status is ReconciliationStatus.DIVERGENT
    assert result.unreconciled_capital == Decimal("1.0")

    cash = _record(
        result,
        ReconciliationSourceKind.SIMULATOR,
        "cash_available",
    )
    assert cash.status is ReconciliationStatus.DIVERGENT
    assert cash.delta_observed_minus_projected == Decimal("1.0")
    assert cash.unreconciled_amount == Decimal("1.0")

    # Reconciliation evidence never mutates the source snapshot.
    assert snapshot.cash_available == _snapshot(events).cash_available
    assert snapshot.capital_reserved == Decimal("20.0")


def test_stale_simulator_values_remain_visible_but_cannot_certify():
    events = _events()
    snapshot = _snapshot(events)
    ppl = ppl_observation_from_events(events, observed_at=Decimal("100"))
    sim = SimulatorFinancialObservation(
        observed_at=Decimal("1"),
        cash_available=snapshot.cash_available,
        capital_reserved=snapshot.capital_reserved,
        open_position_ids=("open-trade",),
        lifecycle_transitions_in_flight=0,
        pending_order_count=0,
    )

    result = reconcile_financial_snapshot(
        snapshot,
        ppl,
        reconciliation_code_sha="fin02-reconciliation-code",
        policy=_policy(stale_after="10"),
        as_of=Decimal("100"),
        simulator=sim,
    )

    assert result.overall_status is ReconciliationStatus.UNRESOLVED
    cash = _record(
        result,
        ReconciliationSourceKind.SIMULATOR,
        "cash_available",
    )
    assert cash.freshness is ObservationFreshness.STALE
    assert cash.delta_observed_minus_projected == Decimal("0.0")
    assert cash.status is ReconciliationStatus.UNRESOLVED


def test_missing_quiescence_evidence_blocks_simulator_certification():
    events = _events()
    snapshot = _snapshot(events)
    ppl = ppl_observation_from_events(events, observed_at=Decimal("10"))
    sim = SimulatorFinancialObservation(
        observed_at=Decimal("10"),
        cash_available=snapshot.cash_available,
        capital_reserved=snapshot.capital_reserved,
        open_position_ids=("open-trade",),
        lifecycle_transitions_in_flight=None,
        pending_order_count=0,
    )

    result = reconcile_financial_snapshot(
        snapshot,
        ppl,
        reconciliation_code_sha="fin02-reconciliation-code",
        policy=_policy(),
        as_of=Decimal("10"),
        simulator=sim,
    )

    quiescence = _record(
        result,
        ReconciliationSourceKind.SIMULATOR,
        "quiescence",
    )
    assert quiescence.comparability is Comparability.UNAVAILABLE
    assert quiescence.status is ReconciliationStatus.UNRESOLVED
    assert result.overall_status is ReconciliationStatus.UNRESOLVED


def test_open_position_identity_mismatch_is_divergent_even_when_count_matches():
    events = _events()
    snapshot = _snapshot(events)
    ppl = ppl_observation_from_events(events, observed_at=Decimal("10"))
    sim = SimulatorFinancialObservation(
        observed_at=Decimal("10"),
        cash_available=snapshot.cash_available,
        capital_reserved=snapshot.capital_reserved,
        open_position_ids=("wrong-trade",),
        lifecycle_transitions_in_flight=0,
        pending_order_count=0,
    )

    result = reconcile_financial_snapshot(
        snapshot,
        ppl,
        reconciliation_code_sha="fin02-reconciliation-code",
        policy=_policy(),
        as_of=Decimal("10"),
        simulator=sim,
    )

    ids = _record(
        result,
        ReconciliationSourceKind.SIMULATOR,
        "open_position_identity_set",
    )
    count = _record(
        result,
        ReconciliationSourceKind.SIMULATOR,
        "open_position_count",
    )
    assert count.status is ReconciliationStatus.EXACT
    assert ids.status is ReconciliationStatus.DIVERGENT
    assert result.overall_status is ReconciliationStatus.DIVERGENT


def test_real_exchange_observation_is_display_only_for_paper_scope():
    events = _events()
    snapshot = _snapshot(events)
    ppl = ppl_observation_from_events(events, observed_at=Decimal("10"))

    external = ExternalFinancialObservation(
        observed_at=Decimal("10"),
        source_id="MEXC_REAL_READ_ONLY",
        asset="USDT",
        free_cash=Decimal("47.5"),
        equity=Decimal("48.2"),
        applicability=ObservationFreshness.NOT_APPLICABLE,
    )

    result = reconcile_financial_snapshot(
        snapshot,
        ppl,
        reconciliation_code_sha="fin02-reconciliation-code",
        policy=_policy(),
        as_of=Decimal("10"),
        simulator=_simulator(events),
        external=external,
    )

    row = _record(
        result,
        ReconciliationSourceKind.EXCHANGE_READ_ONLY,
        "paper_vs_external_account",
    )
    assert row.comparability is Comparability.NOT_APPLICABLE
    assert row.delta_observed_minus_projected is None
    assert "separate accounting scopes" in (row.note or "")
    assert result.overall_status in {
        ReconciliationStatus.EXACT,
        ReconciliationStatus.WITHIN_TOLERANCE,
    }


def test_fin_ppl_identity_mismatch_fails_before_reconciliation():
    events = _events()
    snapshot = _snapshot(events)
    ppl = ppl_observation_from_events(events, observed_at=Decimal("10"))

    tampered = type(ppl)(
        paper_epoch_id=ppl.paper_epoch_id,
        source_stream_digest="different",
        last_sequence=ppl.last_sequence,
        observed_at=ppl.observed_at,
        cash_available=ppl.cash_available,
        capital_reserved=ppl.capital_reserved,
        capital_unresolved=ppl.capital_unresolved,
        lifecycle_realized_pnl=ppl.lifecycle_realized_pnl,
        fees_paid=ppl.fees_paid,
        open_position_ids=ppl.open_position_ids,
        closed_trade_ids=ppl.closed_trade_ids,
        unresolved_position_ids=ppl.unresolved_position_ids,
    )

    with pytest.raises(ValueError, match="source stream digest mismatch"):
        reconcile_financial_snapshot(
            snapshot,
            tampered,
            reconciliation_code_sha="fin02-reconciliation-code",
            policy=_policy(),
            as_of=Decimal("10"),
        )


def test_reconciliation_identity_is_deterministic():
    events = _events()
    snapshot = _snapshot(events)
    ppl = ppl_observation_from_events(events, observed_at=Decimal("10"))
    kwargs = dict(
        reconciliation_code_sha="fin02-reconciliation-code",
        policy=_policy(),
        as_of=Decimal("10"),
        simulator=_simulator(events),
    )

    first = reconcile_financial_snapshot(snapshot, ppl, **kwargs)
    second = reconcile_financial_snapshot(snapshot, ppl, **kwargs)
    changed_code = reconcile_financial_snapshot(
        snapshot,
        ppl,
        **{**kwargs, "reconciliation_code_sha": "fin02-other-code"},
    )

    assert first == second
    assert first.reconciliation_id == second.reconciliation_id
    assert changed_code.reconciliation_id != first.reconciliation_id
