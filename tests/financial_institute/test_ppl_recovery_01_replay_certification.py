from __future__ import annotations

from decimal import Decimal

import pytest

from financial_institute.models import (
    PAPER_LINEAR_FUNDING_EVIDENCE_REF,
    FinancialContext,
    ValuationObservation,
)
from financial_institute.recovery import (
    certify_recovery_replay,
    financial_state_digest,
    ppl_state_digest,
)
from financial_institute.snapshot import build_financial_snapshot
from financial_institute.valuation import ValuationError
from paper_trading.durable_event_store import AppendStatus, DurableEventStore
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
    make_recovery_completed_event,
)
from paper_trading.paper_portfolio_ledger import project
from paper_trading.ppl_recovery import RestartDisposition, plan_restart_recovery


EPOCH = "PPL-RECOVERY-01-TEST-EPOCH"


def _context() -> FinancialContext:
    return FinancialContext(
        fin_code_sha="fin-recovery-source-sha",
        funding_status="NOT_APPLICABLE",
        funding_evidence_ref=PAPER_LINEAR_FUNDING_EVIDENCE_REF,
        strategy_id="recovery-test-strategy",
        strategy_version="v1",
        experiment_id="recovery-test-experiment",
        venue="MEXC_SIM",
        market_type="PAPER_SWAP_MODEL",
    )


def _birth():
    return make_epoch_created_event(
        event_id="ev-1-epoch",
        paper_epoch_id=EPOCH,
        sequence=1,
        timestamp=1.0,
        initial_virtual_capital=1000.0,
        code_sha="ppl-source-sha",
        config_snapshot_hash="cfg-hash",
        schema_version=2,
    )


def _open():
    return make_position_opened_event(
        event_id="ev-2-open",
        paper_epoch_id=EPOCH,
        sequence=2,
        timestamp=10.0,
        trade_id="trade-1",
        symbol="BTCUSDT",
        side="LONG",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.1,
        decision_id="decision-1",
        schema_version=2,
        tp_price=110.0,
        sl_price=90.0,
        timeout_at=20.0,
        recovery_eligible_until=30.0,
    )


def _close():
    return make_position_closed_event(
        event_id="ev-3-close",
        paper_epoch_id=EPOCH,
        sequence=3,
        timestamp=18.0,
        trade_id="trade-1",
        exit_price=110.0,
        exit_fee=0.2,
        decision_id="decision-1",
        schema_version=2,
    )


def _unresolved():
    return make_position_unresolved_event(
        event_id="ev-3-unresolved",
        paper_epoch_id=EPOCH,
        sequence=3,
        timestamp=31.0,
        trade_id="trade-1",
        reason="recovery_window_expired_without_exact_outcome",
        decision_id="decision-1",
        schema_version=2,
    )


def _recovery_completed():
    return make_recovery_completed_event(
        event_id="ev-4-recovery-completed",
        paper_epoch_id=EPOCH,
        sequence=4,
        timestamp=32.0,
        restored_count=0,
        unresolved_count=1,
        schema_version=2,
    )


def _mark(
    *,
    price: str = "105",
    source_timestamp: str = "15",
    symbol: str = "BTCUSDT",
) -> ValuationObservation:
    return ValuationObservation(
        trade_id="trade-1",
        symbol=symbol,
        source_id="market-observer:recovery-test",
        venue="MEXC",
        market_type="swap",
        price=Decimal(price),
        source_timestamp=Decimal(source_timestamp),
    )


def _store(tmp_path, events):
    root = tmp_path / "ppl-store"
    store = DurableEventStore(root)
    for event in events:
        store.append(EPOCH, event)
    return root, store


def test_open_position_replays_exactly_across_independent_store_instances(
    tmp_path,
) -> None:
    root, _ = _store(tmp_path, [_birth(), _open()])

    proof = certify_recovery_replay(
        root_dir=root,
        paper_epoch_id=EPOCH,
        context=_context(),
        observations=[_mark()],
        valuation_as_of=Decimal("16"),
        max_mark_age_s=Decimal("5"),
        restart_now=15.0,
    )

    assert proof.source_event_count == 2
    assert proof.last_source_sequence == 2
    assert proof.exact_replay_equivalent is True
    assert (
        proof.source_stream_digest_before
        == proof.source_stream_digest_after
    )
    assert proof.ppl_state_digest_before == proof.ppl_state_digest_after
    assert (
        proof.financial_snapshot_id_before
        == proof.financial_snapshot_id_after
    )
    assert (
        proof.financial_state_digest_before
        == proof.financial_state_digest_after
    )


def test_restart_plan_replays_from_durable_deadlines_only(tmp_path) -> None:
    root, _ = _store(tmp_path, [_birth(), _open()])
    events = DurableEventStore(root).load_epoch(EPOCH)
    state = project(events)

    monitoring = plan_restart_recovery(state, now=15.0)
    timeout_due = plan_restart_recovery(state, now=20.0)
    unresolved_required = plan_restart_recovery(state, now=30.0001)

    assert monitoring.positions[0].disposition is RestartDisposition.RESTORE_MONITORING
    assert timeout_due.positions[0].disposition is RestartDisposition.RESTORE_TIMEOUT_DUE
    assert (
        unresolved_required.positions[0].disposition
        is RestartDisposition.UNRESOLVED_REQUIRED
    )

    # Planning is read-only: expiry does not fabricate an UNRESOLVED event.
    reloaded = project(DurableEventStore(root).load_epoch(EPOCH))
    assert reloaded.reserved_principal == 10.0
    assert reloaded.unresolved_capital == 0.0
    assert tuple(reloaded.unresolved_positions) == ()


