"""R0-A — authorised universe: discovery and identity of every market.

Discovery reuses the Scanner V1 parsers of the four official public catalogues
(``observability.scanner_universe.catalogues.parse_all``) and their freshness
rule (``scanner_universe.universe.source_status``). Nothing here reads the
network: the catalogue bytes come from the fixture.

One market = venue + market type + contract + base + quote. Kraken BTC/USDT
Spot and MEXC BTC/USDT Spot are two markets; BTC/USD and BTC/USDT are never
merged; Spot and Perpetual stay distinct.
"""
from __future__ import annotations

from observability.scanner_universe.catalogues import COMPLETE, MARKET_LABELS, parse_all
from observability.scanner_universe.universe import asset_class, source_status

from . import contract as c
from .fixture import catalogue_documents


def _type_code(contract_type: str) -> str:
    return c.TYPE_CODES.get(contract_type, "unknown-contract")


def base_market_id(venue: str, contract_type: str, base: str | None, quote: str | None,
                   native_symbol: str) -> str:
    code = _type_code(contract_type)
    if base is None or quote is None:
        return f"{venue}:{code}:?{native_symbol}"
    return f"{venue}:{code}:{base}/{quote}"


def _authorize(policy: dict, venue: str, market_type: str, base, quote, market_id: str):
    if base is None or quote is None:
        return None, "IDENTITY_INSUFFICIENT"
    if venue not in policy["venues"]:
        return False, "VENUE_NOT_AUTHORIZED"
    if market_type not in policy["market_types"]:
        return False, "MARKET_TYPE_NOT_AUTHORIZED"
    if quote not in policy["quotes"]:
        return False, "QUOTE_NOT_AUTHORIZED"
    if asset_class(base) not in policy["asset_classes"]:
        return False, "ASSET_CLASS_NOT_AUTHORIZED"
    if market_id in policy["deny"]:
        return False, "DENIED_BY_POLICY"
    return True, None


