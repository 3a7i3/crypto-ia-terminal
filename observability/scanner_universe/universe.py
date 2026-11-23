"""Scanner V1 common universe: pure intersection of four market catalogues.

    Univers Scanner = MEXC Spot négociable ∩ MEXC Perpétuel négociable
                    ∩ Kraken Spot négociable ∩ Kraken Perpétuel négociable

Key = canonical ``BASE/QUOTE``. ``USD``, ``USDT`` and ``USDC`` stay distinct;
only the explicit Kraken aliases of ``catalogues.KRAKEN_ASSET_ALIASES`` are
applied. No network, file or clock access: ``now_ms`` is always an argument.

Statuses:
- ``VERIFIED``        four COMPLETE and fresh catalogues, at least one pair;
- ``VERIFIED_EMPTY``  four COMPLETE and fresh catalogues, no common pair;
- ``UNVERIFIABLE``    at least one catalogue is unavailable, incomplete,
                      stale or from the future; ``pairs`` is then always empty
                      and a previous verified list may only appear as a dated
                      ``reference`` that is not current.
"""
from __future__ import annotations

import hashlib
import json

from .catalogues import COMPLETE, MARKETS, MarketCatalogue

SCHEMA_VERSION = "scanner-universe/1.0.0"
# Producer cadence: one run every 900 s (same as the D1-RC1 Spot collector,
# which reloads MEXC exchangeInfo at each 900 s campaign). A catalogue stays
# current for two cadences (one missed run tolerated) plus 300 s for timer
# jitter and the bounded request budget (5 requests x 20 s timeout).
CADENCE_MS = 900_000
FRESHNESS_MAX_AGE_MS = 2 * CADENCE_MS + 300_000  # 2 100 000 ms = 35 min
# Allowed clock skew between the producer's reception time and the evaluator.
FUTURE_TOLERANCE_MS = 5_000
NEAR_MISS_MIN_MARKETS = 3
MAX_EXCLUSIONS = 500


def source_status(catalogue: MarketCatalogue, now_ms: int) -> dict:
    """Current qualification of one market catalogue at ``now_ms``."""
    base = {"market": catalogue.market, "catalogue_state": catalogue.state,
            "collected_ms": catalogue.collected_ms, "age_ms": None}
    if catalogue.state != COMPLETE:
        return {**base, "current": False, "reason": f"{catalogue.state}:{catalogue.reason}"}
    age = now_ms - catalogue.collected_ms
    base["age_ms"] = age
    if age < -FUTURE_TOLERANCE_MS:
        return {**base, "current": False, "reason": "COLLECTED_IN_FUTURE"}
    if age > FRESHNESS_MAX_AGE_MS:
        return {**base, "current": False, "reason": "STALE"}
    return {**base, "current": True, "reason": None}


