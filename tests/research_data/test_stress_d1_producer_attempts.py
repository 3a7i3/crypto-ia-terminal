"""Synthetic D1-D V2: independent plans, retries, boundaries and unknowns."""
from copy import deepcopy

import pytest

from research_data.stress_d1_evidence_contract import EvidenceIntegrityError
from research_data.stress_d1_producer_attempts import reconcile_producer_attempts


BOUNDARY = {
    "paper_epoch_id": "SYNTHETIC-EPOCH", "code_sha": "a" * 40,
    "config_sha256": "b" * 64, "dataset_id": "synthetic-dataset",
    "source_boundary_id": "synthetic-boundary", "window_start": "2026-10-10T00:00:00Z",
    "window_end": "2026-10-11T00:00:00Z", "capture_cutoff": "2026-10-11T00:01:00Z",
}


def inputs():
    roster = [{"boundary": deepcopy(BOUNDARY), "roster_id": "r1", "cycle_id": "c1",
               "symbol": "BTC", "selected_for_analysis": True,
               "selected_at": "2026-10-10T23:59:59Z", "attempt_ids": ["a1", "a2"]}]
    receipts = [{"boundary": deepcopy(BOUNDARY), "roster_id": "r1", "cycle_id": "c1",
                 "symbol": "BTC", "attempt_id": a, "outcome": outcome,
                 "packet_id": packet, "started_at": "2026-10-10T23:59:59Z",
                 "ended_at": end} for a, outcome, packet, end in
                [("a1", "RETURN_NO_PACKET", None, "2026-10-10T23:59:59Z"),
                 ("a2", "RETURN_WITH_PACKET", "p2", "2026-10-11T00:00:00Z")]]
    packets = [{"boundary": deepcopy(BOUNDARY), "roster_id": "r1", "cycle_id": "c1",
                "symbol": "BTC", "attempt_id": "a2", "packet_id": "p2"}]
    return roster, receipts, packets


def run(data):
    return reconcile_producer_attempts(*data, boundary=BOUNDARY)


def test_reanalysis_is_not_collapsed_and_midnight_is_retained():
    result = run(inputs())
    assert result["roster_entries"] == 1
    assert result["planned_attempts"] == 2
    assert result["counts"]["PROVEN_RETURN_NO_PACKET"] == 1
    assert result["counts"]["PACKET_CAPTURED"] == 1
    assert sum(result["counts"].values()) == 2
    assert result["late_terminal_receipts"] == 1
    assert result["producer_completeness"] == "NOT_PROVEN"
    assert result["native_epoch_binding"] == "NOT_PROVEN"
    assert result["paper_stress_runtime_go"] == "DENIED"


def test_selected_without_plan_is_unknown_not_zero_calls():
    roster, _, _ = inputs()
    roster[0]["attempt_ids"] = []
    result = run((roster, [], []))
    assert result["selected_without_native_attempt_plan"] == 1
    assert result["unresolved_evidence_count"] == 1


def test_missing_receipt_and_packet_gap_are_not_lost_writes():
    roster, receipts, packets = inputs()
    result = run((roster, receipts[:1], packets))
    assert result["counts"]["MISSING_INVOCATION_RECEIPT"] == 1
    assert result["packet_without_unambiguous_return_receipt"] == 1
    assert result["unresolved_evidence_count"] == 2
    result = run((roster, receipts, []))
    assert result["counts"]["RETURNED_PACKET_NOT_CAPTURED"] == 1


@pytest.mark.parametrize("outcome,category", [
    ("RETURN_NO_PACKET", "PROVEN_RETURN_NO_PACKET"),
    ("RAISED_BEFORE_PACKET", "PROVEN_EXCEPTION_BEFORE_PACKET"),
    ("RAISED_PACKET_STATE_UNKNOWN", "EXCEPTION_PACKET_STATE_UNKNOWN"),
    ("UNKNOWN", "UNKNOWN_INVOCATION_OUTCOME"),
])
def test_terminal_outcomes_are_exclusive(outcome, category):
    roster, receipts, _ = inputs()
    receipts[1].update(outcome=outcome, packet_id=None)
    result = run((roster, receipts, []))
    assert result["counts"][category] >= 1
    assert sum(result["counts"].values()) == result["planned_attempts"]


