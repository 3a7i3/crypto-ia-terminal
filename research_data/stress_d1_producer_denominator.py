"""D1-D source-only population accounting over EXPLICIT, untrusted Research attestations.

Does not access disk, production, network or runtime; no production completeness
certification is available from this pure function. NOT a replay or GO gate.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

VERSION = "D1_D_V1"
RECEIPT_OUTCOMES = frozenset({
    "RETURN_WITH_PACKET", "RETURN_NO_PACKET", "RAISED_BEFORE_PACKET",
    "RAISED_PACKET_STATE_UNKNOWN", "UNKNOWN",
})


class DenominatorIntegrityError(ValueError):
    """Input malformed or contradictory; never silently repair."""


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise DenominatorIntegrityError(code)


def _key(row: Mapping[str, Any]) -> tuple[str, str]:
    cycle = row.get("cycle_id")
    symbol = row.get("symbol")
    _need(isinstance(cycle, str) and bool(cycle) and
          isinstance(symbol, str) and bool(symbol), "INVALID_NATIVE_ROSTER_KEY")
    return (cycle, symbol)


def _rows(raw: Any, kind: str) -> list[Mapping[str, Any]]:
    _need(isinstance(raw, (list, tuple)), f"INVALID_{kind}_COLLECTION")
    _need(all(isinstance(item, Mapping) for item in raw), f"INVALID_{kind}_ROW")
    return list(raw)


def reconcile_producer_roster(
    scheduled: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
    captured_packets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reconcile a caller-asserted cycle-symbol roster, invocation receipts and packets.

    Three sources must originate in the SAME externally proven Research boundary;
    this function neither checks nor asserts that property. Missing receipts and
    missing packet bytes remain UNKNOWN, not synthesized as absent decisions.
    Duplicates, contradictory joins or extra rows fail the whole reconciliation.
    """
    scheduled_rows = _rows(scheduled, "ROSTER")
    receipt_rows = _rows(receipts, "RECEIPTS")
    packet_rows = _rows(captured_packets, "PACKETS")
    _need(bool(scheduled_rows), "ROSTER_NOT_AVAILABLE")

    roster: dict[tuple[str, str], bool] = {}
    for row in scheduled_rows:
        key = _key(row)
        _need(key not in roster, "DUPLICATE_ROSTER_KEY")
        selected = row.get("selected_for_analysis")
        _need(type(selected) is bool, "MISSING_NATIVE_SELECTION_RECEIPT")
        roster[key] = selected

    by_call: dict[tuple[str, str], Mapping[str, Any]] = {}
    packet_ids: set[str] = set()
    for row in receipt_rows:
        key = _key(row)
        _need(key in roster, "ORPHAN_INVOCATION_RECEIPT")
        _need(roster[key], "INVOCATION_OF_NOT_SELECTED_SYMBOL")
        _need(key not in by_call, "DUPLICATE_INVOCATION_RECEIPT")
        outcome = row.get("outcome")
        _need(isinstance(outcome, str) and outcome in RECEIPT_OUTCOMES,
              "INVALID_RECEIPT_OUTCOME")
        packet_id = row.get("packet_id")
        if outcome == "RETURN_WITH_PACKET":
            _need(isinstance(packet_id, str) and bool(packet_id), "MISSING_PACKET_ID_ON_RETURN")
            _need(packet_id not in packet_ids, "DUPLICATE_RETURNED_PACKET_ID")
            packet_ids.add(packet_id)
        else:
            _need(packet_id is None, "PACKET_ID_CONTRADICTS_RECEIPT_OUTCOME")
        by_call[key] = row

    packets_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    packet_id_seen: set[str] = set()
    for row in packet_rows:
        key = _key(row)
        _need(key in roster and roster[key], "PACKET_OUTSIDE_SELECTED_UNIVERSE")
        _need(key not in packets_by_key, "DUPLICATE_CAPTURED_PACKET_KEY")
        p = row.get("packet_id")
        _need(isinstance(p, str) and bool(p), "CAPTURED_PACKET_ID_INVALID")
        _need(p not in packet_id_seen, "DUPLICATE_CAPTURED_PACKET_ID")
        packets_by_key[key] = row
        packet_id_seen.add(p)
        observed = by_call.get(key)
        if observed is not None and observed.get("outcome") == "RETURN_WITH_PACKET":
            _need(observed["packet_id"] == p, "PACKET_ID_CAUSAL_JOIN_MISMATCH")
        elif observed is not None and observed.get("outcome") in (
            "RETURN_NO_PACKET", "RAISED_BEFORE_PACKET"
        ):
            raise DenominatorIntegrityError("PACKET_CONTRADICTS_NO_PACKET_RECEIPT")

    breakdown: Counter[str] = Counter()
    for key, selected in roster.items():
        if not selected:
            breakdown["NOT_SELECTED"] += 1
            continue
        receipt = by_call.get(key)
        packet = packets_by_key.get(key)
        if receipt is None:
            breakdown["MISSING_INVOCATION_RECEIPT"] += 1
        elif receipt["outcome"] == "RETURN_WITH_PACKET":
            breakdown["PACKET_CAPTURED" if packet else "RETURNED_PACKET_NOT_CAPTURED"] += 1
        elif receipt["outcome"] == "RETURN_NO_PACKET":
            breakdown["PROVEN_RETURN_NO_PACKET"] += 1
        elif receipt["outcome"] == "RAISED_BEFORE_PACKET":
            breakdown["PROVEN_EXCEPTION_BEFORE_PACKET"] += 1
        elif receipt["outcome"] == "RAISED_PACKET_STATE_UNKNOWN":
            breakdown["EXCEPTION_PACKET_STATE_UNKNOWN"] += 1
        else:
            breakdown["UNKNOWN_INVOCATION_OUTCOME"] += 1

    # Unmatched packet bytes can be an input-capture mismatch and remain unresolved.
    orphan_to_receipt = sum(1 for key in packets_by_key if
                            key not in by_call or by_call[key]["outcome"] in
                            ("RAISED_PACKET_STATE_UNKNOWN", "UNKNOWN"))
    unknown = sum(breakdown[k] for k in (
        "MISSING_INVOCATION_RECEIPT", "RETURNED_PACKET_NOT_CAPTURED",
        "EXCEPTION_PACKET_STATE_UNKNOWN", "UNKNOWN_INVOCATION_OUTCOME",
    )) + orphan_to_receipt
    output = {k: breakdown.get(k, 0) for k in (
        "NOT_SELECTED", "MISSING_INVOCATION_RECEIPT", "PACKET_CAPTURED",
        "RETURNED_PACKET_NOT_CAPTURED", "PROVEN_RETURN_NO_PACKET",
        "PROVEN_EXCEPTION_BEFORE_PACKET", "EXCEPTION_PACKET_STATE_UNKNOWN",
        "UNKNOWN_INVOCATION_OUTCOME",
    )}
    _need(sum(output.values()) == len(roster), "ROSTER_ACCOUNTING_FAILURE")
    return {
        "version": VERSION,
        "status": "DECLARED_ROSTER_ACCOUNTED_NOT_PRODUCER_CERTIFIED",
        "counts": output,
        "roster_entries": len(roster),
        "selected_for_analysis": sum(roster.values()),
        "invocation_receipts": len(by_call),
        "captured_packets": len(packets_by_key),
        "packet_without_unambiguous_return_receipt": orphan_to_receipt,
        "unresolved_evidence_count": unknown,
        "producer_completeness": "NOT_PROVEN",
        "clock_certified": False,
        "epoch_binding": "NOT_PROVEN",
        "persist_receipts": "NOT_OBSERVED",
        "counterfactual_performance_eligibility": "NOT_PROVEN",
        "paper_stress_runtime_go": "DENIED",
    }
