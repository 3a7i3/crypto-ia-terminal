"""Pure publication builder for MarketDerivativesStress v1.0.0.

No writer, schedule, socket or exchange client. The roster of expected legs is
explicit and independent from the observations: a leg nobody supplied stays visible
as SOURCE_NOT_SUPPLIED. The publication carries no score, ranking or threshold.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re

from observability.venue_quote_comparison import _instrument_known

from . import metrics
from .models import (DERIVATIVE_KINDS, NATIVE_SYMBOL, PRICE_KINDS, TIMESTAMP_KINDS, VENUE_ID,
                     LegObservation, StressBinding)
from .schema import validate_publication

MAX_LEGS = 1_000
MAX_PAIRS = 10_000


def iso(value):
    return None if value is None else value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def aware(value):
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def instrument_id(instrument):
    return hashlib.sha256(json.dumps(asdict(instrument), sort_keys=True).encode()).hexdigest()[:24]


def underlying_id(base, quote):
    return hashlib.sha256(json.dumps({"base_asset_id": base, "quote_asset_id": quote}, sort_keys=True).encode()).hexdigest()[:24]


def validate_binding(b):
    if not isinstance(b, StressBinding) or not VENUE_ID.fullmatch(b.venue):
        raise ValueError("INVALID_VENUE_ID")
    if not NATIVE_SYMBOL.fullmatch(b.native_symbol):
        raise ValueError("INVALID_NATIVE_SYMBOL")
    if not _instrument_known(b.instrument):
        raise ValueError("UNRESOLVED_INSTRUMENT")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", b.mapping_id):
        raise ValueError("MISSING_MAPPING_ID")
    if not re.fullmatch(r"[a-f0-9]{64}", b.mapping_sha256):
        raise ValueError("MISSING_MAPPING_HASH")


def _price(value):
    n = metrics.number(value, positive=True)
    return None if n is None else metrics.fixed(n, 8)


def _blocked(reason):
    """All metric blocks of a leg that cannot be evaluated, with one shared reason."""
    f = metrics.refused
    return {
        "premium_to_index": f(reason, bps=None),
        "basis_vs_spot": f(reason, bps=None, annualized_pct=None, against_venue=None),
        "funding": f(reason, rate=None, interval_s=None, next_funding_utc=None,
                     rate_8h_equivalent=None, annualized_simple_pct=None),
        "open_interest": f(reason, value=None, unit=None, notional_quote=None),
        "windows": [f(reason, window_s=w, sample_gap_ms=None, price_change_bps=None, price_sign=None,
                      oi_change_pct=None, oi_sign=None) for w in metrics.WINDOWS_S],
    }


def _quality(obs, binding, as_of, max_age_ms):
    """Leg-level admission: exchange-side time qualified, clocks consistent, fresh enough."""
    if obs is None:
        return "SOURCE_NOT_SUPPLIED", None
    if obs.failure:
        return obs.failure, None
    if obs.timestamp_kind not in TIMESTAMP_KINDS:
        return "UNRESOLVED_TIMESTAMP_KIND", None
    if not aware(obs.observed_at):
        return "MISSING_EXCHANGE_TIMESTAMP", None
    if not aware(obs.received_at):
        return "MISSING_RECEIPT_TIMESTAMP", None
    if not isinstance(obs.observer_clock_id, str) or not obs.observer_clock_id.strip():
        return "UNRESOLVED_OBSERVER_CLOCK", None
    if obs.observed_at > obs.received_at or obs.received_at > as_of:
        return "FUTURE_OR_INCONSISTENT_CLOCK", None
    age = (as_of - obs.observed_at).total_seconds() * 1000
    if age > max_age_ms:
        return "STALE", age
    if obs.price_kind not in PRICE_KINDS:
        return "UNRESOLVED_PRICE_KIND", None
    return None, age


def _same_clock(a, b, max_skew_ms):
    if a.observer_clock_id != b.observer_clock_id:
        return "OBSERVER_CLOCKS_NOT_ALIGNED", None
    if a.timestamp_kind != b.timestamp_kind:
        return "TIMESTAMP_KINDS_DIFFER", None
    skew = abs((a.observed_at - b.observed_at).total_seconds() * 1000)
    if skew > max_skew_ms:
        return "EVENTS_NOT_SYNCHRONIZED", skew
    return None, skew


def build_publication(bindings, observations, *, as_of, max_age_ms, max_skew_ms,
                      history_tolerance_ms, evidence_kind):
    if not aware(as_of) or evidence_kind not in ("OBSERVATION", "SYNTHETIC"):
        raise ValueError("Explicit publication clock and evidence kind required")
    for v in (max_age_ms, max_skew_ms, history_tolerance_ms):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError("Quality limits must be explicit non-negative integer milliseconds")
    bindings, observations = list(bindings), list(observations)
    if not bindings or len(bindings) > MAX_LEGS:
        raise ValueError("Explicit bounded binding roster required")
    expected, order = {}, {}
    for b in bindings:
        validate_binding(b)
        key = (instrument_id(b.instrument), b.venue)
        if key in expected:
            raise ValueError("Duplicate venue/instrument binding")
        expected[key] = b
        order.setdefault((b.instrument.base_asset_id, b.instrument.quote_asset_id), []).append(b)
    received = {}
    for o in observations:
        if not isinstance(o, LegObservation):
            raise ValueError("Foreign observation")
        key = (instrument_id(o.binding.instrument), o.binding.venue)
        if expected.get(key) != o.binding or key in received:
            raise ValueError("Foreign, changed or duplicate observation")
        received[key] = o

    expiries, available_legs, pair_total = [], 0, 0
    underlyings = []
    for (base, quote), roster in order.items():
        admitted = {}   # (instrument_id, venue) -> (observation, age) for admitted legs
        reasons = {}
        for b in roster:
            key = (instrument_id(b.instrument), b.venue)
            obs = received.get(key)
            reason, age = _quality(obs, b, as_of, max_age_ms)
            reasons[key] = (reason, age)
            if reason is None:
                admitted[key] = obs
                expiries.append(obs.observed_at + timedelta(milliseconds=max_age_ms))
        spot_legs = [b for b in roster if b.instrument.market_kind == "SPOT"
                     and (instrument_id(b.instrument), b.venue) in admitted
                     and admitted[(instrument_id(b.instrument), b.venue)].price_kind in ("BOOK_MID", "LAST_TRADE")]
        legs = []
        for b in roster:
            key = (instrument_id(b.instrument), b.venue)
            obs = received.get(key)
            reason, age = reasons[key]
            is_derivative = b.instrument.market_kind in DERIVATIVE_KINDS
            if reason is None:
                available_legs += 1
                block = _evaluate_leg(b, obs, is_derivative, admitted, spot_legs, as_of, max_skew_ms,
                                      history_tolerance_ms)
            else:
                block = _blocked("LEG_UNAVAILABLE")
            tape = None if obs is None else obs.tape
            block["timing"] = metrics.timing(tape) if tape is not None else metrics.timing(None)
            block["funding"] = {**block["funding"], "next_funding_utc": iso(block["funding"]["next_funding_utc"])}
            legs.append({
                "venue": b.venue, "native_symbol": b.native_symbol,
                "instrument_id": instrument_id(b.instrument), "instrument": asdict(b.instrument),
                "status": "NOT_AVAILABLE" if reason else "AVAILABLE", "reason": reason,
                "observed_at_utc": iso(obs.observed_at) if obs is not None and aware(obs.observed_at) else None,
                "received_at_utc": iso(obs.received_at) if obs is not None and aware(obs.received_at) else None,
                "observer_clock_id": (obs.observer_clock_id or None) if obs is not None else None,
                "timestamp_kind": obs.timestamp_kind if obs is not None and obs.timestamp_kind in TIMESTAMP_KINDS else "UNRESOLVED",
                "event_age_ms": None if age is None else metrics.fixed(Decimal(str(age)), 3),
                "price_kind": obs.price_kind if obs is not None and obs.price_kind in PRICE_KINDS else None,
                "price": None if reason else _price(obs.price),
                "index_price": None if reason else _price(obs.index_price),
                **block,
                "source": {
                    "mapping_id": b.mapping_id, "mapping_sha256": b.mapping_sha256,
                    "payload_sha256": None if obs is None else obs.payload_sha256,
                    "tape_sha256": None if tape is None else tape.tape_sha256,
                },
            })
        pairs = _pairs(roster, admitted, max_skew_ms)
        pair_total += len(pairs)
        if pair_total > MAX_PAIRS:
            raise ValueError("Publication pair budget exceeded; never truncate")
        underlyings.append({
            "underlying_id": underlying_id(base, quote), "base_asset_id": base, "quote_asset_id": quote,
            "legs": legs, "pairs": pairs, "open_interest_total": _oi_total(roster, legs),
        })
    doc = {
        "schema_version": "1.0.0", "product": "MarketDerivativesStress",
        "authority": "OBSERVATIONAL_TELEMETRY", "evidence_kind": evidence_kind,
        "generated_at_utc": iso(as_of), "valid_until_utc": iso(min(expiries)) if expiries else None,
        "execution_authority": False, "costs_funding_fx_included": False,
        "quality_policy": {"max_age_ms": max_age_ms, "max_skew_ms": max_skew_ms,
                           "history_tolerance_ms": history_tolerance_ms},
        "parameters": {
            "windows_s": list(metrics.WINDOWS_S),
            "timing_scan": [{"period_s": p, "radius_ms": r} for p, r in metrics.TIMING_SCAN],
            "timing_min_events": metrics.TIMING_MIN_EVENTS,
            "histogram": {"period_s": metrics.HISTOGRAM_PERIOD_S, "bin_ms": metrics.HISTOGRAM_BIN_MS},
            "funding_reference_interval_s": metrics.FUNDING_REFERENCE_INTERVAL_S,
            "annualization": "SIMPLE_LINEAR_365D",
        },
        "source_counts": {
            "expected": len(bindings),
            "supplied": sum(o.payload_sha256 is not None for o in received.values()),
            "available": available_legs,
        },
        "underlyings": underlyings,
    }
    if not validate_publication(doc):
        raise ValueError("Publication failed its closed presentation contract")
    return doc


def _evaluate_leg(b, obs, is_derivative, admitted, spot_legs, as_of, max_skew_ms, tolerance_ms):
    out = _blocked("NOT_APPLICABLE")
    price = obs.price
    if is_derivative:
        out["premium_to_index"] = metrics.premium(price, obs.index_price)
        # Basis: same-venue spot first, else the first admitted spot leg of the roster.
        same = [s for s in spot_legs if s.venue == b.venue]
        ref = (same or spot_legs or [None])[0]
        if ref is None:
            out["basis_vs_spot"] = metrics.refused("NO_SPOT_REFERENCE", bps=None, annualized_pct=None, against_venue=None)
        else:
            spot = admitted[(instrument_id(ref.instrument), ref.venue)]
            why, _ = _same_clock(obs, spot, max_skew_ms)
            if why:
                out["basis_vs_spot"] = metrics.refused(why, bps=None, annualized_pct=None, against_venue=ref.venue)
            else:
                result = metrics.basis(price, spot.price)
                result["against_venue"] = ref.venue
                if result["status"] == "AVAILABLE" and b.instrument.market_kind.startswith("FUTURE"):
                    pct, why = metrics.annualized_basis(result["bps"], obs.expiry_at, as_of)
                    result["annualized_pct"] = pct
                out["basis_vs_spot"] = result
        out["funding"] = (metrics.funding(obs.funding_rate, obs.funding_interval_s, obs.next_funding_at, as_of)
                          if b.instrument.market_kind.startswith("PERPETUAL")
                          else metrics.refused("NOT_APPLICABLE", rate=None, interval_s=None, next_funding_utc=None,
                                               rate_8h_equivalent=None, annualized_simple_pct=None))
        out["open_interest"] = metrics.open_interest(obs.open_interest, obs.open_interest_unit, price,
                                                     obs.contract_size_base)
    out["windows"] = [metrics.window(price, obs.open_interest if is_derivative else None, obs.samples, as_of, w,
                                     tolerance_ms) for w in metrics.WINDOWS_S]
    return out


def _pairs(roster, admitted, max_skew_ms):
    pairs = []
    for a in roster:
        for c in roster:
            if a.venue == c.venue or a.instrument != c.instrument:
                continue
            ka, kc = (instrument_id(a.instrument), a.venue), (instrument_id(c.instrument), c.venue)
            row = {"instrument_id": ka[0], "reference_venue": a.venue, "other_venue": c.venue,
                   "status": "NOT_AVAILABLE", "reason": None, "event_skew_ms": None,
                   "price_gap_bps": None, "funding_8h_difference": None}
            if ka not in admitted or kc not in admitted:
                row["reason"] = "QUOTE_UNAVAILABLE"
            else:
                x, y = admitted[ka], admitted[kc]
                why, skew = _same_clock(x, y, max_skew_ms)
                row["event_skew_ms"] = None if skew is None else metrics.fixed(Decimal(str(skew)), 3)
                if x.price_kind != y.price_kind:
                    why = "PRICE_KINDS_DIFFER"
                if why:
                    row["reason"] = why
                else:
                    row.update(status="AVAILABLE", price_gap_bps=metrics.gap_bps(x.price, y.price))
                    fx = metrics.funding(x.funding_rate, x.funding_interval_s, x.next_funding_at, x.observed_at)
                    fy = metrics.funding(y.funding_rate, y.funding_interval_s, y.next_funding_at, y.observed_at)
                    if fx["status"] == fy["status"] == "AVAILABLE":
                        row["funding_8h_difference"] = metrics.fixed(
                            Decimal(fy["rate_8h_equivalent"]) - Decimal(fx["rate_8h_equivalent"]), 10)
                    if row["price_gap_bps"] is None:
                        row.update(status="NOT_AVAILABLE", reason="PRICE_MISSING")
            pairs.append(row)
    return pairs


def _oi_total(roster, legs):
    derivatives = [leg for leg, b in zip(legs, roster) if b.instrument.market_kind in DERIVATIVE_KINDS]
    have = [leg for leg in derivatives if leg["open_interest"]["notional_quote"] is not None]
    missing = [leg["venue"] + ":" + leg["native_symbol"] for leg in derivatives if leg not in have]
    cov = {"expected": len(derivatives), "available": len(have), "missing": missing}
    if not derivatives:
        return {"status": "NOT_AVAILABLE", "reason": "NO_DERIVATIVE_LEG", "notional_quote": None, "coverage": cov}
    if missing:
        return {"status": "NOT_AVAILABLE", "reason": "PARTIAL_COVERAGE", "notional_quote": None, "coverage": cov}
    total = sum((Decimal(leg["open_interest"]["notional_quote"]) for leg in have), Decimal(0))
    return {"status": "AVAILABLE", "reason": None, "notional_quote": metrics.fixed(total, 8), "coverage": cov}