def _index(catalogue: MarketCatalogue):
    """key -> admissible record (DUPLICATE_KEY already removed upstream), key -> all records."""
    admissible, everything = {}, {}
    for record in catalogue.records:
        if record.key is None:
            continue
        everything.setdefault(record.key, []).append(record)
        if record.exclusion is None:
            admissible[record.key] = record
    return admissible, everything


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def compute_universe(catalogues: dict, now_ms: int, previous: dict | None = None) -> dict:
    """Return a ``scanner-universe/1.0.0`` document. Pure and deterministic."""
    if set(catalogues) != set(MARKETS):
        raise ValueError("the four market catalogues are required")
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError("now_ms must be a positive integer")
    statuses = [source_status(catalogues[m], now_ms) for m in MARKETS]
    certifiable = all(s["current"] for s in statuses)

    indexes = {m: _index(catalogues[m]) for m in MARKETS}
    available = [m for m in MARKETS if catalogues[m].state == COMPLETE]
    common = None
    for m in available:
        keys = set(indexes[m][0])
        common = keys if common is None else common & keys
    candidate_pairs = []
    if certifiable:
        for key in sorted(common or ()):
            base, quote = key.split("/")
            candidate_pairs.append({
                "key": key, "base": base, "quote": quote,
                "proofs": {m: indexes[m][0][key].as_dict() for m in MARKETS},
            })

    # Near misses: keys stated by at least three markets (admissible or not),
    # each with the reason of every market that does not admit it.
    exclusions = []
    if available:
        all_keys = set().union(*(indexes[m][1] for m in available))
        for key in sorted(all_keys):
            present = [m for m in MARKETS if m in available and key in indexes[m][1]]
            if len(present) < NEAR_MISS_MIN_MARKETS and len(present) < len(available):
                continue
            if certifiable and key in (common or ()):
                continue
            reasons = {}
            for m in MARKETS:
                if m not in available:
                    reasons[m] = "SOURCE_" + catalogues[m].state
                elif key in indexes[m][0]:
                    reasons[m] = None
                elif key in indexes[m][1]:
                    reasons[m] = indexes[m][1][key][0].exclusion
                else:
                    reasons[m] = "ABSENT"
            if all(v is None for v in reasons.values()):
                continue
            natives = {m: [r.native_symbol for r in indexes[m][1].get(key, [])] for m in available}
            exclusions.append({"key": key, "reasons": reasons, "native_symbols": natives})
    truncated = len(exclusions) > MAX_EXCLUSIONS
    exclusions = exclusions[:MAX_EXCLUSIONS]

    sources = [{**catalogues[m].summary(), **{k: v for k, v in s.items() if k != "market"}}
               for m, s in zip(MARKETS, statuses)]
    if certifiable:
        status = "VERIFIED" if candidate_pairs else "VERIFIED_EMPTY"
        blocking = []
    else:
        status = "UNVERIFIABLE"
        blocking = [{"market": s["market"], "reason": s["reason"]} for s in statuses if not s["current"]]
    reference = None
    if not certifiable and previous and previous.get("status") in ("VERIFIED", "VERIFIED_EMPTY"):
        reference = {
            "universe_sha256": previous.get("universe_sha256"),
            "status": previous["status"],
            "computed_ms": previous.get("computed_ms"),
            "keys": [p["key"] for p in previous.get("pairs", [])],
            "current": False,
        }
    elif not certifiable and previous and previous.get("reference"):
        reference = previous["reference"]
    universe_sha = _digest({"status": status, "pairs": candidate_pairs,
                            "sources": [s["raw_sha256"] for s in sources]})
    return {
        "schema_version": SCHEMA_VERSION,
        "product": "ScannerCommonUniverse",
        "authority": "OBSERVATIONAL_TELEMETRY",
        "execution_authority": False,
        "rule": "MEXC_SPOT ∩ MEXC_PERPETUAL ∩ KRAKEN_SPOT ∩ KRAKEN_PERPETUAL on BASE/QUOTE",
        "freshness_max_age_ms": FRESHNESS_MAX_AGE_MS,
        "cadence_ms": CADENCE_MS,
        "computed_ms": now_ms,
        "status": status,
        "blocking_sources": blocking,
        "sources": sources,
        "pairs": candidate_pairs,
        "pair_count": len(candidate_pairs),
        "exclusions": exclusions,
        "exclusions_truncated": truncated,
        "reference": reference,
        "universe_sha256": universe_sha,
    }


def requalify(doc: dict, now_ms: int) -> dict:
    """Serving-time freshness: a published universe loses its current status
    as soon as one source exceeds the freshness bound. Pairs are never added,
    only withdrawn into a dated, non-current ``reference``."""
    stale = []
    sources = []
    for source in doc["sources"]:
        current = bool(source.get("current"))
        reason = source.get("reason")
        age = None
        if source.get("collected_ms") is not None:
            age = now_ms - source["collected_ms"]
            if current and age > FRESHNESS_MAX_AGE_MS:
                current, reason = False, "STALE"
            elif current and age < -FUTURE_TOLERANCE_MS:
                current, reason = False, "COLLECTED_IN_FUTURE"
        if not current:
            stale.append({"market": source["market"], "reason": reason})
        sources.append({**source, "age_ms": age, "current": current, "reason": reason})
    out = {**doc, "sources": sources, "served_ms": now_ms}
    if doc["status"] in ("VERIFIED", "VERIFIED_EMPTY") and stale:
        out.update(
            status="UNVERIFIABLE", blocking_sources=stale, pairs=[], pair_count=0,
            reference={"universe_sha256": doc["universe_sha256"], "status": doc["status"],
                       "computed_ms": doc["computed_ms"], "keys": [p["key"] for p in doc["pairs"]],
                       "current": False},
        )
    return out
