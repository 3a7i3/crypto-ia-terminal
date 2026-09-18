from __future__ import annotations

import pytest

from paper_trading.durable_event_store import DurableEventStore
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
)
from paper_trading.paper_portfolio_ledger import IllegalTransitionError, project
from paper_trading.ppl_recovery import (
    ReplayIncompletePositionError,
    RestartDisposition,
    plan_restart_recovery,
)


EPOCH_V1 = "pe-r2-v1"
EPOCH_V2 = "pe-r2-v2"


def epoch_v1():
    return make_epoch_created_event(
        event_id="ev-v1-epoch",
        paper_epoch_id=EPOCH_V1,
        sequence=1,
        timestamp=1.0,
        initial_virtual_capital=100.0,
        code_sha="sha-v1",
        config_snapshot_hash="cfg-v1",
        schema_version=1,
    )


def epoch_v2():
    return make_epoch_created_event(
        event_id="ev-v2-epoch",
        paper_epoch_id=EPOCH_V2,
        sequence=1,
        timestamp=1.0,
        initial_virtual_capital=100.0,
        code_sha="sha-v2",
        config_snapshot_hash="cfg-v2",
        schema_version=2,
    )


def open_v1():
    return make_position_opened_event(
        event_id="ev-v1-open",
        paper_epoch_id=EPOCH_V1,
        sequence=2,
        timestamp=10.0,
        trade_id="trade-v1",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        schema_version=1,
    )


def open_v2():
    return make_position_opened_event(
        event_id="ev-v2-open",
        paper_epoch_id=EPOCH_V2,
        sequence=2,
        timestamp=10.0,
        trade_id="trade-v2",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        schema_version=2,
        tp_price=104.0,
        sl_price=98.0,
        timeout_at=20.0,
        recovery_eligible_until=30.0,
    )


def close_v2():
    return make_position_closed_event(
        event_id="ev-v2-close",
        paper_epoch_id=EPOCH_V2,
        sequence=3,
        timestamp=18.0,
        trade_id="trade-v2",
        exit_price=103.0,
        exit_fee=0.01,
        schema_version=2,
    )


def test_r2_v2_open_requires_all_replay_terms():
    with pytest.raises(ValueError, match="requires tp_price"):
        make_position_opened_event(
            event_id="ev-bad",
            paper_epoch_id=EPOCH_V2,
            sequence=2,
            timestamp=10.0,
            trade_id="trade-bad",
            symbol="BTCUSDT",
            side="BUY",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            schema_version=2,
        )


@pytest.mark.parametrize(
    ("timeout_at", "recovery_until"),
    [(10.0, 30.0), (20.0, 19.0)],
)
def test_r2_v2_open_rejects_invalid_deadline_order(timeout_at, recovery_until):
    with pytest.raises(ValueError):
        make_position_opened_event(
            event_id="ev-bad-deadline",
            paper_epoch_id=EPOCH_V2,
            sequence=2,
            timestamp=10.0,
            trade_id="trade-bad-deadline",
            symbol="BTCUSDT",
            side="BUY",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            schema_version=2,
            tp_price=104.0,
            sl_price=98.0,
            timeout_at=timeout_at,
            recovery_eligible_until=recovery_until,
        )


def test_r2_v1_cannot_smuggle_replay_terms():
    with pytest.raises(ValueError, match="schema_version=1"):
        make_position_opened_event(
            event_id="ev-v1-bad",
            paper_epoch_id=EPOCH_V1,
            sequence=2,
            timestamp=10.0,
            trade_id="trade-v1-bad",
            symbol="BTCUSDT",
            side="BUY",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            schema_version=1,
            tp_price=104.0,
            sl_price=98.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        )


def test_r2_store_roundtrips_schema_v2_without_reconstruction(tmp_path):
    store = DurableEventStore(tmp_path / "ppl")
    expected = (epoch_v2(), open_v2(), close_v2())
    for event in expected:
        store.append(EPOCH_V2, event)

    assert store.load_epoch(EPOCH_V2) == expected


def test_r2_projected_v2_open_contains_exact_restart_terms():
    state = project([epoch_v2(), open_v2()])
    position = state.open_positions["trade-v2"]

    assert position.opened_at == 10.0
    assert position.tp_price == 104.0
    assert position.sl_price == 98.0
    assert position.timeout_at == 20.0
    assert position.recovery_eligible_until == 30.0
    assert position.replay_complete is True


def test_r2_v1_history_remains_readable_but_not_replay_complete():
    state = project([epoch_v1(), open_v1()])
    position = state.open_positions["trade-v1"]

    assert position.opened_at == 10.0
    assert position.tp_price is None
    assert position.sl_price is None
    assert position.timeout_at is None
    assert position.recovery_eligible_until is None
    assert position.replay_complete is False


def test_r2_mixed_schema_inside_one_epoch_fails_closed():
    mixed_open = make_position_opened_event(
        event_id="ev-mixed-open",
        paper_epoch_id=EPOCH_V2,
        sequence=2,
        timestamp=10.0,
        trade_id="trade-mixed",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        schema_version=1,
    )

    with pytest.raises(IllegalTransitionError, match="mixed schema versions"):
        project([epoch_v2(), mixed_open])


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (15.0, RestartDisposition.RESTORE_MONITORING),
        (20.0, RestartDisposition.RESTORE_TIMEOUT_DUE),
        (30.0, RestartDisposition.RESTORE_TIMEOUT_DUE),
        (30.0001, RestartDisposition.UNRESOLVED_REQUIRED),
    ],
)
def test_r2_restart_plan_is_deterministic_from_durable_deadlines(now, expected):
    state = project([epoch_v2(), open_v2()])
    plan = plan_restart_recovery(state, now=now)

    assert plan.paper_epoch_id == EPOCH_V2
    assert len(plan.positions) == 1
    assert plan.positions[0].trade_id == "trade-v2"
    assert plan.positions[0].disposition is expected


def test_r2_restart_plan_refuses_historical_v1_open():
    state = project([epoch_v1(), open_v1()])

    with pytest.raises(ReplayIncompletePositionError, match="not replay-complete"):
        plan_restart_recovery(state, now=15.0)


def test_r2_restart_plan_with_no_open_positions_is_empty():
    state = project([epoch_v2()])
    plan = plan_restart_recovery(state, now=100.0)

    assert plan.paper_epoch_id == EPOCH_V2
    assert plan.positions == ()
