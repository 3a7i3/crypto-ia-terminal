"""R0-C — scientific selection: six criteria, admissibility, ranking, diversity.

Stage 1 decides, per mission, ADMISSIBLE / A_QUALIFIER / NON_ADMISSIBLE /
UNKNOWN with every reason. Stage 2 ranks only ADMISSIBLE markets with the
versioned integer weights of ``contract.WEIGHTS``. A component whose input is
unknown scores nothing and its weight is not redistributed: an unknown can
never improve a score. Ties are broken by ``market_id``; the input order has
no effect.
"""
from __future__ import annotations

from decimal import Decimal

from . import contract as c

D = Decimal


def criteria(market: dict, seen: dict) -> dict:
    """The six criteria of one market from its light-surveillance measures."""
    if not seen["present"]:
        r = seen["reason"]
        unknown = {"state": c.CRIT_UNKNOWN, "reason": r}
        return {"l2_quality": {**unknown, "proof": "UNKNOWN"},
                "continuity": {**unknown, "time": "UNKNOWN"},
                "spread_depth": {**unknown, "spread": dict(unknown), "depth": dict(unknown)},
                "activity_volatility": {**unknown, "activity": dict(unknown), "volatility": dict(unknown)},
                "collection_cost": {**unknown, "basis": None},
                "diversity": {**unknown, "regime": None}}
    m = seen["measures"]
    l2 = m["l2"]
    if l2["state"] == c.CRIT_UNKNOWN:
        crit_l2 = {"state": c.CRIT_UNKNOWN, "reason": l2["reason"], "proof": "UNKNOWN"}
    else:
        crit_l2 = {"state": l2["state"], "reason": l2["reason"],
                   "proof": "PROVEN" if l2["status"] == "VERIFIED" else "TO_QUALIFY",
                   "status": l2["status"], "evidence_ref": l2["evidence_ref"],
                   "depth_levels": l2["depth_levels"]}

    time = seen["time"]
    if time["state"] == "INCOHERENT" or seen["contradictions"]:
        crit_cont = {"state": c.INVALID, "reason": time["reason"] if time["state"] == "INCOHERENT"
                     else "CONTRADICTORY_VALUES", "time": time["state"]}
    elif time["state"] != "CERTIFIED":
        crit_cont = {"state": c.CRIT_UNKNOWN, "reason": time["reason"], "time": time["state"]}
    else:
        cont, fr = m["continuity"], m["freshness"]
        crit_cont = {"state": c.AVAILABLE if fr["class"] == "FRESH" else c.PARTIAL,
                     "reason": fr["reason"], "time": "CERTIFIED", "class": cont["class"],
                     "ratio": cont["ratio"], "covered": cont["covered"], "expected": cont["expected"],
                     "gaps": cont["gaps"], "longest_gap": cont["longest_gap"],
                     "freshness": fr["class"], "age_ms": fr["age_ms"]}

    sp = m["spread"]
    depth = l2.get("depth") or {"state": c.CRIT_UNKNOWN, "reason": l2["reason"], "basis": None}
    parts = [sp["state"], depth["state"]]
    if crit_cont["state"] == c.INVALID:
        sd_state = c.INVALID
    elif parts == [c.AVAILABLE, c.AVAILABLE]:
        sd_state = c.AVAILABLE
    elif all(p == c.CRIT_UNKNOWN for p in parts):
        sd_state = c.CRIT_UNKNOWN
    else:
        sd_state = c.PARTIAL
    crit_sd = {"state": sd_state, "spread": sp, "depth": depth,
               "reason": None if sd_state == c.AVAILABLE else (sp["reason"] or depth["reason"])}

    act, vol = m["activity"], m["volatility"]
    av = [act["state"], vol["state"]]
    av_state = (c.INVALID if crit_cont["state"] == c.INVALID else
                c.AVAILABLE if av == [c.AVAILABLE, c.AVAILABLE] else
                c.CRIT_UNKNOWN if av == [c.CRIT_UNKNOWN, c.CRIT_UNKNOWN] else c.PARTIAL)
    crit_av = {"state": av_state, "activity": act, "volatility": vol,
               "reason": None if av_state == c.AVAILABLE else (act["reason"] or vol["reason"])}

    cost = m["cost"]
    crit_cost = {"state": cost["state"], **{k: v for k, v in cost.items() if k != "state"}}

    regime = vol.get("regime")
    crit_div = ({"state": c.AVAILABLE, "regime": regime, "reason": None} if regime else
                {"state": c.CRIT_UNKNOWN, "regime": None, "reason": "REGIME_UNKNOWN"})
    return {"l2_quality": crit_l2, "continuity": crit_cont, "spread_depth": crit_sd,
            "activity_volatility": crit_av, "collection_cost": crit_cost, "diversity": crit_div}