@pytest.mark.parametrize("stream,index,field,value,reason", [
    (0, 0, "attempt_ids", ["a1", "a1"], "DUPLICATE_PLANNED_ATTEMPT"),
    (0, 0, "attempt_ids", None, "NATIVE_ATTEMPT_PLAN_NOT_AVAILABLE"),
    (0, 0, "selected_for_analysis", 1, "MISSING_NATIVE_SELECTION"),
    (0, 0, "selected_for_analysis", False, "NOT_SELECTED_HAS_ATTEMPTS"),
    (0, 0, "selected_at", "2026-10-11T00:00:00Z", "ROSTER_OUTSIDE_WINDOW"),
    (0, 0, "selected_at", "2026-10-10T23:59:59", "NAIVE_OR_NON_UTC_TIME"),
    (0, 0, "roster_id", " ", "INVALID_ROSTER_ID"),
    (1, 1, "attempt_id", "a3", "ATTEMPT_OUTSIDE_DECLARED_PLAN"),
    (1, 1, "cycle_id", "other-cycle", "ATTEMPT_NATIVE_JOIN_MISMATCH"),
    (1, 1, "roster_id", "other-roster", "ATTEMPT_NATIVE_JOIN_MISMATCH"),
    (1, 1, "outcome", [], "INVALID_RECEIPT_OUTCOME"),
    (1, 1, "packet_id", None, "MISSING_RETURNED_PACKET_ID"),
    (1, 0, "packet_id", "p2", "PACKET_CONTRADICTS_RECEIPT_OUTCOME"),
    (1, 1, "ended_at", "2026-10-11T00:01:01Z", "INVALID_INVOCATION_INTERVAL"),
    (1, 1, "started_at", "2026-10-10T23:59:58Z", "INVALID_INVOCATION_INTERVAL"),
    (2, 0, "packet_id", "other-packet", "PACKET_ID_CAUSAL_JOIN_MISMATCH"),
    (2, 0, "attempt_id", "a1", "PACKET_CONTRADICTS_NO_PACKET_RECEIPT"),
])
def test_negative_native_join_and_interval(stream, index, field, value, reason):
    data = inputs()
    data[stream][index][field] = value
    with pytest.raises(EvidenceIntegrityError, match=reason):
        run(data)


@pytest.mark.parametrize("field", list(BOUNDARY))
def test_boundary_mismatch_never_promotes_historical_identity(field):
    data = inputs()
    value = data[1][0]["boundary"][field]
    data[1][0]["boundary"][field] = ("c" * len(value) if "sha" in field else
                                      "2026-10-10T00:00:01Z" if "window_start" == field else
                                      "2026-10-11T00:00:01Z" if "window_end" == field else
                                      "2026-10-11T00:01:01Z" if "capture_cutoff" == field else "other")
    with pytest.raises(EvidenceIntegrityError, match="NATIVE_BOUNDARY_MISMATCH"):
        run(data)


@pytest.mark.parametrize("stream,reason", [(0, "DUPLICATE_ROSTER_ID"),
                                         (1, "DUPLICATE_INVOCATION_RECEIPT"),
                                         (2, "DUPLICATE_CAPTURED_ATTEMPT")])
def test_duplicate_native_rows_fail_closed(stream, reason):
    data = inputs()
    data[stream].append(deepcopy(data[stream][0]))
    with pytest.raises(EvidenceIntegrityError, match=reason):
        run(data)


def test_not_selected_is_preserved_without_invented_attempt():
    roster, _, _ = inputs()
    roster[0].update(selected_for_analysis=False, attempt_ids=[])
    result = run((roster, [], []))
    assert result["not_selected"] == 1
    assert result["selected_without_native_attempt_plan"] == 0


def test_input_order_and_input_objects_are_preserved():
    data = inputs()
    before = deepcopy(data)
    assert run(data) == run(tuple(list(reversed(rows)) for rows in data))
    assert data == before
