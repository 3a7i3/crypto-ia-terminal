"""Tests for paper_trading/ledger_events.py (PPL-02A, hardened PPL-02A-R1)."""

import pytest

from paper_trading.ledger_events import (
    LedgerEvent,
    LedgerEventType,
    Side,
    make_epoch_created_event,
    make_epoch_created_event_from_epoch,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
    make_recovery_completed_event,
    normalize_side,
)
from paper_trading.paper_epoch import create_paper_epoch


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
    assert "gross_pnl" not in ev.payload


def test_epoch_created_event_from_epoch_reuses_epoch_fields():
    epoch = create_paper_epoch(
        paper_epoch_id="pe-1",
        created_at=42.0,
        initial_virtual_capital=250.0,
        code_sha="sha123",
        config_snapshot_hash="cfg456",
    )
    ev = make_epoch_created_event_from_epoch(epoch, event_id="e1", sequence=1)
    assert ev.paper_epoch_id == "pe-1"
    assert ev.timestamp == 42.0
    assert ev.payload["initial_virtual_capital"] == 250.0
    assert ev.payload["code_sha"] == "sha123"
    assert ev.payload["config_snapshot_hash"] == "cfg456"


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


def test_event_id_equal_to_trade_id_is_rejected():
    """MASTER finding R1-B: event_id != trade_id is an ENFORCED invariant,
    not merely something two different literals happen to satisfy."""
    with pytest.raises(ValueError):
        make_position_opened_event(
            event_id="same-id",
            paper_epoch_id="pe-1",
            sequence=2,
            timestamp=2.0,
            trade_id="same-id",
            symbol="BTCUSDT",
            side="BUY",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
        )


def test_event_id_equal_to_trade_id_is_rejected_for_closed_event():
    with pytest.raises(ValueError):
        make_position_closed_event(
            event_id="dup-id",
            paper_epoch_id="pe-1",
            sequence=3,
            timestamp=3.0,
            trade_id="dup-id",
            exit_price=110.0,
            exit_fee=0.01,
        )


def test_event_id_equal_to_trade_id_is_rejected_for_unresolved_event():
    with pytest.raises(ValueError):
        make_position_unresolved_event(
            event_id="dup-id",
            paper_epoch_id="pe-1",
            sequence=3,
            timestamp=3.0,
            trade_id="dup-id",
            reason="expired_on_restore",
        )


def test_position_closed_event_has_no_gross_pnl_field():
    """MASTER finding R1-G: gross_pnl is not a durable POSITION_CLOSED
    fact — it is derived by the projection, never trusted from the event."""
    ev = make_position_closed_event(
        event_id="e3",
        paper_epoch_id="pe-1",
        sequence=3,
        timestamp=3.0,
        trade_id="t1",
        exit_price=110.0,
        exit_fee=0.01,
    )
    assert ev.payload["exit_price"] == 110.0
    assert ev.payload["exit_fee"] == 0.01
    assert "gross_pnl" not in ev.payload


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


# ── R1-C: real immutability of payload ────────────────────────────────────


def test_payload_mutation_after_construction_is_impossible():
    ev = make_position_opened_event(
        event_id="evt-1",
        paper_epoch_id="pe-1",
        sequence=1,
        timestamp=1.0,
        trade_id="t1",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
    )
    with pytest.raises(TypeError):
        ev.payload["principal"] = 9999.0  # type: ignore[index]


def test_caller_input_dict_mutation_does_not_affect_event():
    payload_source = {"reason": "expired_on_restore"}
    ev = make_position_unresolved_event(
        event_id="evt-2",
        paper_epoch_id="pe-1",
        sequence=1,
        timestamp=1.0,
        trade_id="t1",
        reason=payload_source["reason"],
    )
    payload_source["reason"] = "tampered"
    assert ev.payload["reason"] == "expired_on_restore"


# ── R1-D: non-finite timestamp rejected ────────────────────────────────────


@pytest.mark.parametrize("bad_ts", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_timestamp_rejected(bad_ts):
    with pytest.raises(ValueError):
        make_epoch_created_event(
            event_id="e1",
            paper_epoch_id="pe-1",
            sequence=1,
            timestamp=bad_ts,
            initial_virtual_capital=100.0,
            code_sha="sha",
            config_snapshot_hash="cfg",
        )


# ── R1-E: side is a closed domain ─────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [("LONG", Side.LONG), ("BUY", Side.LONG), ("buy", Side.LONG),
     ("SHORT", Side.SHORT), ("SELL", Side.SHORT), ("sell", Side.SHORT)],
)
def test_normalize_side_accepts_canonical_and_aliases(raw, expected):
    assert normalize_side(raw) is expected


def test_normalize_side_rejects_unknown_string():
    with pytest.raises(ValueError):
        normalize_side("BANANA")


def test_position_opened_event_rejects_invalid_side():
    with pytest.raises(ValueError):
        make_position_opened_event(
            event_id="evt-1",
            paper_epoch_id="pe-1",
            sequence=1,
            timestamp=1.0,
            trade_id="t1",
            symbol="BTCUSDT",
            side="BANANA",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
        )


def test_position_opened_event_stores_canonical_side_value():
    ev = make_position_opened_event(
        event_id="evt-1",
        paper_epoch_id="pe-1",
        sequence=1,
        timestamp=1.0,
        trade_id="t1",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
    )
    assert ev.payload["side"] == "LONG"