def admissibility(market: dict, seen: dict, crit: dict, mission: str, extra: list) -> dict:
    """Stage 1. ``extra``: (decision, code) pairs found by the engine (identity, budget...)."""
    rules = c.MISSIONS[mission]
    reasons = list(extra)
    cat = market["catalogue"]
    if cat["lifecycle"] == c.RETIRED:
        reasons.append((c.NON_ADMISSIBLE, "MARKET_RETIRED_FROM_CATALOGUE"))
    elif cat["lifecycle"] == c.SOURCE_NOT_CURRENT:
        reasons.append((c.UNKNOWN, "SOURCE_CATALOGUE_NOT_CURRENT"))
    if market["authorized"] is None:
        reasons.append((c.UNKNOWN, market["authorization_reason"]))
    elif market["authorized"] is False:
        reasons.append((c.NON_ADMISSIBLE, market["authorization_reason"]))
    if cat["exclusion"] is not None and market["base"] is not None:
        reasons.append((c.NON_ADMISSIBLE, "CATALOGUE_" + cat["exclusion"]))
    if cat["lifecycle"] == c.LISTED and not cat["metadata_current"]:
        reasons.append((c.TO_QUALIFY, "CATALOGUE_METADATA_" + (cat["metadata_reason"] or "NOT_CURRENT")))
    access = market["source_access"]
    if access == "UNAVAILABLE":
        reasons.append((c.NON_ADMISSIBLE, "SOURCE_UNAVAILABLE"))
    elif access == "DEGRADED":
        reasons.append((c.TO_QUALIFY, "SOURCE_DEGRADED"))
    elif access == "UNKNOWN":
        reasons.append((c.UNKNOWN, "SOURCE_ACCESS_UNKNOWN"))

    if not seen["present"]:
        reasons.append((c.UNKNOWN, seen["reason"]))
    else:
        time = seen["time"]
        if time["state"] == "INCOHERENT":
            reasons.append((c.NON_ADMISSIBLE, time["reason"]))
        elif time["state"] != "CERTIFIED":
            reasons.append((c.UNKNOWN, "TIME_UNCERTIFIED_" + time["reason"]))
        for code in seen["contradictions"]:
            if code not in (time.get("reason"),):
                reasons.append((c.NON_ADMISSIBLE, "CONTRADICTORY_VALUES_" + code))
        cont = crit["continuity"]
        if cont.get("class") == "INSUFFICIENT":
            reasons.append((c.NON_ADMISSIBLE, "CONTINUITY_INSUFFICIENT"))
        elif cont.get("class") == "PARTIAL":
            reasons.append((c.TO_QUALIFY, "CONTINUITY_PARTIAL"))
        if cont.get("freshness") == "STALE":
            reasons.append((c.TO_QUALIFY, "SOURCE_STALE"))
        if cont["state"] in (c.AVAILABLE, c.PARTIAL):
            sp = crit["spread_depth"]["spread"]
            if rules["needs_bbo"] and sp["state"] == c.CRIT_UNKNOWN:
                reasons.append((c.UNKNOWN, "BBO_NOT_PROVIDED"))
            elif rules["needs_bbo"] and sp["state"] == c.PARTIAL:
                reasons.append((c.TO_QUALIFY, "BBO_COVERAGE_PARTIAL"))
            if rules["needs_l2_verified"]:
                proof = crit["l2_quality"].get("proof")
                if proof == "TO_QUALIFY":
                    reasons.append((c.TO_QUALIFY, "L2_TO_QUALIFY_AFTER_AUTHORIZATION"))
                elif proof != "PROVEN":
                    reasons.append((c.UNKNOWN, "L2_NOT_PROVEN"))
                elif crit["spread_depth"]["depth"]["state"] != c.AVAILABLE:
                    reasons.append((c.TO_QUALIFY, "L2_DEPTH_" + str(crit["spread_depth"]["depth"]["reason"])))

    uniq = sorted(set(reasons), key=lambda r: (-c.DECISION_SEVERITY[r[0]], r[1]))
    decision = uniq[0][0] if uniq else c.ADMISSIBLE
    return {"mission": mission, "decision": decision,
            "reasons": [{"decision": d, "code": code} for d, code in uniq[:c.MAX_REASON_CODES]],
            "reasons_truncated": len(uniq) > c.MAX_REASON_CODES}


