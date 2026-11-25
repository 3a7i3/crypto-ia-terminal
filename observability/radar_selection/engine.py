"""One Radar cycle: universe -> light surveillance -> selection -> evaluation document.

Pure function of (fixture bytes, preferences, mission, budgets). No clock,
network, file, PPL, PAPER, FIN, Advisor or Risk access. The evaluation is a
compact presentation/research artifact: it authorises nothing, and a proposal
creates no deep-observation job.
"""
from __future__ import annotations

from . import contract as c
from .fixture import RadarRefusal, canonical, load_fixture, sha256_hex
from .manual import empty_preferences, preferences_digest
from .selection import admissibility, criteria, score, select_candidates
from .surveillance import observe
from .universe import build_universe


def _observation_index(observations: list) -> dict:
    index: dict = {}
    for o in observations:
        index.setdefault((o["venue"], o["market_type"], o["native_symbol"]), []).append(o)
    return index


def evaluate(raw: bytes, prefs: dict | None = None, mission: str = c.DEFAULT_MISSION,
             budgets: c.Budgets = c.TEST_BUDGETS) -> dict:
    """One cycle over a radar-fixture/1.0.0 document (SYNTHETIC, catalogues embedded)."""
    if mission not in c.MISSIONS:
        raise RadarRefusal("UNKNOWN_MISSION:" + str(mission)[:40])
    loaded = load_fixture(raw, budgets)
    doc = loaded["doc"]
    dataset = {"id": doc["dataset_id"], "schema": c.FIXTURE_SCHEMA, "sha256": loaded["sha256"],
               "bytes": loaded["bytes"], "evidence_kind": doc["evidence_kind"],
               "admission": c.ADMISSION, "description": doc["description"]}
    return _cycle(doc, build_universe(doc), dataset, None, prefs, mission, budgets)


def evaluate_batch(raw: bytes, blobs: dict, prefs: dict | None = None, mission: str = c.DEFAULT_MISSION,
                   budgets: c.Budgets = c.TEST_BUDGETS) -> dict:
    """One cycle over a radar-batch/1.0.0 document and the bytes of its references (R1-B).

    ``blobs`` maps each reference to the bytes the caller read (see ``refs``). Every
    fingerprint is checked here; nothing is read, fetched or re-serialised.
    """
    from .batch import load_batch, verify_batch
    if mission not in c.MISSIONS:
        raise RadarRefusal("UNKNOWN_MISSION:" + str(mission)[:40])
    loaded = load_batch(raw, budgets)
    doc = loaded["doc"]
    verified = verify_batch(doc, blobs)
    universe = build_universe(doc, verified["documents"], "SCANNER_RAW_CATALOGUE")
    dataset = {"id": doc["dataset_id"], "schema": c.BATCH_SCHEMA, "sha256": loaded["sha256"],
               "bytes": loaded["bytes"], "evidence_kind": doc["evidence_kind"],
               "admission": c.ADMISSION, "description": doc["description"],
               "adapter_version": doc["adapter_version"]}
    work = {**doc, "observations": verified["observations"]}
    return _cycle(work, universe, dataset, verified["inputs"], prefs, mission, budgets)