def build_universe(doc: dict, documents: dict | None = None,
                   provenance: str = "SYNTHETIC_FIXTURE_CATALOGUE") -> dict:
    """Return {"markets": [...], "sources": [...]} sorted by market_id. Pure.

    ``documents`` is the ``parse_all`` input. A radar-fixture builds it from its
    embedded bodies; a radar-batch passes the original catalogue bytes, already
    checked against their SHA-256 (R1-B, operator D1), so nothing is re-serialised.
    """
    now = doc["evaluation_time_ms"]
    catalogues = parse_all(catalogue_documents(doc) if documents is None else documents)
    sources = []
    for market in sorted(catalogues):
        cat = catalogues[market]
        status = source_status(cat, now)
        declared = doc["source_access"].get(market)
        access = declared["state"] if declared else "UNKNOWN"
        sources.append({
            "market": market, "catalogue_state": cat.state, "catalogue_reason": cat.reason,
            "collected_ms": cat.collected_ms, "metadata_current": status["current"],
            "metadata_reason": status["reason"], "raw_sha256": dict(sorted(cat.raw_sha256.items())),
            "instruments": len(cat.records),
            "access": access, "access_reason": declared["reason"] if declared else "ACCESS_NOT_DECLARED",
        })
    by_source = {s["market"]: s for s in sources}

    rows = []
    for market in sorted(catalogues):
        venue, market_type = MARKET_LABELS[market]
        for r in catalogues[market].records:
            rows.append({
                "base_id": base_market_id(venue, r.contract_type, r.base, r.quote, r.native_symbol),
                "venue": venue, "market_type": market_type, "source_market": market,
                "base": r.base, "quote": r.quote, "native_symbol": r.native_symbol,
                "native_base": r.native_base, "native_quote": r.native_quote,
                "contract_type": r.contract_type, "settlement_asset": r.settlement_asset,
                "native_status": r.status, "catalogue_exclusion": r.exclusion,
                "collected_ms": r.collected_ms,
            })
    # Two native instruments mapped to one id (DUPLICATE_KEY upstream) are both
    # kept and disambiguated by their native symbol; neither is chosen silently.
    counts: dict = {}
    for row in rows:
        counts[row["base_id"]] = counts.get(row["base_id"], 0) + 1
    for row in rows:
        row["market_id"] = row["base_id"] if counts[row["base_id"]] == 1 else f"{row['base_id']}~{row['native_symbol']}"

    previous = {e["market_id"]: e for e in (doc["previous_universe"] or [])}
    markets = []
    for row in rows:
        src = by_source[row["source_market"]]
        authorized, auth_reason = _authorize(doc["policy"], row["venue"], row["market_type"],
                                             row["base"], row["quote"], row["market_id"])
        prev = previous.get(row["market_id"])
        if doc["previous_universe"] is None:
            change = "BASELINE"
        elif prev is None:
            change = "ADDED"
        elif (prev["native_symbol"], prev["contract_type"], prev["settlement_asset"]) != \
                (row["native_symbol"], row["contract_type"], row["settlement_asset"]):
            change = "METADATA_CHANGED"
        else:
            change = "UNCHANGED"
        markets.append({
            "market_id": row["market_id"], "venue": row["venue"], "market_type": row["market_type"],
            "contract_type": row["contract_type"], "base": row["base"], "quote": row["quote"],
            "native_symbol": row["native_symbol"], "settlement_asset": row["settlement_asset"],
            "catalogue": {
                "source_market": row["source_market"], "lifecycle": c.LISTED,
                "native_status": row["native_status"], "exclusion": row["catalogue_exclusion"],
                "native_base": row["native_base"], "native_quote": row["native_quote"],
                "collected_ms": row["collected_ms"], "metadata_current": src["metadata_current"],
                "metadata_reason": src["metadata_reason"], "raw_sha256": src["raw_sha256"],
                "provenance": provenance,
            },
            "discovered": True, "authorized": authorized, "authorization_reason": auth_reason,
            "source_access": src["access"], "source_access_reason": src["access_reason"],
            "change": change,
            "previous": prev,
        })

    # Markets of the previous cycle that are no longer listed stay visible.
    current_ids = {m["market_id"] for m in markets}
    for mid in sorted(set(previous) - current_ids):
        prev = previous[mid]
        venue, code, rest = (mid.split(":", 2) + ["", ""])[:3]
        market_type = "SPOT" if code == "spot" else "PERPETUAL"
        source_market = f"{venue.upper()}_{'SPOT' if market_type == 'SPOT' else 'PERPETUAL'}"
        src = by_source.get(source_market)
        complete = bool(src) and src["catalogue_state"] == COMPLETE
        ident = rest.split("~")[0]
        base, quote = ident.split("/", 1) if "/" in ident and not ident.startswith("?") else (None, None)
        lifecycle = c.RETIRED if complete else c.SOURCE_NOT_CURRENT
        authorized, auth_reason = _authorize(doc["policy"], venue, market_type, base, quote, mid)
        markets.append({
            "market_id": mid, "venue": venue, "market_type": market_type,
            "contract_type": prev["contract_type"], "base": base, "quote": quote,
            "native_symbol": prev["native_symbol"], "settlement_asset": prev["settlement_asset"],
            "catalogue": {
                "source_market": source_market, "lifecycle": lifecycle,
                "native_status": None, "exclusion": None, "native_base": None, "native_quote": None,
                "collected_ms": src["collected_ms"] if src else None,
                "metadata_current": bool(src and src["metadata_current"]),
                "metadata_reason": (src["metadata_reason"] if src else "SOURCE_UNKNOWN"),
                "raw_sha256": src["raw_sha256"] if src else {},
                "provenance": "PREVIOUS_CYCLE_IDENTITY",
            },
            "discovered": False, "authorized": authorized, "authorization_reason": auth_reason,
            "source_access": src["access"] if src else "UNKNOWN",
            "source_access_reason": src["access_reason"] if src else "SOURCE_UNKNOWN",
            "change": "RETIRED" if complete else "SOURCE_NOT_CURRENT",
            "previous": prev,
        })
    markets.sort(key=lambda m: m["market_id"])
    return {"markets": markets, "sources": sources}
