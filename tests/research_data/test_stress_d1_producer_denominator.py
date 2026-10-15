"""Synthetic only: D1-D source-only producer denominator tests."""
import pytest

from research_data.stress_d1_producer_denominator import (
    DenominatorIntegrityError,
    reconcile_producer_roster,
)


def rr(symbol, selected=True, cycle="c1"):
    return {"cycle_id": cycle, "symbol": symbol, "selected_for_analysis": selected}


def rc(symbol, outcome="RETURN_NO_PACKET", packet_id=None, cycle="c1"):
    return {"cycle_id": cycle, "symbol": symbol, "outcome": outcome, "packet_id": packet_id}


def pk(symbol, packet_id, cycle="c1"):
    return {"cycle_id": cycle, "symbol": symbol, "packet_id": packet_id}


def test_synthetic_ledger_preserves_no_packet_and_all_units():
    roster = [rr("BTC"), rr("ETH"), rr("DOGE"), rr("SOL", False), rr("ADA"), rr("XRP")]
    receipts = [rc("BTC", "RETURN_WITH_PACKET", "p1"), rc("ETH"),
                rc("DOGE", "RAISED_BEFORE_PACKET"),
                rc("ADA", "RAISED_PACKET_STATE_UNKNOWN")]
    out = reconcile_producer_roster(roster, receipts, [pk("BTC", "p1")])
    assert out["counts"] == {
        "NOT_SELECTED": 1, "MISSING_INVOCATION_RECEIPT": 1,
        "PACKET_CAPTURED": 1, "RETURNED_PACKET_NOT_CAPTURED": 0,
        "PROVEN_RETURN_NO_PACKET": 1, "PROVEN_EXCEPTION_BEFORE_PACKET": 1,
        "EXCEPTION_PACKET_STATE_UNKNOWN": 1, "UNKNOWN_INVOCATION_OUTCOME": 0}
    assert out["selected_for_analysis"] == 5
    assert out["unresolved_evidence_count"] == 2
    assert out["producer_completeness"] == "NOT_PROVEN"
    assert out["paper_stress_runtime_go"] == "DENIED"


def test_empty_roster_never_establishes_zero_population():
    with pytest.raises(DenominatorIntegrityError, match="ROSTER_NOT_AVAILABLE"):
        reconcile_producer_roster([], [], [])


@pytest.mark.parametrize("scheduled,receipts,packets,reason", [
    ([rr("BTC"), rr("BTC")], [], [], "DUPLICATE_ROSTER_KEY"),
    ([{"cycle_id": "c1", "symbol": "BTC"}], [], [], "MISSING_NATIVE_SELECTION_RECEIPT"),
    ([rr("BTC", False)], [rc("BTC")], [], "INVOCATION_OF_NOT_SELECTED_SYMBOL"),
    ([rr("BTC")], [rc("ETH")], [], "ORPHAN_INVOCATION_RECEIPT"),
    ([rr("BTC")], [rc("BTC"), rc("BTC")], [], "DUPLICATE_INVOCATION_RECEIPT"),
    ([rr("BTC")], [rc("BTC", "RETURN_WITH_PACKET")], [], "MISSING_PACKET_ID_ON_RETURN"),
    ([rr("BTC")], [rc("BTC", "RETURN_WITH_PACKET", "p1")], [pk("BTC", "p2")],
     "PACKET_ID_CAUSAL_JOIN_MISMATCH"),
    ([rr("BTC")], [rc("BTC")], [pk("BTC", "p1")], "PACKET_CONTRADICTS_NO_PACKET_RECEIPT"),
    ([rr("BTC")], [rc("BTC", "RAISED_BEFORE_PACKET")], [pk("BTC", "p1")],
     "PACKET_CONTRADICTS_NO_PACKET_RECEIPT"),
    ([rr("BTC")], [rc("BTC", "UNKNOWN", "p1")], [], "PACKET_ID_CONTRADICTS_RECEIPT_OUTCOME"),
    ([rr("BTC")], [rc("BTC", "RETURN_WITH_PACKET", "p1")],
     [pk("BTC", "p1"), pk("BTC", "p1")], "DUPLICATE_CAPTURED_PACKET_KEY"),
    ([rr("BTC")], [], [pk("ETH", "p1")], "PACKET_OUTSIDE_SELECTED_UNIVERSE"),
    ([rr("BTC")], [rc("BTC", "WRONG")], [], "INVALID_RECEIPT_OUTCOME"),
])
def test_fail_closed_on_contradiction(scheduled, receipts, packets, reason):
    with pytest.raises(DenominatorIntegrityError, match=reason):
        reconcile_producer_roster(scheduled, receipts, packets)


def test_unknown_is_never_converted_to_no_packet():
    out = reconcile_producer_roster([rr("BTC")], [], [])
    assert out["counts"]["MISSING_INVOCATION_RECEIPT"] == 1
    assert out["counts"]["PROVEN_RETURN_NO_PACKET"] == 0
    assert out["unresolved_evidence_count"] == 1


def test_returned_packet_missing_is_not_proven_lost_write():
    out = reconcile_producer_roster([rr("BTC")], [rc("BTC", "RETURN_WITH_PACKET", "p1")], [])
    assert out["counts"]["RETURNED_PACKET_NOT_CAPTURED"] == 1
    assert out["producer_completeness"] == "NOT_PROVEN"


def test_packet_without_receipt_is_explicit():
    out = reconcile_producer_roster([rr("BTC")], [], [pk("BTC", "p1")])
    assert out["packet_without_unambiguous_return_receipt"] == 1
    assert out["counts"]["MISSING_INVOCATION_RECEIPT"] == 1
    assert out["unresolved_evidence_count"] == 2


def test_deterministic_reordering():
    scheduled = [rr("BTC"), rr("ETH"), rr("SOL", False)]
    receipts = [rc("BTC", "RETURN_WITH_PACKET", "p1"), rc("ETH", "RETURN_NO_PACKET")]
    packets = [pk("BTC", "p1")]
    assert reconcile_producer_roster(scheduled, receipts, packets) == reconcile_producer_roster(
        scheduled[::-1], receipts[::-1], packets[::-1])
