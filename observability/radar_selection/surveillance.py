"""R0-B — light surveillance: compact measures from minimal observations.

Only fields that the observation really carries are measured. A measure that
the source cannot support is UNKNOWN with its reason, never 0. No raw journal
is kept: the output is a bounded set of counters, measures and evidence refs.
Depth is read only from an L2 block already provided; it is never derived from
a BBO, and no book is opened to fill a field.
"""
from __future__ import annotations

from decimal import Decimal, localcontext

from . import contract as c
from .fixture import decimal

D = Decimal
BPS = D(10_000)


def _q(v: Decimal, places: str = "0.01") -> str:
    return str(v.quantize(D(places)))


def _median(values: list) -> Decimal:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def observe(obs: dict | None, now_ms: int) -> dict:
    """Measures of one market from its observation (or its absence). Pure."""
    if obs is None:
        return {"present": False, "reason": "NO_OBSERVATION", "evidence_ref": None,
                "time": {"state": "UNKNOWN", "reason": "NO_OBSERVATION"},
                "contradictions": [], "measures": {}}
    with localcontext() as ctx:
        ctx.prec = 34
        return _observe(obs, now_ms)


def _observe(obs: dict, now_ms: int) -> dict:
    w = obs["window"]
    start, step, points = w["start_ms"], w["step_ms"], w["points"]
    grid = [start + k * step for k in range(points)]
    end = grid[-1]
    samples = obs["samples"]
    contradictions = []
    out = {"present": True, "reason": None, "evidence_ref": obs["evidence_ref"],
           "price_kind": obs["price_kind"],
           "window": {"start_ms": start, "step_ms": step, "points": points, "end_ms": end},
           "sample_count": len(samples), "contradictions": contradictions, "measures": {}}
    m = out["measures"]

    # --- time certification (B04)
    times = [s["t_ms"] for s in samples]
    if not samples:
        out["time"] = {"state": "UNKNOWN", "reason": "NO_SAMPLES"}
    elif any(t is None for t in times):
        out["time"] = {"state": "UNCERTIFIED", "reason": "TIMESTAMP_MISSING",
                       "missing": sum(t is None for t in times)}
    elif any(b <= a for a, b in zip(times, times[1:])):
        out["time"] = {"state": "INCOHERENT", "reason": "TIMESTAMP_NOT_STRICTLY_INCREASING"}
        contradictions.append("TIMESTAMP_NOT_STRICTLY_INCREASING")
    elif times[-1] > now_ms + c.FUTURE_TOLERANCE_MS:
        out["time"] = {"state": "INCOHERENT", "reason": "TIMESTAMP_IN_FUTURE"}
        contradictions.append("TIMESTAMP_IN_FUTURE")
    else:
        out["time"] = {"state": "CERTIFIED", "reason": None}

    # --- value contradictions (B08), checked on every sample
    for s in samples:
        price, bid, ask = decimal(s["price"]), decimal(s["bid"]), decimal(s["ask"])
        if any(v is not None and v <= 0 for v in (price, bid, ask)):
            contradictions.append("NON_POSITIVE_VALUE")
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            if bid >= ask:
                contradictions.append("CROSSED_OR_LOCKED_BOOK")
            elif obs["price_kind"] == "MID_BBO" and price is not None and price != (bid + ask) / 2:
                contradictions.append("MID_PRICE_MISMATCH")
        if obs["price_kind"] == "MID_BBO" and price is not None and (bid is None or ask is None):
            contradictions.append("MID_WITHOUT_BBO")
    out["contradictions"] = sorted(set(contradictions))

    if out["time"]["state"] != "CERTIFIED" or out["contradictions"]:
        reason = out["time"]["reason"] if out["time"]["state"] != "CERTIFIED" else "CONTRADICTORY_VALUES"
        for k in ("continuity", "freshness", "spread", "volatility"):
            m[k] = {"state": "UNKNOWN", "reason": reason}
        m["activity"] = _activity(obs)
        m["l2"] = _l2(obs)
        m["cost"] = _cost(obs)
        return out

    # --- continuity on the declared grid (B03)
    in_window = [s for s in samples if start - step < s["t_ms"] <= end]
    outside = len(samples) - len(in_window)
    covered = []  # (instant, sample) for instants that have a sample with a price
    for g in grid:
        best = None
        for s in in_window:
            if g - step < s["t_ms"] <= g and s["price"] is not None:
                best = s
        if best is not None:
            covered.append((g, best))
    covered_set = {g for g, _ in covered}
    runs, run = [], 0
    for g in grid:
        if g in covered_set:
            if run:
                runs.append(run)
            run = 0
        else:
            run += 1
    if run:
        runs.append(run)
    ratio = D(len(covered)) / D(points)
    if ratio >= D(c.CONTINUITY_GOOD):
        cls = "GOOD"
    elif ratio >= D(c.CONTINUITY_VIABLE):
        cls = "VIABLE"
    elif ratio >= D(c.CONTINUITY_PARTIAL):
        cls = "PARTIAL"
    else:
        cls = "INSUFFICIENT"
    m["continuity"] = {"state": "AVAILABLE", "class": cls, "covered": len(covered), "expected": points,
                       "ratio": _q(ratio, "0.0001"), "gaps": len(runs), "longest_gap": max(runs, default=0),
                       "outside_window": outside, "reason": None}

    # --- freshness (B05)
    last = samples[-1]["t_ms"]
    age = now_ms - last
    fresh = age <= c.FRESHNESS_STEPS * step
    m["freshness"] = {"state": "AVAILABLE", "class": "FRESH" if fresh else "STALE", "age_ms": age,
                      "max_age_ms": c.FRESHNESS_STEPS * step, "reason": None if fresh else "SOURCE_STALE"}

    # --- spread from BBO only (B06)
    spreads = []
    for _, s in covered:
        bid, ask = decimal(s["bid"]), decimal(s["ask"])
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2
            spreads.append((ask - bid) / mid * BPS)
    if not covered or not spreads:
        m["spread"] = {"state": "UNKNOWN", "reason": "BBO_NOT_PROVIDED", "basis": None}
    else:
        bbo_cov = D(len(spreads)) / D(len(covered))
        state = "AVAILABLE" if bbo_cov >= D(c.BBO_COVERAGE_MIN) else "PARTIAL"
        m["spread"] = {"state": state, "basis": "BBO", "median_bps": _q(_median(spreads), "0.001"),
                       "bbo_samples": len(spreads), "bbo_coverage": _q(bbo_cov, "0.0001"),
                       "reason": None if state == "AVAILABLE" else "BBO_COVERAGE_BELOW_MIN"}

    # --- volatility: RMS of returns between consecutive covered instants
    rets = []
    prev = None
    for g, s in covered:
        p = decimal(s["price"])
        if prev is not None and g - prev[0] == step:
            rets.append((p - prev[1]) / prev[1] * BPS)
        prev = (g, p)
    if len(rets) < c.VOL_MIN_RETURNS:
        m["volatility"] = {"state": "UNKNOWN", "reason": "TOO_FEW_CONSECUTIVE_RETURNS",
                           "returns": len(rets), "min_returns": c.VOL_MIN_RETURNS}
    else:
        rms = (sum(r * r for r in rets) / D(len(rets))).sqrt()
        if rms >= D(c.REGIME_VOLATILE_BPS):
            regime = "VOLATILE"
        elif rms >= D(c.REGIME_ACTIVE_BPS):
            regime = "ACTIVE"
        else:
            regime = "CALM"
        m["volatility"] = {"state": "AVAILABLE", "rms_step_bps": _q(rms, "0.001"), "returns": len(rets),
                           "regime": regime, "price_kind": obs["price_kind"], "reason": None}
    m["activity"] = _activity(obs)
    m["l2"] = _l2(obs)
    m["cost"] = _cost(obs)
    return out


