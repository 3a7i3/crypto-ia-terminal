"""D1-D V2 native roster/attempt accounting; no production imports, IO or authority."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from research_data.stress_d1_evidence_contract import (
    bound_rows,
    native_id,
    require,
    utc_time,
    validate_boundary,
)

OUTCOMES = frozenset({"RETURN_WITH_PACKET", "RETURN_NO_PACKET", "RAISED_BEFORE_PACKET",
                      "RAISED_PACKET_STATE_UNKNOWN", "UNKNOWN"})
CATEGORIES = ("MISSING_INVOCATION_RECEIPT", "PACKET_CAPTURED", "RETURNED_PACKET_NOT_CAPTURED",
              "PROVEN_RETURN_NO_PACKET", "PROVEN_EXCEPTION_BEFORE_PACKET",
              "EXCEPTION_PACKET_STATE_UNKNOWN", "UNKNOWN_INVOCATION_OUTCOME")


def reconcile_producer_attempts(
    scheduled: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
    captured_packets: Sequence[Mapping[str, Any]],
    *,
    boundary: Mapping[str, str],
) -> dict[str, Any]:
    """Account for an independently supplied roster with zero or many native attempts.

    Each selected roster row supplies its native planned ``attempt_ids``. An empty
    plan is unresolved, not zero calls. Never derive a plan from captured packets.
    Matching declarations do not attest native origin, custody or completeness.
    """
    declared = validate_boundary(boundary)
    roster_rows = bound_rows(scheduled, declared)
    require(bool(roster_rows), "ROSTER_NOT_AVAILABLE")
    roster: dict[str, Mapping[str, Any]] = {}
    planned: dict[str, Mapping[str, Any]] = {}
    for row in roster_rows:
        roster_id = native_id(row.get("roster_id"), "INVALID_ROSTER_ID")
        require(roster_id not in roster, "DUPLICATE_ROSTER_ID")
        for field in ("cycle_id", "symbol"):
            native_id(row.get(field), "INVALID_NATIVE_ROSTER_KEY")
        require(type(row.get("selected_for_analysis")) is bool, "MISSING_NATIVE_SELECTION")
        selected_at = utc_time(row.get("selected_at"))
        require(utc_time(declared["window_start"]) <= selected_at <
                utc_time(declared["window_end"]), "ROSTER_OUTSIDE_WINDOW")
        attempts = row.get("attempt_ids")
        require(isinstance(attempts, (list, tuple)), "NATIVE_ATTEMPT_PLAN_NOT_AVAILABLE")
        require(row["selected_for_analysis"] or not attempts, "NOT_SELECTED_HAS_ATTEMPTS")
        for attempt in attempts:
            native_id(attempt, "INVALID_ATTEMPT_ID")
            require(attempt not in planned, "DUPLICATE_PLANNED_ATTEMPT")
            planned[attempt] = row
        roster[roster_id] = row

    def join(row: Mapping[str, Any]) -> str:
        attempt = native_id(row.get("attempt_id"), "INVALID_ATTEMPT_ID")
        require(attempt in planned, "ATTEMPT_OUTSIDE_DECLARED_PLAN")
        parent = planned[attempt]
        require(all(row.get(k) == parent[k] for k in ("roster_id", "cycle_id", "symbol")),
                "ATTEMPT_NATIVE_JOIN_MISMATCH")
        return attempt

    observed: dict[str, Mapping[str, Any]] = {}
    returned_ids: dict[str, str] = {}
    for row in bound_rows(receipts, declared):
        attempt = join(row)
        require(attempt not in observed, "DUPLICATE_INVOCATION_RECEIPT")
        outcome = row.get("outcome")
        require(isinstance(outcome, str) and outcome in OUTCOMES, "INVALID_RECEIPT_OUTCOME")
        start, end = utc_time(row.get("started_at")), utc_time(row.get("ended_at"))
        require(utc_time(planned[attempt]["selected_at"]) <= start <= end <=
                utc_time(declared["capture_cutoff"]), "INVALID_INVOCATION_INTERVAL")
        packet = row.get("packet_id")
        if outcome == "RETURN_WITH_PACKET":
            native_id(packet, "MISSING_RETURNED_PACKET_ID")
            require(packet not in returned_ids, "DUPLICATE_RETURNED_PACKET_ID")
            returned_ids[packet] = attempt
        else:
            require(packet is None, "PACKET_CONTRADICTS_RECEIPT_OUTCOME")
        observed[attempt] = row

    packets: dict[str, Mapping[str, Any]] = {}
    packet_ids: set[str] = set()
    for row in bound_rows(captured_packets, declared):
        attempt = join(row)
        require(attempt not in packets, "DUPLICATE_CAPTURED_ATTEMPT")
        packet = native_id(row.get("packet_id"), "INVALID_CAPTURED_PACKET_ID")
        require(packet not in packet_ids, "DUPLICATE_CAPTURED_PACKET_ID")
        packet_ids.add(packet)
        receipt = observed.get(attempt)
        if receipt is not None:
            require(receipt["outcome"] not in {"RETURN_NO_PACKET", "RAISED_BEFORE_PACKET"},
                    "PACKET_CONTRADICTS_NO_PACKET_RECEIPT")
            if receipt["outcome"] == "RETURN_WITH_PACKET":
                require(receipt["packet_id"] == packet, "PACKET_ID_CAUSAL_JOIN_MISMATCH")
        # Also reject a packet ID attributed to a different invocation.
        require(packet not in returned_ids or returned_ids[packet] == attempt,
                "CROSS_ATTEMPT_PACKET_ALIAS")
        packets[attempt] = row

    counts: Counter[str] = Counter()
    details = []
    for attempt in sorted(planned):
        receipt = observed.get(attempt)
        if receipt is None:
            category = "MISSING_INVOCATION_RECEIPT"
        else:
            category = {
                "RETURN_WITH_PACKET": ("PACKET_CAPTURED" if attempt in packets else
                                       "RETURNED_PACKET_NOT_CAPTURED"),
                "RETURN_NO_PACKET": "PROVEN_RETURN_NO_PACKET",
                "RAISED_BEFORE_PACKET": "PROVEN_EXCEPTION_BEFORE_PACKET",
                "RAISED_PACKET_STATE_UNKNOWN": "EXCEPTION_PACKET_STATE_UNKNOWN",
                "UNKNOWN": "UNKNOWN_INVOCATION_OUTCOME",
            }[receipt["outcome"]]
        counts[category] += 1
        details.append({"attempt_id": attempt, "category": category})
    missing_plan = sum(r["selected_for_analysis"] and not r["attempt_ids"]
                       for r in roster.values())
    ambiguous = sum(a not in observed or observed[a]["outcome"] in
                    {"UNKNOWN", "RAISED_PACKET_STATE_UNKNOWN"} for a in packets)
    require(sum(counts.values()) == len(planned), "ATTEMPT_ACCOUNTING_FAILURE")
    return {
        "version": "D1_D_V2", "status": "DECLARED_ATTEMPTS_ACCOUNTED_NOT_CERTIFIED",
        "boundary": declared, "roster_entries": len(roster),
        "not_selected": sum(not r["selected_for_analysis"] for r in roster.values()),
        "selected_roster_entries": sum(r["selected_for_analysis"] for r in roster.values()),
        "selected_without_native_attempt_plan": missing_plan,
        "planned_attempts": len(planned), "invocation_receipts": len(observed),
        "captured_packets": len(packets), "counts": {k: counts[k] for k in CATEGORIES},
        "attempts": details, "packet_without_unambiguous_return_receipt": ambiguous,
        "late_terminal_receipts": sum(utc_time(r["ended_at"]) >=
                                      utc_time(declared["window_end"]) for r in observed.values()),
        "unresolved_evidence_count": missing_plan + ambiguous + sum(counts[k] for k in
            ("MISSING_INVOCATION_RECEIPT", "RETURNED_PACKET_NOT_CAPTURED",
             "EXCEPTION_PACKET_STATE_UNKNOWN", "UNKNOWN_INVOCATION_OUTCOME")),
        "producer_completeness": "NOT_PROVEN", "native_epoch_binding": "NOT_PROVEN",
        "custody": "NOT_VERIFIED", "clock_certified": False,
        "counterfactual_performance_eligibility": "NOT_PROVEN",
        "paper_stress_runtime_go": "DENIED",
    }
