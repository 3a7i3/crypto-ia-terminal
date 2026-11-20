"""Closed validation of MarketLastTradeComposite and MarketVenueCoverage v1.0.0.

Validation never recomputes a price from trades; it checks shape, contract
numbers and the internal consistency of what is published (OHLC versus the
published sample points, contributors versus source states).
"""
from __future__ import annotations

import re
from decimal import Decimal

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


_POSITIVE = re.compile(r"\d{1,40}(?:\.\d{1,40})?")
_SIGNED = re.compile(r"-?\d{1,40}(?:\.\d{1,40})?")
_BPS = re.compile(r"-?\d{1,40}\.\d{8}")
OHLC = ("open", "high", "low", "close")


def _positive(value):
    """Positive decimal string as published by the contract (no exponent, NaN or sign)."""
    if not isinstance(value, str) or not _POSITIVE.fullmatch(value):
        return None
    number = Decimal(value)
    return number if number > 0 else None


def _signed(value, pattern=_SIGNED):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        return None
    return Decimal(value)


def _int(value, *, signed=False):
    return (isinstance(value, int) and not isinstance(value, bool)
            and (signed or value >= 0))


def _ohlc(candle, prices):
    """Exact keys, positive decimals, low <= open/close <= high, equal to the sampled points."""
    if not isinstance(candle, dict) or set(candle) != set(OHLC):
        return False
    values = {k: _positive(candle[k]) for k in OHLC}
    if any(v is None for v in values.values()):
        return False
    if not values["low"] <= min(values["open"], values["close"]) <= max(
        values["open"], values["close"]
    ) <= values["high"]:
        return False
    sampled = [Decimal(p) for p in prices]
    return (values["open"], values["high"], values["low"], values["close"]) == (
        sampled[0], max(sampled), min(sampled), sampled[-1]
    )


def _series(entry, prices, expected, *, applicable=True):
    if entry["valid_points"] != len(prices) or not _int(entry["valid_points"]):
        return False
    if not applicable:
        return entry["status"] == "NOT_APPLICABLE_SINGLE_VENUE_COVERAGE" and entry["ohlc"] is None
    if entry["status"] != ("COMPLETE" if len(prices) == expected else "INCOMPLETE"):
        return False
    if entry["status"] != "COMPLETE":
        return entry["ohlc"] is None
    return _ohlc(entry["ohlc"], prices)


def _source(src, instant, max_age):
    if set(src) != SOURCE:
        return False
    if src["price"] is not None and _positive(src["price"]) is None:
        return False
    for field in ("trade_ms", "first_received_ms"):
        if src[field] is not None and not _int(src[field]):
            return False
    for field in ("trade_age_ms", "receipt_lag_ms"):
        if src[field] is not None and not _int(src[field], signed=True):
            return False
    present = src["trade_ms"] is not None
    if any((src[f] is not None) != present for f in (
        "price", "first_received_ms", "trade_age_ms", "receipt_lag_ms", "provider"
    )):
        return False
    if present and (
        src["trade_age_ms"] != instant - src["trade_ms"]
        or src["receipt_lag_ms"] != src["first_received_ms"] - src["trade_ms"]
        or src["first_received_ms"] > instant
    ):
        return False
    if src["state"] == "ELIGIBLE":
        return src["reason"] is None and present and src["trade_age_ms"] <= max_age
    return src["state"] == "EXCLUDED" and src["reason"] in REASONS


def validate_composite(doc) -> bool:
    try:
        return _composite(doc)
    except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError):
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
    params = doc["parameters"]
    max_age = params["max_trade_age_ms"]
    max_skew = params["max_inter_source_skew_ms"]
    if set(max_age) != set(venues) or not all(_int(v) for v in max_age.values()) or not _int(max_skew):
        return False
    window = doc["window"]
    points = doc["points"]
    expected = window["expected_points"]
    if not all(_int(window[k]) for k in ("start_ms", "end_exclusive_ms", "step_ms", "expected_points")):
        return False
    if len(points) != expected or window["step_ms"] * expected != window["end_exclusive_ms"] - window["start_ms"]:
        return False
    expected_instants = list(range(window["start_ms"], window["end_exclusive_ms"], window["step_ms"]))
    if [p["instant_ms"] for p in points] != expected_instants:
        return False
    composite_prices, single = [], {v: [] for v in venues}
    for point in points:
        if set(point) != POINT or set(point["sources"]) != set(venues):
            return False
        instant = point["instant_ms"]
        for venue, src in point["sources"].items():
            if not _source(src, instant, max_age[venue]):
                return False
            if src["state"] == "ELIGIBLE":
                single[venue].append(src["price"])
        eligible = [v for v in venues if point["sources"][v]["state"] == "ELIGIBLE"]
        has = point["composite_price"] is not None
        if has != (point["status"] == "COMPOSITE"):
            return False
        if has != (point["spread_bps"] is not None) or has != (point["spread_abs"] is not None):
            return False
        if point["pair_reason"] not in PAIR_REASONS or (not two and point["pair_reason"] is not None):
            return False
        skew = point["inter_source_skew_ms"]
        if two and len(eligible) == 2:
            a, b = (point["sources"][v]["trade_ms"] for v in venues)
            if not _int(skew) or skew != abs(a - b):
                return False
        elif skew is not None:
            return False
        if has:
            # Every contributor of a composite point must be an eligible source.
            if not two or point["contributors"] != venues or eligible != venues:
                return False
            if point["pair_reason"] is not None or skew > max_skew:
                return False
            if (_positive(point["composite_price"]) is None
                    or _signed(point["spread_abs"]) is None
                    or _signed(point["spread_bps"], _BPS) is None):
                return False
            composite_prices.append(point["composite_price"])
        else:
            if point["contributors"]:
                return False
            if two and point["pair_reason"] != (
                "EVENTS_NOT_SYNCHRONIZED" if len(eligible) == 2 else "SOURCE_EXCLUDED"
            ):
                return False
            if point["status"] != ("SINGLE_VENUE_ONLY" if eligible else "NO_ELIGIBLE_SOURCE"):
                return False
    comp = doc["series"]["composite"]
    if comp["series_kind"] != "COMPOSITE" or not _series(comp, composite_prices, expected, applicable=two):
        return False
    labels = {comp["label"]}
    if set(doc["series"]["single_venue"]) != set(venues):
        return False
    for venue in venues:
        s = doc["series"]["single_venue"][venue]
        if s["series_kind"] != "SINGLE_VENUE" or s["venue"] != venue:
            return False
        if not _series(s, single[venue], expected):
            return False
        labels.add(s["label"])
    return len(labels) == len(venues) + 1


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
