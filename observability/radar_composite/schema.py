"""Closed validation of MarketLastTradeComposite and MarketVenueCoverage v1.0.0.

Validation never recomputes prices; it checks shape and internal consistency.
"""
from __future__ import annotations

from .composite import REASONS as _REASONS
from .coverage import CATEGORIES
from .instruments import EVIDENCE_KINDS

TOP = {
    "schema_version", "product", "authority", "execution_authority",
    "evidence_kind", "price_kind", "spread_semantics", "method",
    "instrument_id", "instrument", "bindings", "reference_venue", "coverage",
    "parameters", "window", "input_sha256", "counts", "series",
    "exclusions_by_venue", "pair_exclusions", "points",
}
POINT = {
    "instant_ms", "status", "composite_price", "contributors", "spread_abs",
    "spread_bps", "inter_source_skew_ms", "pair_reason", "sources",
}
SOURCE = {
    "state", "reason", "price", "trade_ms", "first_received_ms",
    "trade_age_ms", "receipt_lag_ms", "provider", "trade_id", "last_poll_status",
}
REASONS = set(_REASONS)
PAIR_REASONS = {None, "EVENTS_NOT_SYNCHRONIZED", "SOURCE_EXCLUDED"}


def validate_composite(doc) -> bool:
    try:
        return _composite(doc)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def _composite(doc):
    if not isinstance(doc, dict) or set(doc) != TOP:
        return False
    if (doc["schema_version"], doc["product"], doc["authority"], doc["price_kind"]) != (
        "1.0.0", "MarketLastTradeComposite", "OBSERVATIONAL_TELEMETRY", "LAST_TRADE"
    ):
        return False
    if doc["execution_authority"] is not False or doc["evidence_kind"] not in EVIDENCE_KINDS:
        return False
    if doc["spread_semantics"] != "LAST_TRADE_DIFFERENCE_NOT_EXECUTABLE":
        return False
    venues = doc["coverage"]["venues"]
    if venues[0] != doc["reference_venue"] or len(set(venues)) != len(venues):
        return False
    if [b["venue"] for b in doc["bindings"]] != venues:
        return False
    if any(b["instrument_id"] != doc["instrument_id"] for b in doc["bindings"]):
        return False
    two = len(venues) == 2
    if doc["coverage"]["kind"] != ("TWO_VENUES" if two else "SINGLE_VENUE"):
        return False
    window = doc["window"]
    points = doc["points"]
    if len(points) != window["expected_points"]:
        return False
    expected_instants = list(range(window["start_ms"], window["end_exclusive_ms"], window["step_ms"]))
    if [p["instant_ms"] for p in points] != expected_instants:
        return False
    composite_count, single = 0, {v: 0 for v in venues}
    for point in points:
        if set(point) != POINT or set(point["sources"]) != set(venues):
            return False
        for venue, src in point["sources"].items():
            if set(src) != SOURCE:
                return False
            if src["state"] == "ELIGIBLE":
                if src["reason"] is not None or src["price"] is None:
                    return False
                single[venue] += 1
            elif src["state"] != "EXCLUDED" or src["reason"] not in REASONS:
                return False
        has = point["composite_price"] is not None
        if has != (point["status"] == "COMPOSITE"):
            return False
        if has != (point["spread_bps"] is not None) or has != (point["spread_abs"] is not None):
            return False
        if has and (not two or point["contributors"] != venues or point["pair_reason"] is not None):
            return False
        if not has and point["contributors"]:
            return False
        if point["pair_reason"] not in PAIR_REASONS or (not two and point["pair_reason"] is not None):
            return False
        eligible = sum(s["state"] == "ELIGIBLE" for s in point["sources"].values())
        if not has and point["status"] != ("SINGLE_VENUE_ONLY" if eligible else "NO_ELIGIBLE_SOURCE"):
            return False
        composite_count += has
    comp = doc["series"]["composite"]
    expected = window["expected_points"]
    if comp["series_kind"] != "COMPOSITE" or comp["valid_points"] != composite_count:
        return False
    if two:
        if comp["status"] != ("COMPLETE" if composite_count == expected else "INCOMPLETE"):
            return False
    elif comp["status"] != "NOT_APPLICABLE_SINGLE_VENUE_COVERAGE":
        return False
    if (comp["ohlc"] is not None) != (comp["status"] == "COMPLETE"):
        return False
    labels = {comp["label"]}
    for venue in venues:
        s = doc["series"]["single_venue"][venue]
        if s["series_kind"] != "SINGLE_VENUE" or s["venue"] != venue or s["valid_points"] != single[venue]:
            return False
        if s["status"] != ("COMPLETE" if single[venue] == expected else "INCOMPLETE"):
            return False
        if (s["ohlc"] is not None) != (s["status"] == "COMPLETE"):
            return False
        labels.add(s["label"])
    return len(labels) == len(venues) + 1 and set(doc["series"]["single_venue"]) == set(venues)


def validate_coverage(doc) -> bool:
    try:
        if doc["product"] != "MarketVenueCoverage" or doc["schema_version"] != "1.0.0":
            return False
        if doc["execution_authority"] is not False:
            return False
        rows = doc["rows"]
        symbols = [r["native_symbol"] for r in rows]
        if len(set(symbols)) != len(symbols) or len(rows) != doc["selection"]["count"]:
            return False
        if set(doc["totals"]) != set(CATEGORIES) or sum(doc["totals"].values()) != len(rows):
            return False
        for category in CATEGORIES:
            if doc["totals"][category] != sum(r["coverage"] == category for r in rows):
                return False
        for row in rows:
            if row["coverage"] not in CATEGORIES:
                return False
            if bool(row["bindings"]) != (row["coverage"] == "EXACT_COMMON_PAIR"):
                return False
            if (row["reason"] is None) != (row["coverage"] == "EXACT_COMMON_PAIR"):
                return False
        return True
    except (KeyError, TypeError, AttributeError):
        return False