def test_close_is_not_double_applied_after_restart_or_idempotent_retry(
    tmp_path,
) -> None:
    root, store = _store(tmp_path, [_birth(), _open()])
    close = _close()

    first = store.append(EPOCH, close)
    retry = store.append(EPOCH, close)

    assert first.status is AppendStatus.APPENDED
    assert retry.status is AppendStatus.ALREADY_EXISTS

    events_before = DurableEventStore(root).load_epoch(EPOCH)
    state_before = project(events_before)
    snapshot_before = build_financial_snapshot(
        events_before,
        _context(),
        [],
        valuation_as_of=Decimal("19"),
        max_mark_age_s=Decimal("5"),
    )

    events_after = DurableEventStore(root).load_epoch(EPOCH)
    state_after = project(events_after)
    snapshot_after = build_financial_snapshot(
        events_after,
        _context(),
        [],
        valuation_as_of=Decimal("19"),
        max_mark_age_s=Decimal("5"),
    )

    assert len(events_after) == 3
    assert state_before == state_after
    assert ppl_state_digest(state_before) == ppl_state_digest(state_after)

    # Principal release, fees and PnL appear once, not once per process replay.
    assert state_after.reserved_principal == 0.0
    assert state_after.available_cash == pytest.approx(1000.7)
    assert state_after.fees_paid == pytest.approx(0.3)
    assert state_after.realized_pnl == pytest.approx(0.7)

    assert snapshot_after.capital_reserved == Decimal("0.0")
    assert snapshot_after.cash_available == Decimal("1000.7")
    assert snapshot_after.fees_paid == Decimal("0.3")
    assert snapshot_after.gross_realized_price_pnl == Decimal("1.0")
    assert snapshot_after.realized_pnl == Decimal("0.7")
    assert (
        snapshot_after.funding_evidence_ref
        == PAPER_LINEAR_FUNDING_EVIDENCE_REF
    )
    assert snapshot_before.snapshot_id == snapshot_after.snapshot_id
    assert financial_state_digest(snapshot_before) == financial_state_digest(
        snapshot_after
    )


def test_unresolved_evidence_survives_restart_without_fake_equity(tmp_path) -> None:
    root, _ = _store(
        tmp_path,
        [_birth(), _open(), _unresolved(), _recovery_completed()],
    )

    proof = certify_recovery_replay(
        root_dir=root,
        paper_epoch_id=EPOCH,
        context=_context(),
        observations=[],
        valuation_as_of=Decimal("33"),
        max_mark_age_s=Decimal("5"),
        restart_now=33.0,
    )
    assert proof.exact_replay_equivalent is True

    events = DurableEventStore(root).load_epoch(EPOCH)
    state = project(events)
    snapshot = build_financial_snapshot(
        events,
        _context(),
        [],
        valuation_as_of=Decimal("33"),
        max_mark_age_s=Decimal("5"),
    )

    assert state.reserved_principal == 0.0
    assert state.unresolved_capital == 10.0
    assert state.realized_pnl == 0.0
    assert state.restored_count_total == 0
    assert state.unresolved_count_total == 1
    assert tuple(state.unresolved_positions) == ("trade-1",)

    assert snapshot.capital_reserved == Decimal("0.0")
    assert snapshot.capital_unresolved == Decimal("10.0")
    assert snapshot.certified_equity is None
    assert snapshot.unresolved_position_count == 1


def test_fin_projection_failure_cannot_mutate_authoritative_ppl_bytes(
    tmp_path,
) -> None:
    root, _ = _store(tmp_path, [_birth(), _open()])
    epoch_file = next((root / "epochs").glob("*.jsonl"))
    bytes_before = epoch_file.read_bytes()
    events_before = DurableEventStore(root).load_epoch(EPOCH)
    state_digest_before = ppl_state_digest(project(events_before))

    with pytest.raises(ValuationError, match="symbol mismatch"):
        build_financial_snapshot(
            events_before,
            _context(),
            [_mark(symbol="ETHUSDT")],
            valuation_as_of=Decimal("16"),
            max_mark_age_s=Decimal("5"),
        )

    bytes_after = epoch_file.read_bytes()
    events_after = DurableEventStore(root).load_epoch(EPOCH)
    state_digest_after = ppl_state_digest(project(events_after))

    assert bytes_after == bytes_before
    assert events_after == events_before
    assert state_digest_after == state_digest_before


def test_recovery_certificate_is_fail_closed_on_changed_explicit_inputs(
    tmp_path,
) -> None:
    root, _ = _store(tmp_path, [_birth(), _open()])

    first = certify_recovery_replay(
        root_dir=root,
        paper_epoch_id=EPOCH,
        context=_context(),
        observations=[_mark(price="105")],
        valuation_as_of=Decimal("16"),
        max_mark_age_s=Decimal("5"),
        restart_now=15.0,
    )
    second = certify_recovery_replay(
        root_dir=root,
        paper_epoch_id=EPOCH,
        context=_context(),
        observations=[_mark(price="106")],
        valuation_as_of=Decimal("16"),
        max_mark_age_s=Decimal("5"),
        restart_now=15.0,
    )

    assert first.source_stream_digest_before == second.source_stream_digest_before
    assert first.ppl_state_digest_before == second.ppl_state_digest_before
    assert (
        first.financial_snapshot_id_before
        != second.financial_snapshot_id_before
    )
    assert (
        first.financial_state_digest_before
        != second.financial_state_digest_before
    )
