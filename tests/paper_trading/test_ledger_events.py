"""Tests for paper_trading/ledger_events.py (PPL-02A)."""

import pytest

from paper_trading.ledger_events import (
    LedgerEvent,
    LedgerEventType,
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
    make_recovery_completed_event,
)


def test_epoch_created_event_shape():
    ev = make_epoch_created_event(
        event_id="e1",
        paper_epoch_id="pe-1",
        sequence=1,
        timestamp=1.0,
        initial_virtual_capital=100.0,
        code_sha="sha",
        config_snapshot_hash="cfg",
    )
    assert ev.event_type is LedgerEventType.EPOCH_CREATED
    assert ev.trade_id is None
    assert ev.payload["initial_virtual_capital"] == 100.0


def test_position_opened_event_requires_trade_id():
    with pytest.raises(ValueError):
        LedgerEvent(
            event_id="e2",
            paper_epoch_id="pe-1",
            sequence=2,
            event_type=LedgerEventType.POSITION_OPENED,
            timestamp=2.0,
            trade_id=None,
            decision_id=None,
            payload={},
        )


def test_epoch_created_event_must_not_carry_trade_id():
    with pytest.raises(ValueError):
        LedgerEvent(
            event_id="e1",
            paper_epoch_id="pe-1",
            sequence=1,
            event_type=LedgerEventType.EPOCH_CREATED,
            timestamp=1.0,
            trade_id="t1",
            decision_id=None,
            payload={},
        )


def test_event_id_is_distinct_field_from_trade_id():
    ev = make_position_opened_event(
        event_id="evt-abc",
        paper_epoch_id="pe-1",
        sequence=2,
        timestamp=2.0,
        trade_id="trade-xyz",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
    )
    assert ev.event_id == "evt-abc"
    assert ev.trade_id == "trade-xyz"
    assert ev.event_id != ev.trade_id


def test_position_closed_event_payload():
    ev = make_position_closed_event(
        event_id="e3",
        paper_epoch_id="pe-1",
        sequence=3,
        timestamp=3.0,
        trade_id="t1",
        exit_price=110.0,
        gross_pnl=1.0,
        exit_fee=0.01,
    )
    assert ev.payload["gross_pnl"] == 1.0
    assert ev.payload["exit_fee"] == 0.01


def test_position_unresolved_event_carries_reason_not_pnl():
    ev = make_position_unresolved_event(
        event_id="e4",
        paper_epoch_id="pe-1",
        sequence=4,
        timestamp=4.0,
        trade_id="t1",
        reason="expired_on_restore",
    )
    assert "pnl_usd" not in ev.payload
    assert "gross_pnl" not in ev.payload
    assert ev.payload["reason"] == "expired_on_restore"


def test_recovery_completed_event_has_no_trade_id():
    ev = make_recovery_completed_event(
        event_id="e5",
        paper_epoch_id="pe-1",
        sequence=5,
        timestamp=5.0,
        restored_count=2,
        unresolved_count=1,
    )
    assert ev.trade_id is None
    assert ev.payload["restored_count"] == 2


def test_sequence_must_be_positive():
    with pytest.raises(ValueError):
        make_epoch_created_event(
            event_id="e1",
            paper_epoch_id="pe-1",
            sequence=0,
            timestamp=1.0,
            initial_virtual_capital=100.0,
            code_sha="sha",
            config_snapshot_hash="cfg",
        )


def test_event_is_immutable():
    ev = make_epoch_created_event(
        event_id="e1",
        paper_epoch_id="pe-1",
        sequence=1,
        timestamp=1.0,
        initial_virtual_capital=100.0,
        code_sha="sha",
        config_snapshot_hash="cfg",
    )
    with pytest.raises(Exception):
        ev.sequence = 2  # type: ignore[misc]
