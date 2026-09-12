"""Tests for paper_trading/paper_portfolio_ledger.py (PPL-02A).

Includes a regression test (`test_regression_mexc_simulator_double_charges_entry_fee`)
demonstrating that the arithmetic currently used by
`paper_trading/mexc_simulator.py::_fill_market`/`_close_position` (confirmed
in PPL-01R's ENTRY_FEE_DEFECT_VERDICT) would violate this module's canonical
accounting identity — MexcSimulator itself is NOT imported or modified here,
this test only reproduces its documented formula inline to prove the
canonical model rejects it.
"""

import pytest

from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
    make_recovery_completed_event,
)
from paper_trading.paper_portfolio_ledger import (
    CloseWithoutOpenError,
    DoubleCloseError,
    DuplicateEventError,
    DuplicateOpenError,
    EpochMismatchError,
    IllegalTransitionError,
    NegativeCashError,
    SequenceGapError,
    SequenceRegressionError,
    project,
)

EPOCH = "pe-core-001"


def epoch_created(seq=1, capital=100.0, **kw):
    return make_epoch_created_event(
        event_id=f"ev-epoch-{seq}",
        paper_epoch_id=EPOCH,
        sequence=seq,
        timestamp=0.0,
        initial_virtual_capital=capital,
        code_sha="sha",
        config_snapshot_hash="cfg",
        **kw,
    )


def opened(seq, trade_id, principal=10.0, entry_price=100.0, entry_fee=0.01, symbol="BTCUSDT", side="BUY"):
    return make_position_opened_event(
        event_id=f"ev-open-{trade_id}-{seq}",
        paper_epoch_id=EPOCH,
        sequence=seq,
        timestamp=float(seq),
        trade_id=trade_id,
        symbol=symbol,
        side=side,
        principal=principal,
        entry_price=entry_price,
        entry_fee=entry_fee,
    )


def closed(seq, trade_id, exit_price=110.0, gross_pnl=1.0, exit_fee=0.01):
    return make_position_closed_event(
        event_id=f"ev-close-{trade_id}-{seq}",
        paper_epoch_id=EPOCH,
        sequence=seq,
        timestamp=float(seq),
        trade_id=trade_id,
        exit_price=exit_price,
        gross_pnl=gross_pnl,
        exit_fee=exit_fee,
    )


def unresolved(seq, trade_id, reason="expired_on_restore"):
    return make_position_unresolved_event(
        event_id=f"ev-unresolved-{trade_id}-{seq}",
        paper_epoch_id=EPOCH,
        sequence=seq,
        timestamp=float(seq),
        trade_id=trade_id,
        reason=reason,
    )


# ── Epoch creation ──────────────────────────────────────────────────────


def test_epoch_creation_sets_initial_state():
    state = project([epoch_created(capital=250.0)])
    assert state.paper_epoch_id == EPOCH
    assert state.available_cash == 250.0
    assert state.reserved_principal == 0.0
    assert state.unresolved_capital == 0.0
    assert state.realized_pnl == 0.0
    assert state.fees_paid == 0.0


def test_first_event_must_be_epoch_created():
    with pytest.raises(IllegalTransitionError):
        project([opened(1, "t1")])


def test_epoch_created_cannot_appear_twice():
    with pytest.raises(IllegalTransitionError):
        project([epoch_created(seq=1), epoch_created(seq=2)])


# ── Single open / close ─────────────────────────────────────────────────


def test_single_open():
    state = project([epoch_created(capital=100.0), opened(2, "t1", principal=10.0, entry_fee=0.01)])
    assert state.available_cash == pytest.approx(100.0 - 10.0 - 0.01)
    assert state.reserved_principal == pytest.approx(10.0)
    assert state.fees_paid == pytest.approx(0.01)
    assert "t1" in state.open_positions


