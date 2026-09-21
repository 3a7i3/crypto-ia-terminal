from __future__ import annotations

from decimal import Decimal

import pytest

from financial_institute.models import FinancialContext, ValuationObservation
from financial_institute.ppl_adapter import adapt_ppl_stream
from financial_institute.semantics import (
    EvidenceStatus,
    FinancialModel,
    ValuationStatus,
)
from financial_institute.snapshot import build_financial_snapshot
from financial_institute.valuation import ValuationError
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
    make_recovery_completed_event,
)


EPOCH = "F00-EPOCH-FIN01-TEST"


def birth():
    return make_epoch_created_event(
        event_id="e1",
        paper_epoch_id=EPOCH,
        sequence=1,
        timestamp=1000.0,
        initial_virtual_capital=1000.0,
        code_sha="source-sha",
        config_snapshot_hash="config-hash",
        schema_version=2,
    )


def opened(*, sequence: int = 2, trade_id: str = "t1"):
    return make_position_opened_event(
        event_id=f"e{sequence}",
        paper_epoch_id=EPOCH,
        sequence=sequence,
        timestamp=1001.0,
        trade_id=trade_id,
        symbol="BTCUSDT",
        side="LONG",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        decision_id="d1",
        schema_version=2,
        tp_price=110.0,
        sl_price=90.0,
        timeout_at=1100.0,
        recovery_eligible_until=1200.0,
    )


def context(
    *,
    funding_status: EvidenceStatus = EvidenceStatus.NOT_APPLICABLE,
    strategy_id: str | None = None,
    experiment_id: str | None = None,
    fin_code_sha: str = "fin-sha",
) -> FinancialContext:
    return FinancialContext(
        fin_code_sha=fin_code_sha,
        funding_status=funding_status,
        strategy_id=strategy_id,
        strategy_version="v1" if strategy_id else None,
        experiment_id=experiment_id,
        venue="MEXC_SIM",
        market_type="PAPER_SWAP_MODEL",
    )


def live_mark(*, price: str = "105", source_timestamp: str = "1002"):
    return ValuationObservation(
        trade_id="t1",
        symbol="BTCUSDT",
        source_id="market-observer:test",
        venue="MEXC",
        market_type="swap",
        price=Decimal(price),
        source_timestamp=Decimal(source_timestamp),
    )


def test_open_snapshot_exposes_financial_truth_with_live_mark() -> None:
    snapshot = build_financial_snapshot(
        [birth(), opened()],
        context(),
        [live_mark()],
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )

    assert snapshot.initial_epoch_capital == Decimal("1000.0")
    assert snapshot.cash_available == Decimal("989.99")
    assert snapshot.capital_reserved == Decimal("10.0")
    assert snapshot.capital_deployed == Decimal("10.0")
    assert snapshot.capital_unresolved == Decimal("0")
    assert snapshot.fees_paid == Decimal("0.01")
    assert snapshot.gross_realized_price_pnl == Decimal("0")
    assert snapshot.realized_pnl == Decimal("-0.01")
    assert snapshot.known_unrealized_pnl == Decimal("0.5")
    assert snapshot.unrealized_pnl == Decimal("0.5")
    assert snapshot.certified_equity == Decimal("1000.49")
    assert snapshot.evidence_status is EvidenceStatus.COMPLETE
    assert snapshot.valuation_statuses == (ValuationStatus.LIVE,)


def test_same_inputs_replay_to_identical_snapshot() -> None:
    events = [birth(), opened()]
    marks = [live_mark()]
    kwargs = dict(
        events=events,
        context=context(),
        observations=marks,
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )

    first = build_financial_snapshot(**kwargs)
    second = build_financial_snapshot(**kwargs)

    assert first == second
    assert first.snapshot_id == second.snapshot_id
    assert first.source_stream_digest == second.source_stream_digest