def _unknown_reason(obs, key, default):
    """Explicit reason of an absent field (radar-batch ``unknown_reasons``), else the R0 default."""
    return (obs.get("unknown_reasons") or {}).get(key) or default


def _activity(obs):
    a = obs["activity"]
    if a is None:
        return {"state": "UNKNOWN", "reason": _unknown_reason(obs, "activity", "ACTIVITY_NOT_PROVIDED")}
    if a["kind"] not in c.ACTIVITY_KINDS:
        return {"state": "UNKNOWN", "reason": "ACTIVITY_KIND_NOT_SUPPORTED", "kind": a["kind"]}
    if a["value"] is None:
        return {"state": "UNKNOWN", "reason": "ACTIVITY_VALUE_MISSING", "kind": a["kind"]}
    return {"state": "AVAILABLE", "kind": a["kind"], "value": a["value"],
            "evidence_ref": a["evidence_ref"], "reason": None}


def _l2(obs):
    l2 = obs["l2"]
    if l2 is None:
        return {"state": "UNKNOWN", "reason": "L2_NOT_PROVIDED", "status": None, "depth": None}
    if l2["status"] == "VERIFIED" and not l2["evidence_ref"]:
        return {"state": "UNKNOWN", "reason": "L2_CLAIM_WITHOUT_EVIDENCE", "status": None, "depth": None}
    depth = l2["depth_quote_10bps"]
    if depth is None:
        d = {"state": "UNKNOWN", "reason": _unknown_reason(obs, "depth", "DEPTH_NOT_PROVIDED"), "basis": "L2"}
    elif depth["bid"] is None or depth["ask"] is None:
        d = {"state": "PARTIAL", "reason": "DEPTH_ONE_SIDE_MISSING", "basis": "L2",
             "bid_quote_10bps": depth["bid"], "ask_quote_10bps": depth["ask"]}
    else:
        d = {"state": "AVAILABLE", "reason": None, "basis": "L2",
             "bid_quote_10bps": depth["bid"], "ask_quote_10bps": depth["ask"]}
    if l2["status"] == "TECHNICALLY_COMPATIBLE" and d["state"] != "UNKNOWN":
        d = {**d, "state": "PARTIAL", "reason": "DEPTH_FROM_UNVERIFIED_L2"}
    if l2["status"] == "VERIFIED_TOP_N":
        # Operator D3: only the first depth_levels levels are attested, on valid instants
        # only. Never presented as a verified book; the scope stays attached.
        return {"state": "PARTIAL", "status": l2["status"], "evidence_ref": l2["evidence_ref"],
                "depth_levels": l2["depth_levels"], "scope": l2["scope"], "depth": d,
                "reason": "L2_VERIFIED_TOP_N_ONLY"}
    return {"state": "AVAILABLE" if l2["status"] == "VERIFIED" else "PARTIAL",
            "status": l2["status"], "evidence_ref": l2["evidence_ref"],
            "depth_levels": l2["depth_levels"], "depth": d,
            "reason": None if l2["status"] == "VERIFIED" else "L2_TO_QUALIFY_AFTER_AUTHORIZATION"}


def _cost(obs):
    cost = obs["cost"]
    if cost is None:
        return {"state": "UNKNOWN", "reason": _unknown_reason(obs, "cost", "COST_NOT_PROVIDED"), "basis": None}
    fields = ("network_kib_s", "cpu_pct", "memory_mib", "storage_mib_h", "connections")
    missing = [k for k in fields if cost[k] is None]
    return {"state": "AVAILABLE" if not missing else "PARTIAL", "basis": cost["basis"],
            "provenance": cost["provenance"], **{k: cost[k] for k in fields},
            "rate_limit_note": cost["rate_limit_note"], "missing": missing,
            "reason": None if not missing else "COST_FIELDS_MISSING"}
