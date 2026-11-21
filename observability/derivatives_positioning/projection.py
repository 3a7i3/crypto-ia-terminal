"""Bounded read projection of the positioning store for the Operator API (lot 2).

Pure read: the store is opened read-only by the caller; nothing is computed here that
the store does not already expose (latest, OI change, history, comparisons), except the
eligibility of chart series, which only *filters* stored points. No score, no signal.

A roster declares which legs are shown and the cadence of each (the cadence is a
declaration of the collector, never inferred from the data).
"""

from __future__ import annotations

import json
from pathlib import Path

from .contract import iso_ms, parse_utc_ms
from .models_roster import parse_roster
from .store import PositioningStore

PRODUCT = "MarketDerivativesPositioning"
SCHEMA_VERSION = "1.0.0"
MAX_CHART_WINDOW_S = 86_400
MAX_CHART_POINTS = 400


def load_roster(path):
    return parse_roster(json.loads(Path(path).read_text(encoding="utf-8")))


def project(store: PositioningStore, roster, *, as_of_ms):
    legs_out, pair_legs = [], []
    for leg in roster["legs"]:
        key = (leg["venue"], leg["native_symbol"], leg["contract_type"])
        latest = store.latest(*key, as_of_ms=as_of_ms)
        oi = store.oi_change(*key, as_of_ms=as_of_ms, cadence_s=leg["cadence_s"])
        legs_out.append({
            "leg_id": leg_id(leg), **{k: leg[k] for k in ("venue", "native_symbol", "contract_type", "cadence_s")},
            "latest": latest, "oi_change": oi["windows"], "tolerance_ms": oi["tolerance_ms"],
        })
        pair_legs.append(key)
    cmp = store.compare(pair_legs, as_of_ms=as_of_ms) if len(pair_legs) > 1 else {"pairs": []}
    pairs = cmp["pairs"]  # "a"/"b" are already leg ids (venue:symbol:type)
    return {
        "product": PRODUCT, "schema_version": SCHEMA_VERSION, "authority": "OBSERVATIONAL_TELEMETRY",
        "execution_authority": False, "evidence_kind": roster["evidence_kind"],
        "generated_at_utc": iso_ms(as_of_ms), "policy": store.policy.as_dict(),
        "legs": legs_out, "pairs": pairs,
        "chart": chart(store, roster, legs_out, as_of_ms=as_of_ms),
    }


def leg_id(leg):
    return "%s:%s:%s" % (leg["venue"], leg["native_symbol"], leg["contract_type"])


def chart(store, roster, legs_out, *, as_of_ms):
    """Price + OI series per leg, kept only when comparable over the window and on its cadence grid.

    A leg is admitted when, over [as_of - window, as_of]: every point has a mark price and an
    OI in the unit, contract size and time basis of the latest observation; every point lies
    within the tolerance of its cadence slot with at most one point per slot; coverage reaches
    the policy minimum. Legs shown together must share cadence and time basis with the first
    admitted leg; otherwise they are listed with a reason and no points.
    """
    window_s = roster["chart_window_s"]
    start = as_of_ms - window_s * 1000
    series, reference = [], None
    for leg, out in zip(roster["legs"], legs_out):
        row = {"leg_id": out["leg_id"], "status": "NOT_AVAILABLE", "reason": None, "price_unit": None,
               "oi_unit": None, "contract_size_base": None, "time_basis": None, "cadence_s": leg["cadence_s"],
               "coverage": None, "points": []}
        series.append(row)
        if out["latest"]["status"] != "AVAILABLE":
            row["reason"] = "NO_OBSERVATION"
            continue
        if leg["cadence_s"] is None:
            row["reason"] = "CADENCE_UNKNOWN"
            continue
        last = out["latest"]["observation"]
        oi_last = last["measures"]["open_interest"]
        if oi_last["status"] != "AVAILABLE" or last["measures"]["mark_price"]["status"] != "AVAILABLE":
            row["reason"] = "LATEST_PRICE_OR_OI_MISSING"
            continue
        hist = store.history(leg["venue"], leg["native_symbol"], leg["contract_type"], start, as_of_ms,
                             limit=MAX_CHART_POINTS, cadence_s=leg["cadence_s"])
        if hist["coverage"]["truncated"]:
            row["reason"] = "HISTORY_TOO_LONG"
            continue
        why, points = _comparable_points(hist["observations"], last, leg["cadence_s"], store.policy)
        row.update(price_unit=last["quote_currency"], oi_unit=oi_last["unit"],
                   contract_size_base=oi_last["contract_size_base"], time_basis=last["time_basis"],
                   coverage=hist["coverage"]["ratio"])
        if why:
            row["reason"] = why
            continue
        if hist["coverage"]["ratio"] is None or float(hist["coverage"]["ratio"]) < float(store.policy.min_coverage):
            row["reason"] = "INSUFFICIENT_COVERAGE"
            continue
        if reference is None:
            reference = row
        elif (row["cadence_s"], row["time_basis"]) != (reference["cadence_s"], reference["time_basis"]):
            row["reason"] = "NOT_ALIGNED_WITH_REFERENCE_LEG"
            continue
        row.update(status="AVAILABLE", points=points)
    return {"window_s": window_s, "start_utc": iso_ms(start), "end_utc": iso_ms(as_of_ms),
            "reference_leg_id": None if reference is None else reference["leg_id"], "series": series,
            "note": "Prix et OI en unités natives, axes séparés ; aucune conversion entre plateformes."}


def _comparable_points(observations, last, cadence_s, policy):
    oi_ref = last["measures"]["open_interest"]
    slot_ms, tol = cadence_s * 1000, policy.min_tolerance_ms
    seen, points = set(), []
    for o in observations:
        m = o["measures"]
        if m["mark_price"]["status"] != "AVAILABLE" or m["open_interest"]["status"] != "AVAILABLE":
            return "POINT_WITHOUT_PRICE_OR_OI", []
        oi = m["open_interest"]
        if oi["unit"] != oi_ref["unit"]:
            return "OPEN_INTEREST_UNITS_DIFFER", []
        if oi["contract_size_base"] != oi_ref["contract_size_base"]:
            return "CONTRACT_SIZES_DIFFER", []
        if o["time_basis"] != last["time_basis"]:
            return "TIME_BASES_DIFFER", []
        t = _ms(o["effective_time_utc"])
        slot = round(t / slot_ms)
        if abs(t - slot * slot_ms) > tol or slot in seen:
            return "POINTS_OFF_CADENCE_GRID", []
        seen.add(slot)
        points.append({"t": o["effective_time_utc"], "price": m["mark_price"]["value"], "oi": oi["value"]})
    return None, points


def _ms(iso):
    return parse_utc_ms(iso, "t")
