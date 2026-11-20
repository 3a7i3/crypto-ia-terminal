"""Deterministic last-trade composite for one closed UTC M5 window (method v1).

Offline and pure: the input packet already contains decoded trades and request
attempts. Nothing is fetched, scheduled, persisted or sent to a runtime.

Four instants are kept distinct for every source:
- ``trade_ms``: execution time declared by the venue (never a ticker time);
- ``first_received_ms``: first time the observer received that trade;
- ``instant_ms``: grid instant at which the series is evaluated;
- the ticker age of the Radar is not an input here and is never substituted.

Two controls are distinct: per-source trade freshness and inter-source skew.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

from .instruments import (
    EVIDENCE_KINDS, PRICE_KIND, binding_from_dict, instrument_dict,
    instrument_from_dict, instrument_id,
)

PERIOD_MS = 300_000
METHOD_ID = "cat.last-trade.equal-weight"
METHOD_VERSION = 1
# Hypotheses carried over from the v1 prototype, to be tested by a pilot.
V1_HYPOTHESIS = {
    "step_ms": 10_000,
    "points": 30,
    "max_trade_age_ms": {"mexc": 5_000, "kraken": 5_000},
    "max_inter_source_skew_ms": 5_000,
    "max_clock_lead_ms": 1_000,
}
LABELS = {"mexc": "MEXC", "kraken": "Kraken"}
REASONS = (
    "CLOCK_INCONSISTENT", "NO_OBSERVATION", "FETCH_ERROR",
    "LATE_RECEIPT", "STALE_TRADE",
)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TEXT = re.compile(r"[A-Za-z0-9@.:/_=-]{1,64}")
_DEC = re.compile(r"\d{1,20}(?:\.\d{1,20})?")
_TRADE_KEYS = {
    "venue", "provider", "native_symbol", "price", "qty", "side", "trade_ms",
    "native_time", "trade_id", "received_ms", "payload_sha256",
    "identity_evidence", "evidence_kind",
}
_POLL_KEYS = {
    "venue", "native_symbol", "provider", "requested_ms", "received_ms",
    "status", "reason", "payload_sha256",
}
_IDENTITY = {"mexc": "REQUEST_CONTEXT", "kraken": "NATIVE_KEY_ECHO"}


def _int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid {name}")
    return value


def _dec(value, name):
    if not isinstance(value, str) or not _DEC.fullmatch(value) or Decimal(value) <= 0:
        raise ValueError(f"invalid {name}")
    return Decimal(value)


def canonical_sha256(packet) -> str:
    data = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode()).hexdigest()


def _parameters(params, venues):
    if not isinstance(params, dict) or set(params) != set(V1_HYPOTHESIS):
        raise ValueError("parameters must be explicit and complete")
    step = _int(params["step_ms"], "step_ms")
    points = _int(params["points"], "points")
    if step == 0 or points == 0 or step * points != PERIOD_MS:
        raise ValueError("grid must cover exactly one M5 window")
    ages = params["max_trade_age_ms"]
    if not isinstance(ages, dict) or set(ages) != set(venues):
        raise ValueError("one freshness threshold per covered venue")
    for value in ages.values():
        _int(value, "max_trade_age_ms")
    _int(params["max_inter_source_skew_ms"], "max_inter_source_skew_ms")
    _int(params["max_clock_lead_ms"], "max_clock_lead_ms")
    return step, points


def _trade_key(trade):
    if trade["trade_id"] is not None:
        return (trade["venue"], trade["native_symbol"], "ID", trade["trade_id"])
    return (trade["venue"], trade["native_symbol"], "APPROX", str(trade["trade_ms"]),
            trade["price"], trade["qty"], trade["side"])


def _validate_trade(trade, bindings, kind):
    if not isinstance(trade, dict) or set(trade) != _TRADE_KEYS:
        raise ValueError("invalid trade record")
    venue = trade["venue"]
    if venue not in bindings:
        raise ValueError("trade from a venue outside the coverage")
    if trade["native_symbol"] != bindings[venue].native_symbol:
        raise ValueError("trade native symbol differs from binding")
    if trade["evidence_kind"] not in EVIDENCE_KINDS or trade["evidence_kind"] != kind:
        raise ValueError("evidence kinds cannot be mixed")
    if trade["identity_evidence"] != _IDENTITY[venue]:
        raise ValueError("invalid identity evidence")
    if not isinstance(trade["provider"], str) or not _TEXT.fullmatch(trade["provider"]):
        raise ValueError("invalid provider")
    _dec(trade["price"], "price")
    _dec(trade["qty"], "qty")
    if trade["side"] not in ("buy", "sell"):
        raise ValueError("invalid side")
    _int(trade["trade_ms"], "trade_ms")
    _int(trade["received_ms"], "received_ms")
    if not isinstance(trade["native_time"], str) or not trade["native_time"]:
        raise ValueError("invalid native time")
    if trade["trade_id"] is not None and (
        not isinstance(trade["trade_id"], str) or not _TEXT.fullmatch(trade["trade_id"])
    ):
        raise ValueError("invalid trade id")
    if not isinstance(trade["payload_sha256"], str) or not _HEX64.fullmatch(
        trade["payload_sha256"]
    ):
        raise ValueError("invalid payload digest")


def _validate_poll(poll, bindings):
    if not isinstance(poll, dict) or set(poll) != _POLL_KEYS:
        raise ValueError("invalid poll record")
    if poll["venue"] not in bindings or (
        poll["native_symbol"] != bindings[poll["venue"]].native_symbol
    ):
        raise ValueError("poll outside the coverage")
    _int(poll["requested_ms"], "requested_ms")
    _int(poll["received_ms"], "received_ms")
    if poll["received_ms"] < poll["requested_ms"]:
        raise ValueError("poll receipt before request")
    if poll["status"] not in ("OK", "FETCH_ERROR") or (
        (poll["status"] == "OK") != (poll["reason"] is None)
    ):
        raise ValueError("invalid poll status")
    if poll["payload_sha256"] is not None and (
        not isinstance(poll["payload_sha256"], str)
        or not _HEX64.fullmatch(poll["payload_sha256"])
    ):
        raise ValueError("invalid poll digest")


def _unique_trades(trades):
    """First reception wins; a later reception never rejuvenates a trade."""
    unique, duplicates = {}, {}
    ordered = sorted(trades, key=lambda t: (t["received_ms"], t["trade_ms"], _trade_key(t)))
    for trade in ordered:
        key = _trade_key(trade)
        if key in unique:
            first = unique[key]
            if any(first[f] != trade[f] for f in ("trade_ms", "price", "qty", "side")):
                raise ValueError("conflicting duplicate trade")
            duplicates[trade["venue"]] = duplicates.get(trade["venue"], 0) + 1
            continue
        unique[key] = {**trade, "first_received_ms": trade["received_ms"], "key": key}
    return list(unique.values()), duplicates


def _rank(trade):
    tid = trade["trade_id"]
    numeric = int(tid) if tid is not None and tid.isdigit() else -1
    return (trade["trade_ms"], numeric, trade["key"])


def _source_state(trades, polls, instant, max_age, max_lead):
    received = [t for t in trades if t["first_received_ms"] <= instant]
    latest = max(received, key=_rank) if received else None
    late = [
        t for t in trades
        if t["first_received_ms"] > instant
        and t["trade_ms"] <= instant
        and instant - t["trade_ms"] <= max_age
        and (latest is None or t["trade_ms"] > latest["trade_ms"])
    ]
    past_polls = [p for p in polls if p["received_ms"] <= instant]
    last_poll = max(past_polls, key=lambda p: (p["received_ms"], p["requested_ms"])) if past_polls else None
    detail = {
        "state": "EXCLUDED", "reason": None, "price": None, "trade_ms": None,
        "first_received_ms": None, "trade_age_ms": None, "receipt_lag_ms": None,
        "provider": None, "trade_id": None,
        "last_poll_status": None if last_poll is None else last_poll["status"],
    }
    if latest is not None:
        detail.update(
            price=latest["price"], trade_ms=latest["trade_ms"],
            first_received_ms=latest["first_received_ms"],
            trade_age_ms=instant - latest["trade_ms"],
            receipt_lag_ms=latest["first_received_ms"] - latest["trade_ms"],
            provider=latest["provider"], trade_id=latest["trade_id"],
        )
    if latest is not None and latest["trade_ms"] > latest["first_received_ms"] + max_lead:
        detail["reason"] = "CLOCK_INCONSISTENT"
    elif latest is None:
        detail["reason"] = (
            "LATE_RECEIPT" if late
            else "FETCH_ERROR" if last_poll is not None and last_poll["status"] == "FETCH_ERROR"
            else "NO_OBSERVATION"
        )
    elif instant - latest["trade_ms"] > max_age:
        detail["reason"] = "LATE_RECEIPT" if late else "STALE_TRADE"
    else:
        detail["state"] = "ELIGIBLE"
    return detail


def _fixed_bps(value):
    return format(value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN), "f")


def _candle(prices, expected):
    status = "COMPLETE" if len(prices) == expected else "INCOMPLETE"
    if status != "COMPLETE":
        return status, None
    values = [Decimal(p) for p in prices]
    return status, {
        "open": format(values[0], "f"), "high": format(max(values), "f"),
        "low": format(min(values), "f"), "close": format(values[-1], "f"),
    }


def compute(packet):
    """Return a MarketLastTradeComposite v1.0.0 publication for one M5 window."""
    if not isinstance(packet, dict) or set(packet) != {
        "version", "kind", "instrument", "bindings", "reference_venue",
        "start_ms", "parameters", "polls", "trades",
    }:
        raise ValueError("invalid packet")
    if packet["version"] != 2 or packet["kind"] not in EVIDENCE_KINDS:
        raise ValueError("expected packet v2 with explicit evidence kind")
    kind = packet["kind"]
    instrument = instrument_from_dict(packet["instrument"])
    raw_bindings = packet["bindings"]
    if not isinstance(raw_bindings, list) or not 1 <= len(raw_bindings) <= 2:
        raise ValueError("one or two covered venues")
    bindings = {}
    for item in raw_bindings:
        binding = binding_from_dict(item, instrument)
        if binding.venue in bindings:
            raise ValueError("duplicate venue binding")
        bindings[binding.venue] = binding
    reference = packet["reference_venue"]
    if reference not in bindings:
        raise ValueError("reference venue must be covered")
    venues = sorted(bindings, key=lambda v: (v != reference, v))
    step, points = _parameters(packet["parameters"], venues)
    params = packet["parameters"]
    start = _int(packet["start_ms"], "start_ms")
    if start % PERIOD_MS:
        raise ValueError("start must be UTC-aligned on M5")
    if not isinstance(packet["trades"], list) or not isinstance(packet["polls"], list):
        raise ValueError("trades and polls must be lists")
    for trade in packet["trades"]:
        _validate_trade(trade, bindings, kind)
    for poll in packet["polls"]:
        _validate_poll(poll, bindings)

    unique, duplicates = _unique_trades(packet["trades"])
    by_venue = {v: [t for t in unique if t["venue"] == v] for v in venues}
    polls = {v: [p for p in packet["polls"] if p["venue"] == v] for v in venues}
    two = len(venues) == 2
    other = venues[1] if two else None
    exclusions = {v: {} for v in venues}
    pair_exclusions = {}
    series = {"composite": [], **{v: [] for v in venues}}
    out_points = []

    for instant in range(start, start + PERIOD_MS, step):
        sources = {
            v: _source_state(by_venue[v], polls[v], instant,
                             params["max_trade_age_ms"][v], params["max_clock_lead_ms"])
            for v in venues
        }
        eligible = [v for v in venues if sources[v]["state"] == "ELIGIBLE"]
        for v in venues:
            if v in eligible:
                series[v].append(sources[v]["price"])
            else:
                reason = sources[v]["reason"]
                exclusions[v][reason] = exclusions[v].get(reason, 0) + 1
        point = {
            "instant_ms": instant, "status": None, "composite_price": None,
            "contributors": [], "spread_abs": None, "spread_bps": None,
            "inter_source_skew_ms": None, "pair_reason": None, "sources": sources,
        }
        if two and len(eligible) == 2:
            ref, alt = sources[reference], sources[other]
            skew = abs(ref["trade_ms"] - alt["trade_ms"])
            point["inter_source_skew_ms"] = skew
            if skew > params["max_inter_source_skew_ms"]:
                point["pair_reason"] = "EVENTS_NOT_SYNCHRONIZED"
            else:
                with localcontext() as ctx:
                    ctx.prec = 34
                    p_ref, p_alt = Decimal(ref["price"]), Decimal(alt["price"])
                    point["composite_price"] = format((p_ref + p_alt) / 2, "f")
                    point["spread_abs"] = format(p_alt - p_ref, "f")
                    point["spread_bps"] = _fixed_bps((p_alt - p_ref) / p_ref * 10_000)
                point["contributors"] = list(venues)
                series["composite"].append(point["composite_price"])
        elif two:
            point["pair_reason"] = "SOURCE_EXCLUDED"
        if point["pair_reason"]:
            pair_exclusions[point["pair_reason"]] = pair_exclusions.get(point["pair_reason"], 0) + 1
        point["status"] = (
            "COMPOSITE" if point["composite_price"] is not None
            else "SINGLE_VENUE_ONLY" if eligible else "NO_ELIGIBLE_SOURCE"
        )
        out_points.append(point)

    if two:
        status, ohlc = _candle(series["composite"], points)
        composite = {
            "series_kind": "COMPOSITE", "status": status,
            "label": "CAT composite · " + " + ".join(LABELS[v] for v in venues) + f" · v{METHOD_VERSION}",
            "venues": list(venues), "valid_points": len(series["composite"]), "ohlc": ohlc,
        }
    else:
        composite = {
            "series_kind": "COMPOSITE", "status": "NOT_APPLICABLE_SINGLE_VENUE_COVERAGE",
            "label": "Composite non applicable · une seule plateforme cote la paire",
            "venues": list(venues), "valid_points": 0, "ohlc": None,
        }
    single = {}
    for v in venues:
        status, ohlc = _candle(series[v], points)
        single[v] = {
            "series_kind": "SINGLE_VENUE", "venue": v, "status": status,
            "label": f"{LABELS[v]} seule · pas un composite",
            "valid_points": len(series[v]), "ohlc": ohlc,
        }
    return {
        "schema_version": "1.0.0",
        "product": "MarketLastTradeComposite",
        "authority": "OBSERVATIONAL_TELEMETRY",
        "execution_authority": False,
        "evidence_kind": kind,
        "price_kind": PRICE_KIND,
        "spread_semantics": "LAST_TRADE_DIFFERENCE_NOT_EXECUTABLE",
        "method": {
            "id": METHOD_ID, "version": METHOD_VERSION, "weights": "EQUAL",
            "sign_convention": "SPREAD_POSITIVE_MEANS_OTHER_ABOVE_REFERENCE",
            "candle": "SAMPLED_POINTS_ONLY",
        },
        "instrument_id": instrument_id(instrument),
        "instrument": instrument_dict(instrument),
        "bindings": [bindings[v].as_dict() for v in venues],
        "reference_venue": reference,
        "coverage": {"kind": "TWO_VENUES" if two else "SINGLE_VENUE", "venues": list(venues)},
        "parameters": json.loads(json.dumps(params)),
        "window": {
            "timeframe": "M5", "start_ms": start, "end_exclusive_ms": start + PERIOD_MS,
            "step_ms": step, "expected_points": points,
        },
        "input_sha256": canonical_sha256(packet),
        "counts": {
            "trades_supplied": len(packet["trades"]),
            "trades_unique": len(unique),
            "duplicates_by_venue": {v: duplicates.get(v, 0) for v in venues},
            "polls": len(packet["polls"]),
            "fetch_errors_by_venue": {
                v: sum(p["status"] == "FETCH_ERROR" for p in polls[v]) for v in venues
            },
        },
        "series": {"composite": composite, "single_venue": single},
        "exclusions_by_venue": {v: dict(sorted(exclusions[v].items())) for v in venues},
        "pair_exclusions": dict(sorted(pair_exclusions.items())),
        "points": out_points,
    }


if __name__ == "__main__":
    print(json.dumps(compute(json.loads(Path(sys.argv[1]).read_text())), indent=2))