def _points(value: Decimal, table, floor) -> int:
    for bound, pts in table:
        if value <= D(bound):
            return pts
    return floor


def score(crit: dict, decision: str) -> dict | None:
    """Stage 2 score, only for ADMISSIBLE markets. Unknown components score nothing."""
    if decision != c.ADMISSIBLE:
        return None
    comps, missing = {}, []
    cont = crit["continuity"]
    ratio = D(cont["ratio"])
    comps["continuity"] = next((p for b, p in c.CONTINUITY_POINTS if ratio >= D(b)), 0)
    sp = crit["spread_depth"]["spread"]
    if sp["state"] == c.AVAILABLE:
        comps["spread"] = _points(D(sp["median_bps"]), c.SPREAD_POINTS_BPS, c.SPREAD_FLOOR_POINTS)
    else:
        missing.append("spread")
    act = crit["activity_volatility"]["activity"]
    if act["state"] == c.AVAILABLE:
        comps["activity"] = next((p for b, p in c.ACTIVITY_POINTS if act["value"] >= b), 0)
    else:
        missing.append("activity")
    l2 = crit["l2_quality"]
    if l2["state"] != c.CRIT_UNKNOWN:
        comps["l2"] = c.L2_POINTS[l2["status"]]
    else:
        missing.append("l2")
    cost = crit["collection_cost"]
    if cost["state"] != c.CRIT_UNKNOWN and cost.get("network_kib_s") is not None:
        comps["cost"] = _points(D(cost["network_kib_s"]), c.COST_POINTS_KIB_S, c.COST_FLOOR_POINTS)
    else:
        missing.append("cost")
    total = sum(D(c.WEIGHTS[k]) * D(v) for k, v in comps.items()) / D(100)
    return {"value": str(total.quantize(D("0.01"))), "components": dict(sorted(comps.items())),
            "weights": dict(c.WEIGHTS), "missing": sorted(missing),
            "quality": "COMPLETE" if not missing else "INCOMPLETE",
            "max_reachable": str((D(100) - sum(D(c.WEIGHTS[k]) for k in missing)).quantize(D("0.01")))}


def _limits(entry: dict) -> list:
    crit = entry["criteria"]
    out = ["Données SYNTHETIC : aucune valeur LIVE"]
    if crit["l2_quality"].get("proof") != "PROVEN":
        out.append("Intégrité L2 non prouvée")
    if crit["spread_depth"]["depth"]["state"] != c.AVAILABLE:
        out.append("Profondeur non mesurée")
    cost = crit["collection_cost"]
    if cost.get("basis") == "ESTIMATED":
        out.append("Coût estimé, non mesuré")
    elif cost["state"] == c.CRIT_UNKNOWN:
        out.append("Coût inconnu")
    vol = crit["activity_volatility"]["volatility"]
    if vol["state"] == c.AVAILABLE:
        out.append(f"Régime sur une seule fenêtre ({vol['returns']} retours)")
    return out