def test_single_profitable_close():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.01),
        closed(3, "t1", gross_pnl=1.0, exit_fee=0.01),
    ]
    state = project(events)
    assert state.reserved_principal == pytest.approx(0.0)
    assert "t1" not in state.open_positions
    assert "t1" in state.closed_trade_ids
    # trade_realized_pnl = gross_pnl - entry_fee - exit_fee = 1.0 - 0.01 - 0.01
    assert state.realized_pnl == pytest.approx(1.0 - 0.01 - 0.01)
    # available_cash = 100 -10 -0.01 (open) +10 +1.0 -0.01 (close)
    expected_cash = (100.0 - 10.0 - 0.01) + 10.0 + 1.0 - 0.01
    assert state.available_cash == pytest.approx(expected_cash)
    assert state.fees_paid == pytest.approx(0.02)


def test_single_losing_close():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.01),
        closed(3, "t1", gross_pnl=-2.0, exit_fee=0.01),
    ]
    state = project(events)
    assert state.realized_pnl == pytest.approx(-2.0 - 0.01 - 0.01)
    expected_cash = (100.0 - 10.0 - 0.01) + 10.0 - 2.0 - 0.01
    assert state.available_cash == pytest.approx(expected_cash)


def test_entry_fee_charged_exactly_once():
    """Round-trip cash delta must reflect entry_fee exactly once total."""
    entry_fee = 0.05
    exit_fee = 0.03
    principal = 10.0
    gross_pnl = 0.0  # isolate fee effect from price movement
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=principal, entry_fee=entry_fee),
        closed(3, "t1", gross_pnl=gross_pnl, exit_fee=exit_fee),
    ]
    state = project(events)
    # Round trip with zero price movement: cash should end at
    # initial - entry_fee - exit_fee (principal returns in full).
    expected = 100.0 - entry_fee - exit_fee
    assert state.available_cash == pytest.approx(expected)
    assert state.realized_pnl == pytest.approx(-entry_fee - exit_fee)


def test_exit_fee_charged_exactly_once():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.0),
        closed(3, "t1", gross_pnl=0.0, exit_fee=0.07),
    ]
    state = project(events)
    assert state.fees_paid == pytest.approx(0.07)
    assert state.available_cash == pytest.approx(100.0 - 0.07)


# ── Multiple trades ──────────────────────────────────────────────────────


def test_multiple_sequential_trades():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.01),
        closed(3, "t1", gross_pnl=1.0, exit_fee=0.01),
        opened(4, "t2", principal=20.0, entry_fee=0.02),
        closed(5, "t2", gross_pnl=-1.0, exit_fee=0.02),
    ]
    state = project(events)
    assert "t1" in state.closed_trade_ids
    assert "t2" in state.closed_trade_ids
    assert state.reserved_principal == pytest.approx(0.0)
    expected_realized = (1.0 - 0.01 - 0.01) + (-1.0 - 0.02 - 0.02)
    assert state.realized_pnl == pytest.approx(expected_realized)


def test_multiple_simultaneous_open_positions():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.01, symbol="BTCUSDT"),
        opened(3, "t2", principal=20.0, entry_fee=0.02, symbol="ETHUSDT"),
    ]
    state = project(events)
    assert set(state.open_positions.keys()) == {"t1", "t2"}
    assert state.reserved_principal == pytest.approx(30.0)
    assert state.available_cash == pytest.approx(100.0 - 10.0 - 0.01 - 20.0 - 0.02)


# ── Unrealized PnL (equity query, not part of replay) ────────────────────


def test_unrealized_pnl_projection_via_equity():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.0, entry_price=100.0, symbol="BTCUSDT", side="BUY"),
    ]
    state = project(events)
    breakdown = state.equity(mark_prices={"BTCUSDT": 110.0})
    assert breakdown.unrealized_pnl == pytest.approx(10.0 * ((110.0 - 100.0) / 100.0))
    assert breakdown.reserved_principal == pytest.approx(10.0)
    assert breakdown.equity == pytest.approx(
        breakdown.available_cash + breakdown.reserved_principal + breakdown.unrealized_pnl
    )