def _cycle(doc: dict, universe: dict, dataset: dict, inputs: dict | None, prefs: dict | None,
           mission: str, budgets: c.Budgets) -> dict:
    prefs = prefs or empty_preferences()
    now = doc["evaluation_time_ms"]
    obs_index = _observation_index(doc["observations"])
    # radar-batch: observations refused at verification stay visible as UNKNOWN with their code.
    refused = {(r["venue"], r["market_type"], r["native_symbol"]): r["reason"]
               for r in (inputs or {}).get("refused_observations", [])}
    used_keys = set()
    excluded = set(prefs["excluded"])

    entries = []
    evaluated = 0
    for market in universe["markets"]:
        key = (market["venue"], market["market_type"], market["native_symbol"])
        found = obs_index.get(key, []) if market["catalogue"]["lifecycle"] == c.LISTED else []
        if found:
            used_keys.add(key)
        extra = []
        obs = None
        if market["authorized"] is not True:
            seen = observe(None, now)
            seen["reason"] = "NOT_EVALUATED_OUTSIDE_AUTHORIZED_UNIVERSE"
        elif evaluated >= budgets.max_instruments_per_cycle:
            seen = observe(None, now)
            seen["reason"] = "NOT_EVALUATED_BUDGET_INSTRUMENTS_PER_CYCLE"
            extra.append((c.UNKNOWN, "BUDGET_NOT_EVALUATED"))
        else:
            evaluated += 1
            if len(found) > 1:
                extra.append((c.NON_ADMISSIBLE, "DUPLICATE_OBSERVATION"))
            obs = found[0] if found else None
            if obs is not None:
                for field, value in (("declared_base", market["base"]), ("declared_quote", market["quote"])):
                    if obs[field] is not None and obs[field] != value:
                        extra.append((c.NON_ADMISSIBLE, "IDENTITY_CONFLICT_" + field.upper()))
            seen = observe(obs, now)
            if obs is None and key in refused:
                seen["reason"] = refused[key]
        crit = criteria(market, seen)
        adm = admissibility(market, seen, crit, mission, extra)
        entry = {
            **{k: market[k] for k in ("market_id", "venue", "market_type", "contract_type", "base",
                                      "quote", "native_symbol", "settlement_asset", "catalogue",
                                      "change", "previous")},
            "lifecycle": {
                "discovered": market["discovered"],
                "authorized": market["authorized"], "authorization_reason": market["authorization_reason"],
                "source_access": market["source_access"], "source_access_reason": market["source_access_reason"],
                "recent_data": _recent(seen),
                "scientific": adm["decision"],
            },
            "observation": {"present": seen["present"], "reason": seen["reason"],
                            "evidence_kind": doc["evidence_kind"],
                            "source_id": obs.get("source_id") if obs else None,
                            "evidence_ref": seen.get("evidence_ref"), "price_kind": seen.get("price_kind"),
                            "window": seen.get("window"), "sample_count": seen.get("sample_count"),
                            "time": seen["time"], "contradictions": seen["contradictions"]},
            "criteria": crit,
            "admissibility": adm,
            "manual": {k: market["market_id"] in prefs[k] for k in ("selected", "pinned", "excluded")},
        }
        entry["score"] = score(crit, adm["decision"])
        entries.append(entry)

    orphans = sorted(
        ({"venue": k[0], "market_type": k[1], "native_symbol": k[2],
          "evidence_refs": sorted(o["evidence_ref"] for o in v), "reason": "NO_SUCH_MARKET_IN_UNIVERSE"}
         for k, v in obs_index.items() if k not in used_keys),
        key=lambda o: (o["venue"], o["market_type"], o["native_symbol"]))

    by_id = {e["market_id"]: e for e in entries}
    candidates, empty_reason = select_candidates(entries, excluded)
    manual = {k: [_manual_item(mid, by_id.get(mid)) for mid in prefs[k]] for k in ("selected", "pinned", "excluded")}

    counts = {
        "discovered": sum(e["lifecycle"]["discovered"] for e in entries),
        "listed": sum(e["catalogue"]["lifecycle"] == c.LISTED for e in entries),
        "retired_or_source_not_current": sum(e["catalogue"]["lifecycle"] != c.LISTED for e in entries),
        "authorized": sum(e["lifecycle"]["authorized"] is True for e in entries),
        "not_authorized": sum(e["lifecycle"]["authorized"] is False for e in entries),
        "identity_unknown": sum(e["lifecycle"]["authorized"] is None for e in entries),
        "evaluated": evaluated,
        **{d.lower(): sum(e["admissibility"]["decision"] == d for e in entries) for d in c.DECISIONS},
        "scored": sum(e["score"] is not None for e in entries),
        "manually_excluded": sum(e["manual"]["excluded"] for e in entries),
        "candidates": len(candidates),
        "orphan_observations": len(orphans),
    }
    out = {
        "schema_version": c.EVALUATION_SCHEMA,
        "rules_version": c.RULES_VERSION,
        "ranking_version": c.RANKING_VERSION,
        "mode": {**c.MODE, "evidence": doc["evidence_kind"]},
        "authority": dict(c.AUTHORITY),
        "dataset": dataset,
        "inputs": inputs,
        "mission": {"id": mission, **c.MISSIONS[mission]},
        "evaluation_time_ms": now,
        "preferences_sha256": preferences_digest(prefs),
        "policy": doc["policy"],
        "sources": universe["sources"],
        "counts": counts,
        "candidates": candidates,
        "candidates_empty_reason": empty_reason,
        "manual": manual,
        "orphan_observations": orphans,
        "markets": entries,
        "budgets": {"profile": budgets.profile, "limits": budgets.as_dict(),
                    "production": {"status": c.PRODUCTION_BUDGETS_STATUS, "values": c.PRODUCTION_BUDGETS},
                    "usage": {"input_bytes": dataset["bytes"], "instruments_listed": len(entries),
                              "instruments_evaluated": evaluated,
                              "observations": len(doc["observations"])}},
        "deep_observation_jobs": [],
    }
    out["evaluation_sha256"] = sha256_hex(canonical(out))
    size = len(canonical(out))
    if size > budgets.max_output_bytes:
        raise RadarRefusal(f"OUTPUT_TOO_LARGE:{size}>{budgets.max_output_bytes}")
    return out


def _recent(seen: dict) -> str:
    if not seen["present"]:
        return "ABSENT" if seen["reason"] == "NO_OBSERVATION" else "UNKNOWN"
    fr = seen["measures"].get("freshness", {})
    return fr.get("class", "UNKNOWN") if fr.get("state") == "AVAILABLE" else "UNKNOWN"


def _manual_item(mid: str, entry: dict | None) -> dict:
    if entry is None:
        return {"market_id": mid, "present": False, "decision": c.UNKNOWN,
                "presented_as_admissible": False, "note": "NOT_IN_UNIVERSE"}
    d = entry["admissibility"]["decision"]
    return {"market_id": mid, "present": True, "decision": d,
            "presented_as_admissible": d == c.ADMISSIBLE,
            "note": "MANUAL_CHOICE_DOES_NOT_AUTHORIZE_COLLECTION"}
