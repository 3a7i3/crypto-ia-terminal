"""Closed validation of MarketBboComposite 1.0.0.

``validate_bbo`` returns a list of error codes (empty when valid). It checks
the closed shape and the internal consistency of what is published: per
source, values present only for eligible states, ``mid`` and ``spread_bps``
consistent with bid/ask; per point, the category consistent with the source
states, the signed gap and the closed threshold; counts and candles
consistent with the points. It never rebuilds a book.
"""
from __future__ import annotations

import re
from decimal import Decimal, localcontext

from . import bbo_book as bk
from .composite import PERIOD_MS
from .instruments import EVIDENCE_KINDS

TOP = {"schema", "schema_version", "pilot", "evidence_kind", "instrument", "market_type",
       "venues", "parameters", "window", "points", "counts", "candles"}
PARAMS = {"liveness_max_ms", "gap_max_bps", "gap_boundary", "weights", "reference_venue",
          "step_ms", "points_per_window"}
POINT = {"instant_ms", "category", "composite_mid", "mid_gap_bps", "sources"}
SOURCE = {"state", "eligible", "bid", "ask", "bid_qty", "ask_qty", "mid", "spread_bps",
          "continuity", "lost_reason", "quote_as_of_ms", "quote_age_ms", "last_top_change_ms",
          "liveness_ms", "liveness_age_ms", "source_timestamp"}
VALUE_KEYS = ("bid", "ask", "bid_qty", "ask_qty", "mid", "spread_bps")
CANDLE = {"status", "points", "open", "high", "low", "close"}
OHLC = ("open", "high", "low", "close")
CONTINUITY = {"NOT_INITIALIZED", "SYNCED", "CONTINUITY_LOST"}
_POS = re.compile(r"[0-9]{1,40}(\.[0-9]{1,40})?")
_SIGNED6 = re.compile(r"-?[0-9]{1,40}\.[0-9]{6}")


def _pos(v):
    if not isinstance(v, str) or not _POS.fullmatch(v):
        return None
    d = Decimal(v)
    return d if d > 0 else None


def _q6(d):
    return d.quantize(Decimal("0.000001"), context=bk.CTX)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _source(src, errors, where):
    if not isinstance(src, dict) or set(src) != SOURCE:
        errors.append(f"{where}:SOURCE_KEYS")
        return None
    if src["state"] not in bk.SOURCE_STATES:
        errors.append(f"{where}:SOURCE_STATE")
        return None
    if src["eligible"] is not (src["state"] in bk.ELIGIBLE):
        errors.append(f"{where}:ELIGIBLE_FLAG")
    if src["continuity"] not in CONTINUITY:
        errors.append(f"{where}:CONTINUITY")
    if src["state"] in bk.ELIGIBLE and src["continuity"] != "SYNCED":
        errors.append(f"{where}:ELIGIBLE_NOT_SYNCED")
    if not src["eligible"]:
        if any(src[k] is not None for k in VALUE_KEYS):
            errors.append(f"{where}:VALUES_ON_EXCLUDED_SOURCE")
        return None
    vals = {k: _pos(src[k]) for k in ("bid", "ask", "bid_qty", "ask_qty", "mid")}
    if any(v is None for v in vals.values()):
        errors.append(f"{where}:VALUE_FORMAT")
        return None
    if not vals["ask"] > vals["bid"]:
        errors.append(f"{where}:CROSSED_OR_LOCKED")
        return None
    with localcontext(bk.CTX):
        mid = (vals["bid"] + vals["ask"]) / bk.TWO
        spread = (vals["ask"] - vals["bid"]) / mid * bk.BPS
    if mid != vals["mid"]:
        errors.append(f"{where}:MID")
    if not isinstance(src["spread_bps"], str) or not _SIGNED6.fullmatch(src["spread_bps"]) \
            or Decimal(src["spread_bps"]) != _q6(spread):
        errors.append(f"{where}:SPREAD_BPS")
    for k in ("quote_as_of_ms", "liveness_ms", "last_top_change_ms", "quote_age_ms", "liveness_age_ms"):
        if not _is_int(src[k]):
            errors.append(f"{where}:{k.upper()}")
    return mid


def _candle(c, series, errors, where):
    if not isinstance(c, dict) or set(c) != CANDLE:
        errors.append(f"{where}:CANDLE_KEYS")
        return
    valid = [v for v in series if v is not None]
    if c["points"] != len(valid):
        errors.append(f"{where}:CANDLE_POINTS")
    if len(valid) == len(series) == 30:
        if c["status"] != "COMPLETE":
            errors.append(f"{where}:CANDLE_STATUS")
            return
        got = tuple(_pos(c[k]) for k in OHLC)
        if got != (valid[0], max(valid), min(valid), valid[-1]):
            errors.append(f"{where}:CANDLE_OHLC")
    else:
        if c["status"] != "INCOMPLETE" or any(c[k] is not None for k in OHLC):
            errors.append(f"{where}:INCOMPLETE_HAS_OHLC")