def _candidate(entry: dict, rank: int, rule: str) -> dict:
    crit = entry["criteria"]
    s = entry["score"]
    sp = crit["spread_depth"]["spread"]
    regime = crit["diversity"]["regime"]
    why = {"REGIME_SLOT": f"Meilleur score du régime {regime}",
           "BASE_DIVERSITY": "Meilleur score restant avec un autre actif de base",
           "SCORE": "Meilleur score restant"}[rule]
    detail = (f"score {s['value']}/100 ; continuité {crit['continuity']['class']} "
              f"({crit['continuity']['ratio']})")
    if sp["state"] == c.AVAILABLE:
        detail += f" ; spread médian {sp['median_bps']} bps (BBO)"
    cost = crit["collection_cost"]
    return {
        "rank": rank, "market_id": entry["market_id"], "venue": entry["venue"],
        "market_type": entry["market_type"], "contract_type": entry["contract_type"],
        "base": entry["base"], "quote": entry["quote"], "native_symbol": entry["native_symbol"],
        "regime": regime, "selection_rule": rule, "reason": f"{why} : {detail}",
        "score": s["value"], "quality": s["quality"],
        "criteria_available": sorted(k for k, v in crit.items() if v["state"] == c.AVAILABLE),
        "criteria_missing": sorted(k for k, v in crit.items() if v["state"] != c.AVAILABLE),
        "cost": {"state": cost["state"], "basis": cost.get("basis"), "provenance": cost.get("provenance"),
                 "network_kib_s": cost.get("network_kib_s"), "storage_mib_h": cost.get("storage_mib_h"),
                 "connections": cost.get("connections")},
        "limits": _limits(entry),
        "status": "PROPOSED_NOT_AUTHORIZED",
    }


def select_candidates(entries: list, excluded: set, reference_id: str) -> tuple:
    """Up to three candidates with diversity of regimes. Deterministic and order-free."""
    pool = sorted((e for e in entries if e["score"] is not None and e["market_id"] not in excluded
                   and e["market_id"] != reference_id),
                  key=lambda e: (-D(e["score"]["value"]), e["market_id"]))
    chosen, rules = [], []
    for regime in c.DIVERSITY_ORDER:
        for e in pool:
            if e not in chosen and e["criteria"]["diversity"]["regime"] == regime:
                chosen.append(e)
                rules.append("REGIME_SLOT")
                break
        if len(chosen) == c.MAX_CANDIDATES:
            break
    bases = {e["base"] for e in chosen}
    for e in pool:
        if len(chosen) == c.MAX_CANDIDATES:
            break
        if e not in chosen and e["base"] not in bases:
            chosen.append(e)
            rules.append("BASE_DIVERSITY")
            bases.add(e["base"])
    for e in pool:
        if len(chosen) == c.MAX_CANDIDATES:
            break
        if e not in chosen:
            chosen.append(e)
            rules.append("SCORE")
    # Present by score order; the rule that admitted each one is kept.
    pairs = sorted(zip(chosen, rules), key=lambda p: (-D(p[0]["score"]["value"]), p[0]["market_id"]))
    candidates = [_candidate(e, i + 1, r) for i, (e, r) in enumerate(pairs)]
    if candidates:
        return candidates, None
    admissible = [e for e in entries if e["score"] is not None]
    if not admissible:
        return [], "NO_ADMISSIBLE_MARKET_FOR_MISSION"
    return [], "ADMISSIBLE_MARKETS_ALL_EXCLUDED_OR_REFERENCE"
