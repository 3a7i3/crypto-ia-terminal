"""Closed presentation schema. Validation never computes a price, metric or verdict."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

from . import metrics
from .models import DERIVATIVE_KINDS, OI_UNITS, PRICE_KINDS, TIMESTAMP_KINDS, VENUE_ID

TOP = {"schema_version", "product", "authority", "evidence_kind", "generated_at_utc", "valid_until_utc",
       "execution_authority", "costs_funding_fx_included", "quality_policy", "parameters", "source_counts",
       "underlyings"}
UNDERLYING = {"underlying_id", "base_asset_id", "quote_asset_id", "legs", "pairs", "open_interest_total"}
LEG = {"venue", "native_symbol", "instrument_id", "instrument", "status", "reason", "observed_at_utc",
       "received_at_utc", "observer_clock_id", "timestamp_kind", "event_age_ms", "price_kind", "price",
       "index_price", "premium_to_index", "basis_vs_spot", "funding", "open_interest", "windows", "timing",
       "source"}
INSTRUMENT = {"base_asset_id", "quote_asset_id", "market_kind", "settlement_asset_id", "contract_identity"}
SOURCE = {"mapping_id", "mapping_sha256", "payload_sha256", "tape_sha256"}
PAIR = {"instrument_id", "reference_venue", "other_venue", "status", "reason", "event_skew_ms",
        "price_gap_bps", "funding_8h_difference"}
KINDS = {"SPOT", *DERIVATIVE_KINDS}
UNRESOLVED = {"UNKNOWN", "UNRESOLVED", "NOT_AVAILABLE"}
REASON = r"[A-Z][A-Z0-9_]{1,79}"
SCAN_FIELDS = ("boundary_events", "boundary_count_share", "boundary_count_lift", "boundary_volume_share",
               "boundary_volume_lift", "placebo_events", "placebo_count_share", "placebo_count_lift",
               "placebo_volume_share", "placebo_volume_lift")


def keys(value, expected):
    return isinstance(value, dict) and set(value) == set(expected)


def stamp(value):
    if not isinstance(value, str) or not value.endswith("Z") or len(value) > 40:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def text(value, pattern=r"[A-Za-z0-9@.:/_=-]{1,120}"):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def integer(value, low=0):
    return isinstance(value, int) and not isinstance(value, bool) and value >= low


def decimal(value, *, signed=False, positive=False):
    if not isinstance(value, str) or len(value) > 90 or not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return False
    try:
        d = Decimal(value)
    except InvalidOperation:
        return False
    return d.is_finite() and (signed or d >= 0) and (not positive or d > 0)


def nullable(value, check):
    return value is None or check(value)


def _fields(block, spec, keep=()):
    """Closed block: AVAILABLE or NOT_AVAILABLE(reason) with every value field valid-or-null."""
    if not keys(block, {"status", "reason", *spec}):
        return False
    if block["status"] == "AVAILABLE":
        return block["reason"] is None or text(block["reason"], REASON)
    if block["status"] != "NOT_AVAILABLE" or not text(block["reason"], REASON):
        return False
    return all(block[k] is None for k in spec if k not in keep)


def _spec_ok(block, spec):
    return all(nullable(block[k], check) for k, check in spec.items())


def _signed(v):
    return decimal(v, signed=True)


PREMIUM = {"bps": _signed}
BASIS = {"bps": _signed, "annualized_pct": _signed, "against_venue": lambda v: bool(VENUE_ID.fullmatch(v))}
FUNDING = {"rate": _signed, "interval_s": lambda v: integer(v, 60) and v <= 86_400,
           "next_funding_utc": lambda v: stamp(v) is not None, "rate_8h_equivalent": _signed,
           "annualized_simple_pct": _signed}
OI = {"value": decimal, "unit": lambda v: v in OI_UNITS, "notional_quote": decimal}
WINDOW = {"window_s": integer, "sample_gap_ms": integer, "price_change_bps": _signed,
          "price_sign": lambda v: v in ("UP", "DOWN", "FLAT"), "oi_change_pct": _signed,
          "oi_sign": lambda v: v in ("UP", "DOWN", "FLAT")}


def validate_publication(doc):
    try:
        return _validate(doc)
    except (KeyError, TypeError, ValueError, OverflowError, InvalidOperation, IndexError):
        return False


def _timing(block):
    if not keys(block, {"status", "reason", "events", "volume_base", "histogram", "scan"}):
        return False
    if block["status"] == "NOT_AVAILABLE":
        return text(block["reason"], REASON) and all(block[k] is None for k in ("events", "volume_base", "histogram", "scan"))
    if block["status"] != "AVAILABLE" or block["reason"] is not None:
        return False
    n = block["events"]
    if not integer(n, metrics.TIMING_MIN_EVENTS) or n > metrics.TIMING_MAX_EVENTS or not decimal(block["volume_base"], positive=True):
        return False
    h = block["histogram"]
    bins = metrics.HISTOGRAM_PERIOD_S * 1000 // metrics.HISTOGRAM_BIN_MS
    if not keys(h, {"period_s", "bin_ms", "counts"}) or h["period_s"] != metrics.HISTOGRAM_PERIOD_S \
            or h["bin_ms"] != metrics.HISTOGRAM_BIN_MS or not isinstance(h["counts"], list) \
            or len(h["counts"]) != bins or not all(integer(c) for c in h["counts"]) or sum(h["counts"]) != n:
        return False
    scan = block["scan"]
    if not isinstance(scan, list) or len(scan) != len(metrics.TIMING_SCAN):
        return False
    for row, (period_s, radius_ms) in zip(scan, metrics.TIMING_SCAN):
        if not keys(row, {"period_s", "radius_ms", "expected_share", *SCAN_FIELDS}):
            return False
        if row["period_s"] != period_s or row["radius_ms"] != radius_ms:
            return False
        if not decimal(row["expected_share"], positive=True) or Decimal(row["expected_share"]) > 1:
            return False
        for k in SCAN_FIELDS:
            if k.endswith("_events"):
                if not integer(row[k]) or row[k] > n:
                    return False
            elif not decimal(row[k]):
                return False
            elif k.endswith("_share") and Decimal(row[k]) > 1:
                return False
    return True


def _leg(leg, underlying, doc, generated):
    if not keys(leg, LEG) or not keys(leg["instrument"], INSTRUMENT) or not keys(leg["source"], SOURCE):
        return False
    ins = leg["instrument"]
    if not all(text(v) and v.upper() not in UNRESOLVED for v in ins.values()):
        return False
    if ins["market_kind"] not in KINDS or (ins["market_kind"] == "SPOT" and ins["contract_identity"] != "SPOT"):
        return False
    if (ins["base_asset_id"], ins["quote_asset_id"]) != (underlying["base_asset_id"], underlying["quote_asset_id"]):
        return False
    ident = hashlib.sha256(json.dumps(ins, sort_keys=True).encode()).hexdigest()[:24]
    if leg["instrument_id"] != ident or not VENUE_ID.fullmatch(str(leg["venue"])) or not text(leg["native_symbol"]):
        return False
    src = leg["source"]
    if not text(src["mapping_id"]) or not re.fullmatch(r"[a-f0-9]{64}", str(src["mapping_sha256"])) \
            or not nullable(src["payload_sha256"], lambda v: re.fullmatch(r"[a-f0-9]{64}", v) is not None) \
            or not nullable(src["tape_sha256"], lambda v: re.fullmatch(r"[a-f0-9]{64}", v) is not None):
        return False
    if leg["timestamp_kind"] not in ("UNRESOLVED", *TIMESTAMP_KINDS) or not nullable(leg["price_kind"], lambda v: v in PRICE_KINDS):
        return False
    for k in ("observed_at_utc", "received_at_utc"):
        if not nullable(leg[k], lambda v: stamp(v) is not None):
            return False
    if not nullable(leg["observer_clock_id"], text) or not nullable(leg["event_age_ms"], decimal):
        return False
    if not nullable(leg["price"], lambda v: decimal(v, positive=True)) or not nullable(leg["index_price"], lambda v: decimal(v, positive=True)):
        return False
    blocks = (("premium_to_index", PREMIUM, ()), ("basis_vs_spot", BASIS, ("against_venue",)),
              ("funding", FUNDING, ()), ("open_interest", OI, ()))
    for name, spec, keep in blocks:
        if not _fields(leg[name], spec, keep) or not _spec_ok(leg[name], spec):
            return False
    if not isinstance(leg["windows"], list) or len(leg["windows"]) != len(metrics.WINDOWS_S):
        return False
    for block, w in zip(leg["windows"], metrics.WINDOWS_S):
        if not _fields(block, WINDOW, ("window_s",)) or not _spec_ok(block, WINDOW) or block["window_s"] != w:
            return False
        if block["status"] == "AVAILABLE" and block["price_change_bps"] is None and block["oi_change_pct"] is None:
            return False
        if (block["price_change_bps"] is None) != (block["price_sign"] is None) \
                or (block["oi_change_pct"] is None) != (block["oi_sign"] is None):
            return False
    if not _timing(leg["timing"]):
        return False
    derivative = ins["market_kind"] in DERIVATIVE_KINDS
    if not derivative:
        for name in ("premium_to_index", "basis_vs_spot", "funding", "open_interest"):
            if leg[name]["status"] != "NOT_AVAILABLE":
                return False
    if ins["market_kind"] != "SPOT" and not ins["market_kind"].startswith("PERPETUAL") and leg["funding"]["status"] != "NOT_AVAILABLE":
        return False
    if leg["basis_vs_spot"]["status"] == "AVAILABLE" and not ins["market_kind"].startswith("FUTURE") \
            and leg["basis_vs_spot"]["annualized_pct"] is not None:
        return False
    if leg["open_interest"]["status"] == "AVAILABLE" and leg["open_interest"]["notional_quote"] is None \
            and leg["open_interest"]["reason"] is None:
        return False
    if leg["status"] == "AVAILABLE":
        if leg["reason"] is not None or any(leg[k] is None for k in
                                            ("observed_at_utc", "received_at_utc", "observer_clock_id", "event_age_ms", "price_kind")) \
                or leg["timestamp_kind"] == "UNRESOLVED":
            return False
        observed, received = stamp(leg["observed_at_utc"]), stamp(leg["received_at_utc"])
        if observed > received or received > generated:
            return False
        if Decimal(leg["event_age_ms"]) > doc["quality_policy"]["max_age_ms"]:
            return False
    elif leg["status"] == "NOT_AVAILABLE" and text(leg["reason"], REASON):
        if leg["price"] is not None or leg["index_price"] is not None:
            return False
        for name in ("premium_to_index", "basis_vs_spot", "funding", "open_interest"):
            if leg[name]["status"] != "NOT_AVAILABLE":
                return False
        if any(b["status"] != "NOT_AVAILABLE" for b in leg["windows"]):
            return False
    else:
        return False
    return True


def _validate(doc):
    if not keys(doc, TOP) or doc["schema_version"] != "1.0.0" or doc["product"] != "MarketDerivativesStress":
        return False
    if doc["authority"] != "OBSERVATIONAL_TELEMETRY" or doc["evidence_kind"] not in ("OBSERVATION", "SYNTHETIC"):
        return False
    if doc["execution_authority"] is not False or doc["costs_funding_fx_included"] is not False:
        return False
    generated, expiry = stamp(doc["generated_at_utc"]), stamp(doc["valid_until_utc"])
    if not generated or (doc["valid_until_utc"] is not None and (expiry is None or expiry < generated)):
        return False
    qp = doc["quality_policy"]
    if not keys(qp, {"max_age_ms", "max_skew_ms", "history_tolerance_ms"}) or not all(integer(x) for x in qp.values()):
        return False
    expected_params = {
        "windows_s": list(metrics.WINDOWS_S),
        "timing_scan": [{"period_s": p, "radius_ms": r} for p, r in metrics.TIMING_SCAN],
        "timing_min_events": metrics.TIMING_MIN_EVENTS,
        "histogram": {"period_s": metrics.HISTOGRAM_PERIOD_S, "bin_ms": metrics.HISTOGRAM_BIN_MS},
        "funding_reference_interval_s": metrics.FUNDING_REFERENCE_INTERVAL_S,
        "annualization": "SIMPLE_LINEAR_365D",
    }
    if doc["parameters"] != expected_params:
        return False
    sc = doc["source_counts"]
    if not keys(sc, {"expected", "supplied", "available"}) or not all(integer(x) for x in sc.values()):
        return False
    if not isinstance(doc["underlyings"], list) or not 1 <= len(doc["underlyings"]) <= 1000:
        return False
    total = supplied = available = pair_count = 0
    seen, expiries = set(), []
    for u in doc["underlyings"]:
        if not keys(u, UNDERLYING) or not text(u["base_asset_id"]) or not text(u["quote_asset_id"]):
            return False
        uid = hashlib.sha256(json.dumps({"base_asset_id": u["base_asset_id"], "quote_asset_id": u["quote_asset_id"]},
                                        sort_keys=True).encode()).hexdigest()[:24]
        if u["underlying_id"] != uid or uid in seen:
            return False
        seen.add(uid)
        if not isinstance(u["legs"], list) or not 1 <= len(u["legs"]) <= 50 or not isinstance(u["pairs"], list):
            return False
        index = {}
        for leg in u["legs"]:
            if not _leg(leg, u, doc, generated):
                return False
            key = (leg["instrument_id"], leg["venue"])
            if key in index:
                return False
            index[key] = leg
            total += 1
            supplied += leg["source"]["payload_sha256"] is not None
            if leg["status"] == "AVAILABLE":
                available += 1
                expiries.append(stamp(leg["observed_at_utc"]))
        seen_pairs = set()
        for p in u["pairs"]:
            if not keys(p, PAIR) or not text(p["reason"] or "X", REASON) and p["reason"] is not None:
                return False
            a, b = index.get((p["instrument_id"], p["reference_venue"])), index.get((p["instrument_id"], p["other_venue"]))
            pk = (p["instrument_id"], p["reference_venue"], p["other_venue"])
            if a is None or b is None or p["reference_venue"] == p["other_venue"] or pk in seen_pairs:
                return False
            seen_pairs.add(pk)
            if not nullable(p["event_skew_ms"], decimal) or not nullable(p["price_gap_bps"], _signed) \
                    or not nullable(p["funding_8h_difference"], _signed):
                return False
            if p["status"] == "AVAILABLE":
                if p["reason"] is not None or p["price_gap_bps"] is None or a["status"] != "AVAILABLE" or b["status"] != "AVAILABLE" \
                        or p["event_skew_ms"] is None or Decimal(p["event_skew_ms"]) > qp["max_skew_ms"]:
                    return False
            elif p["status"] != "NOT_AVAILABLE" or p["reason"] is None or p["price_gap_bps"] is not None \
                    or p["funding_8h_difference"] is not None:
                return False
            pair_count += 1
        if not _oi_total(u):
            return False
    if pair_count > 10_000 or (sc["expected"], sc["supplied"], sc["available"]) != (total, supplied, available):
        return False
    expected_expiry = None if not expiries else min(expiries).timestamp() * 1000 + qp["max_age_ms"]
    if (expected_expiry is None) != (expiry is None):
        return False
    return expected_expiry is None or abs(expiry.timestamp() * 1000 - expected_expiry) < 1


def _oi_total(u):
    t = u["open_interest_total"]
    if not keys(t, {"status", "reason", "notional_quote", "coverage"}) or not keys(t["coverage"], {"expected", "available", "missing"}):
        return False
    cov = t["coverage"]
    if not integer(cov["expected"]) or not integer(cov["available"]) or not isinstance(cov["missing"], list) \
            or not all(text(m) for m in cov["missing"]) or cov["available"] > cov["expected"]:
        return False
    derivatives = [x for x in u["legs"] if x["instrument"]["market_kind"] in DERIVATIVE_KINDS]
    have = [x for x in derivatives if x["open_interest"]["notional_quote"] is not None]
    if cov["expected"] != len(derivatives) or cov["available"] != len(have) \
            or len(cov["missing"]) != cov["expected"] - cov["available"]:
        return False
    if t["status"] == "AVAILABLE":
        return t["reason"] is None and cov["expected"] > 0 and cov["available"] == cov["expected"] and decimal(t["notional_quote"]) \
            and Decimal(t["notional_quote"]) == sum((Decimal(x["open_interest"]["notional_quote"]) for x in have), Decimal(0))
    return t["status"] == "NOT_AVAILABLE" and text(t["reason"], REASON) and t["notional_quote"] is None