def validate_bbo(pub):
    errors = []
    if not isinstance(pub, dict) or set(pub) != TOP:
        return ["TOP_KEYS"]
    if pub["schema"] != "MarketBboComposite" or pub["schema_version"] != "1.0.0":
        errors.append("SCHEMA_ID")
    if pub["evidence_kind"] not in EVIDENCE_KINDS:
        errors.append("EVIDENCE_KIND")
    if pub["market_type"] != "SPOT":
        errors.append("MARKET_TYPE")
    p = pub["parameters"]
    if not isinstance(p, dict) or set(p) != PARAMS:
        return errors + ["PARAMETER_KEYS"]
    gmax = _pos(p["gap_max_bps"])
    if (not _is_int(p["liveness_max_ms"]) or p["liveness_max_ms"] <= 0 or gmax is None
            or p["gap_boundary"] != "CLOSED" or p["weights"] != "EQUAL"
            or p["reference_venue"] != bk.REFERENCE or p["step_ms"] != 10_000
            or p["points_per_window"] != 30):
        return errors + ["PARAMETERS"]
    w = pub["window"]
    if (not isinstance(w, dict) or set(w) != {"index", "start_ms", "end_ms"}
            or not _is_int(w["start_ms"]) or w["start_ms"] % PERIOD_MS
            or w["end_ms"] != w["start_ms"] + PERIOD_MS):
        return errors + ["WINDOW"]
    points = pub["points"]
    if not isinstance(points, list) or len(points) != 30:
        return errors + ["POINT_COUNT"]
    cats = {c: 0 for c in bk.CATEGORIES}
    states = {v: {s: 0 for s in bk.SOURCE_STATES} for v in bk.VENUES}
    comp_series, series = [], {v: [] for v in bk.VENUES}
    for i, pt in enumerate(points):
        where = f"P{i}"
        if not isinstance(pt, dict) or set(pt) != POINT:
            errors.append(f"{where}:POINT_KEYS")
            return errors
        if pt["instant_ms"] != w["start_ms"] + i * 10_000:
            errors.append(f"{where}:INSTANT")
        cat = pt["category"]
        if cat not in bk.CATEGORIES:
            errors.append(f"{where}:CATEGORY")
            return errors
        cats[cat] += 1
        if cat == bk.NOT_EVALUATED:
            if pt["sources"] is not None or pt["composite_mid"] is not None or pt["mid_gap_bps"] is not None:
                errors.append(f"{where}:NOT_EVALUATED_HAS_DATA")
            comp_series.append(None)
            for v in bk.VENUES:
                series[v].append(None)
            continue
        if not isinstance(pt["sources"], dict) or set(pt["sources"]) != set(bk.VENUES):
            errors.append(f"{where}:SOURCES")
            return errors
        mids = {}
        for v in bk.VENUES:
            src = pt["sources"][v]
            mids[v] = _source(src, errors, f"{where}:{v}")
            if isinstance(src, dict) and src.get("state") in bk.SOURCE_STATES:
                states[v][src["state"]] += 1
            series[v].append(mids[v])
        n = sum(m is not None for m in mids.values())
        expected = None
        comp = None
        if n == 2:
            with localcontext(bk.CTX):
                gap = (mids["kraken"] - mids["mexc"]) / mids["mexc"] * bk.BPS
            if not isinstance(pt["mid_gap_bps"], str) or not _SIGNED6.fullmatch(pt["mid_gap_bps"]) \
                    or Decimal(pt["mid_gap_bps"]) != _q6(gap):
                errors.append(f"{where}:GAP")
            expected = bk.COMPOSITE if abs(gap) <= gmax else bk.EXCESSIVE_GAP
            if expected == bk.COMPOSITE:
                with localcontext(bk.CTX):
                    comp = (mids["kraken"] + mids["mexc"]) / bk.TWO
        else:
            if pt["mid_gap_bps"] is not None:
                errors.append(f"{where}:GAP_WITHOUT_TWO_SOURCES")
            expected = bk.SINGLE_SOURCE if n == 1 else bk.SOURCE_EXCLUDED
        if cat != expected:
            errors.append(f"{where}:CATEGORY_INCONSISTENT")
        if comp is None:
            if pt["composite_mid"] is not None:
                errors.append(f"{where}:COMPOSITE_WITHOUT_ELIGIBILITY")
        elif _pos(pt["composite_mid"]) != comp:
            errors.append(f"{where}:COMPOSITE_MID")
        comp_series.append(comp)
    counts = pub["counts"]
    if counts != {"by_category": cats, "by_source_state": states}:
        errors.append("COUNTS")
    c = pub["candles"]
    if not isinstance(c, dict) or set(c) != {"composite", *bk.VENUES}:
        return errors + ["CANDLES_KEYS"]
    _candle(c["composite"], comp_series, errors, "composite")
    for v in bk.VENUES:
        _candle(c[v], series[v], errors, v)
    return errors