def test_semantic_context_changes_financial_and_snapshot_identity() -> None:
    events = [birth(), opened()]
    marks = [live_mark()]
    first = build_financial_snapshot(
        events,
        context(strategy_id="strategy-a"),
        marks,
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )
    second = build_financial_snapshot(
        events,
        context(strategy_id="strategy-b"),
        marks,
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )
    assert first.semantic_context_digest != second.semantic_context_digest
    assert first.snapshot_id != second.snapshot_id

    adapted_a = adapt_ppl_stream(events, context(strategy_id="strategy-a"))
    adapted_b = adapt_ppl_stream(events, context(strategy_id="strategy-b"))
    assert (
        adapted_a.financial_events[0].financial_event_id
        != adapted_b.financial_events[0].financial_event_id
    )


def test_decimal_fin_projection_does_not_fail_on_ppl_float_accumulation_artifact() -> None:
    open_event = make_position_opened_event(
        event_id="e2",
        paper_epoch_id=EPOCH,
        sequence=2,
        timestamp=1001.0,
        trade_id="t1",
        symbol="BTCUSDT",
        side="LONG",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.1,
        decision_id="d1",
        schema_version=2,
        tp_price=110.0,
        sl_price=90.0,
        timeout_at=1100.0,
        recovery_eligible_until=1200.0,
    )
    close_event = make_position_closed_event(
        event_id="e3",
        paper_epoch_id=EPOCH,
        sequence=3,
        timestamp=1004.0,
        trade_id="t1",
        exit_price=100.0,
        exit_fee=0.2,
        decision_id="d1",
        schema_version=2,
    )
    snapshot = build_financial_snapshot(
        [birth(), open_event, close_event],
        context(),
        [],
        valuation_as_of=Decimal("1005"),
        max_mark_age_s=Decimal("10"),
    )
    assert snapshot.fees_paid == Decimal("0.3")
    assert snapshot.realized_pnl == Decimal("-0.3")
    assert snapshot.cash_available == Decimal("999.7")


def test_fin_code_sha_is_snapshot_provenance() -> None:
    events = [birth(), opened()]
    marks = [live_mark()]
    first = build_financial_snapshot(
        events,
        context(fin_code_sha="fin-a"),
        marks,
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )
    second = build_financial_snapshot(
        events,
        context(fin_code_sha="fin-b"),
        marks,
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )
    assert first.snapshot_id != second.snapshot_id


def test_stale_mark_is_visible_but_cannot_certify_equity() -> None:
    snapshot = build_financial_snapshot(
        [birth(), opened()],
        context(),
        [live_mark(source_timestamp="900")],
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )
    assert snapshot.valuation_statuses == (ValuationStatus.STALE,)
    assert snapshot.known_unrealized_pnl == Decimal("0.5")
    assert snapshot.unrealized_pnl is None
    assert snapshot.certified_equity is None
    assert snapshot.evidence_status is EvidenceStatus.PARTIAL


def test_missing_mark_is_unresolved_not_zero() -> None:
    snapshot = build_financial_snapshot(
        [birth(), opened()],
        context(),
        [],
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )
    assert snapshot.valuation_statuses == (ValuationStatus.UNAVAILABLE,)
    assert snapshot.unrealized_pnl is None
    assert snapshot.certified_equity is None
    assert snapshot.evidence_status is EvidenceStatus.UNRESOLVED


def test_unknown_funding_blocks_realized_pnl_and_equity() -> None:
    snapshot = build_financial_snapshot(
        [birth(), opened()],
        context(funding_status=EvidenceStatus.UNRESOLVED),
        [live_mark()],
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )
    assert snapshot.funding_net is None
    assert snapshot.realized_pnl is None
    assert snapshot.certified_equity is None
    assert snapshot.evidence_status is EvidenceStatus.UNRESOLVED