def test_equity_without_mark_prices_omits_unrealized_but_keeps_principal():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.0),
    ]
    state = project(events)
    breakdown = state.equity()
    assert breakdown.unrealized_pnl == 0.0
    assert breakdown.reserved_principal == pytest.approx(10.0)


# ── Unknown outcome contract ──────────────────────────────────────────────


def test_unknown_outcome_moves_principal_to_unresolved_not_available_cash():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.01),
        unresolved(3, "t1", reason="expired_on_restore"),
    ]
    state = project(events)
    assert "t1" not in state.open_positions
    assert "t1" in state.unresolved_positions
    assert state.unresolved_capital == pytest.approx(10.0)
    assert state.reserved_principal == pytest.approx(0.0)
    # principal must NOT have flowed into available_cash
    assert state.available_cash == pytest.approx(100.0 - 10.0 - 0.01)


def test_unknown_outcome_never_becomes_zero_pnl():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.01),
        unresolved(3, "t1"),
    ]
    state = project(events)
    # realized_pnl must remain untouched by the unresolved position — it is
    # not incremented by 0, it is simply not counted at all.
    assert state.realized_pnl == 0.0
    assert "t1" not in state.closed_trade_ids
    assert state.unresolved_count_total == 1


def test_unresolved_then_double_resolve_rejected():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.0),
        unresolved(3, "t1"),
    ]
    # A position already resolved as unresolved must not be closeable —
    # fails closed as DoubleCloseError (it is, in effect, already resolved).
    with pytest.raises(DoubleCloseError):
        project(events + [closed(4, "t1")])
    with pytest.raises(IllegalTransitionError):
        project(events + [unresolved(4, "t1")])


def test_equity_reports_unresolved_capital_separately_from_certified():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.0),
        unresolved(3, "t1"),
    ]
    state = project(events)
    breakdown = state.equity()
    assert breakdown.unresolved_capital == pytest.approx(10.0)
    assert breakdown.certified_equity == pytest.approx(90.0)
    assert breakdown.equity == pytest.approx(100.0)
    assert breakdown.certified_equity != breakdown.equity


# ── Idempotency / fail-closed contract ────────────────────────────────────


def test_duplicate_event_id_rejected():
    ev1 = epoch_created(seq=1)
    ev2 = opened(2, "t1")
    ev_dup = make_position_opened_event(
        event_id=ev2.event_id,  # duplicate event_id, different trade_id
        paper_epoch_id=EPOCH,
        sequence=3,
        timestamp=3.0,
        trade_id="t2",
        symbol="ETHUSDT",
        side="BUY",
        principal=5.0,
        entry_price=1.0,
        entry_fee=0.0,
    )
    with pytest.raises(DuplicateEventError):
        project([ev1, ev2, ev_dup])


def test_sequence_gap_rejected():
    events = [epoch_created(seq=1), opened(3, "t1")]  # skips seq=2
    with pytest.raises(SequenceGapError):
        project(events)


def test_sequence_regression_rejected():
    events = [epoch_created(seq=1), opened(2, "t1"), opened(2, "t2")]
    with pytest.raises(SequenceRegressionError):
        project(events)


def test_double_open_rejected():
    events = [epoch_created(seq=1), opened(2, "t1"), opened(3, "t1")]
    with pytest.raises(DuplicateOpenError):
        project(events)


def test_close_without_open_rejected():
    events = [epoch_created(seq=1), closed(2, "t1")]
    with pytest.raises(CloseWithoutOpenError):
        project(events)


def test_double_close_rejected():
    events = [
        epoch_created(seq=1),
        opened(2, "t1"),
        closed(3, "t1"),
    ]
    with pytest.raises(DoubleCloseError):
        project(events + [closed(4, "t1")])


def test_reopen_of_closed_trade_id_rejected():
    events = [
        epoch_created(seq=1),
        opened(2, "t1"),
        closed(3, "t1"),
    ]
    with pytest.raises(IllegalTransitionError):
        project(events + [opened(4, "t1")])