def test_close_releases_principal_and_recognizes_net_result() -> None:
    close = make_position_closed_event(
        event_id="e3",
        paper_epoch_id=EPOCH,
        sequence=3,
        timestamp=1004.0,
        trade_id="t1",
        exit_price=110.0,
        exit_fee=0.01,
        decision_id="d1",
        schema_version=2,
    )
    snapshot = build_financial_snapshot(
        [birth(), opened(), close],
        context(),
        [],
        valuation_as_of=Decimal("1005"),
        max_mark_age_s=Decimal("10"),
    )
    assert snapshot.cash_available == Decimal("1000.98")
    assert snapshot.capital_reserved == Decimal("0.0")
    assert snapshot.gross_realized_price_pnl == Decimal("1.0")
    assert snapshot.fees_paid == Decimal("0.02")
    assert snapshot.realized_pnl == Decimal("0.98")
    assert snapshot.unrealized_pnl == Decimal("0")
    assert snapshot.certified_equity == Decimal("1000.98")
    assert snapshot.settled_position_count == 1


def test_unresolved_position_preserves_principal_without_equity_claim() -> None:
    unresolved = make_position_unresolved_event(
        event_id="e3",
        paper_epoch_id=EPOCH,
        sequence=3,
        timestamp=1004.0,
        trade_id="t1",
        reason="missing_exact_outcome",
        decision_id="d1",
        schema_version=2,
    )
    snapshot = build_financial_snapshot(
        [birth(), opened(), unresolved],
        context(),
        [],
        valuation_as_of=Decimal("1005"),
        max_mark_age_s=Decimal("10"),
    )
    assert snapshot.cash_available == Decimal("989.99")
    assert snapshot.capital_reserved == Decimal("0.0")
    assert snapshot.capital_unresolved == Decimal("10.0")
    assert snapshot.certified_equity is None
    assert snapshot.evidence_status is EvidenceStatus.UNRESOLVED
    assert snapshot.unresolved_position_count == 1


def test_recovery_marker_changes_source_identity_not_financial_balances() -> None:
    unresolved = make_position_unresolved_event(
        event_id="e3",
        paper_epoch_id=EPOCH,
        sequence=3,
        timestamp=1004.0,
        trade_id="t1",
        reason="missing_exact_outcome",
        schema_version=2,
    )
    recovery = make_recovery_completed_event(
        event_id="e4",
        paper_epoch_id=EPOCH,
        sequence=4,
        timestamp=1005.0,
        restored_count=0,
        unresolved_count=1,
        schema_version=2,
    )
    adapted = adapt_ppl_stream(
        [birth(), opened(), unresolved, recovery],
        context(),
    )
    assert len(adapted.financial_events) == 3
    assert adapted.last_source_sequence == 4


def test_attribution_is_explicit_and_never_inferred() -> None:
    missing = build_financial_snapshot(
        [birth()],
        context(),
        [],
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )
    assert missing.strategy_id is None
    assert missing.strategy_attribution_status is EvidenceStatus.UNRESOLVED
    assert missing.experiment_id is None
    assert missing.experiment_attribution_status is EvidenceStatus.UNRESOLVED

    explicit = build_financial_snapshot(
        [birth()],
        context(strategy_id="mean-reversion", experiment_id="F00-test"),
        [],
        valuation_as_of=Decimal("1003"),
        max_mark_age_s=Decimal("10"),
    )
    assert explicit.strategy_attribution_status is EvidenceStatus.COMPLETE
    assert explicit.experiment_attribution_status is EvidenceStatus.COMPLETE


def test_duplicate_or_non_open_valuation_evidence_fails_closed() -> None:
    duplicate = [live_mark(), live_mark()]
    with pytest.raises(ValuationError, match="duplicate"):
        build_financial_snapshot(
            [birth(), opened()],
            context(),
            duplicate,
            valuation_as_of=Decimal("1003"),
            max_mark_age_s=Decimal("10"),
        )


def test_exchange_faithful_models_are_not_accepted_by_fin01() -> None:
    with pytest.raises(ValueError, match="PAPER_LINEAR_PRINCIPAL_V1"):
        FinancialContext(
            fin_code_sha="fin-sha",
            financial_model=FinancialModel.DERIVATIVE_CONTRACT,
        )