def test_epoch_mismatch_rejected():
    ev1 = epoch_created(seq=1)
    ev2 = make_position_opened_event(
        event_id="ev-wrong-epoch",
        paper_epoch_id="pe-different",
        sequence=2,
        timestamp=2.0,
        trade_id="t1",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.0,
    )
    with pytest.raises(EpochMismatchError):
        project([ev1, ev2])


def test_negative_available_cash_rejected():
    events = [epoch_created(seq=1, capital=5.0), opened(2, "t1", principal=10.0, entry_fee=0.0)]
    with pytest.raises(NegativeCashError):
        project(events)


def test_recovery_completed_event_is_bookkeeping_only():
    events = [
        epoch_created(seq=1),
        make_recovery_completed_event(
            event_id="ev-rec",
            paper_epoch_id=EPOCH,
            sequence=2,
            timestamp=2.0,
            restored_count=3,
            unresolved_count=1,
        ),
    ]
    state = project(events)
    assert state.restored_count_total == 3
    assert state.available_cash == 100.0  # unaffected


# ── Determinism / replay ───────────────────────────────────────────────


def test_restart_replay_determinism_same_events_same_state():
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=10.0, entry_fee=0.01),
        closed(3, "t1", gross_pnl=1.0, exit_fee=0.01),
        opened(4, "t2", principal=5.0, entry_fee=0.005),
    ]
    state_a = project(events)
    state_b = project(events)  # simulate a restart replaying the same log
    assert state_a.available_cash == state_b.available_cash
    assert state_a.reserved_principal == state_b.reserved_principal
    assert state_a.realized_pnl == state_b.realized_pnl
    assert state_a.open_positions.keys() == state_b.open_positions.keys()


def test_different_event_order_rejected_where_causal_order_invalid():
    # CLOSE before OPEN for the same trade_id, sequence otherwise valid.
    events_reordered = [
        epoch_created(seq=1),
        closed(2, "t1"),
        opened(3, "t1"),
    ]
    with pytest.raises(CloseWithoutOpenError):
        project(events_reordered)


# ── Regression: reproduce MexcSimulator's confirmed double fee-charge ────


def test_regression_mexc_simulator_double_charges_entry_fee():
    """PPL-01R ENTRY_FEE_DEFECT_VERDICT, reproduced without importing
    MexcSimulator: its documented formula is

        at OPEN:  capital -= size + fee_entry
        at CLOSE: pnl_usd = size*gross_pct - fee_exit - fee_entry
                  capital += size + pnl_usd

    which nets to `capital` being short by exactly one extra `fee_entry`
    per round trip versus the canonical single-charge identity this module
    implements. This test proves the two arithmetic models diverge by
    exactly `fee_entry`, and that the canonical ledger does NOT reproduce
    the defect.
    """
    size = 10.0
    fee_entry = 0.05
    fee_exit = 0.03
    gross_pct = 0.0  # isolate fee effect

    # -- MexcSimulator's own (defective) arithmetic, reproduced inline --
    mexc_capital = 100.0
    mexc_capital -= size + fee_entry  # _fill_market:813
    pnl_usd = size * gross_pct - fee_exit - fee_entry  # _close_position:996
    mexc_capital += size + pnl_usd  # _close_position:1006
    mexc_round_trip_cost = 100.0 - mexc_capital
    assert mexc_round_trip_cost == pytest.approx(fee_exit + 2 * fee_entry)

    # -- canonical PaperPortfolioLedger arithmetic --
    events = [
        epoch_created(capital=100.0),
        opened(2, "t1", principal=size, entry_fee=fee_entry),
        closed(3, "t1", gross_pnl=size * gross_pct, exit_fee=fee_exit),
    ]
    state = project(events)
    canonical_round_trip_cost = 100.0 - state.available_cash
    assert canonical_round_trip_cost == pytest.approx(fee_exit + fee_entry)

    # The defect's exact magnitude: MexcSimulator charges one extra fee_entry.
    assert mexc_round_trip_cost - canonical_round_trip_cost == pytest.approx(fee_entry)
    assert mexc_capital != state.available_cash
