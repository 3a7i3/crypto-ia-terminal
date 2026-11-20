"""Per-instrument venue coverage bound to one dated Radar selection.

Pure: catalogue responses are supplied as bytes (or as an explicit
unavailability). A catalogue that cannot be read never removes a row and
never becomes a confirmed absence.
"""
from __future__ import annotations

import hashlib
import re

from .decoders import strict_json
from .instruments import KRAKEN_ALIASES, Binding, instrument_id, spot_instrument

CATEGORIES = (
    "EXACT_COMMON_PAIR", "MAPPING_TO_VERIFY", "MEXC_ONLY", "KRAKEN_ONLY",
    "NO_VENUE_LISTED", "SOURCE_UNAVAILABLE",
)
CATALOGUES = ("mexc_exchange_info", "kraken_asset_pairs", "kraken_assets")
_SYMBOL = re.compile(r"[A-Z0-9]{2,40}")
_CODE = re.compile(r"[A-Z][A-Z0-9_]{1,79}")


def selection_from_scanner(raw):
    """Selection = observed rows + declared unavailable symbols, nothing dropped."""
    doc = strict_json(raw)
    if not isinstance(doc, dict) or doc.get("schema_version") != "spot-radar/1.0.0":
        raise ValueError("expected a spot-radar/1.0.0 scanner payload")
    symbols = []
    for row in doc["rows"]:
        ident = row["identity"]
        if ident.get("exchange") != "mexc" or ident.get("market") != "spot":
            raise ValueError("Radar rows must be MEXC Spot")
        symbols.append({"native_symbol": ident["native_symbol"],
                        "base_asset": row["base_asset"], "quote_asset": row["quote_asset"]})
    for item in doc["unavailable"]:
        symbols.append({"native_symbol": item["symbol"], "base_asset": None, "quote_asset": None})
    if len(symbols) != doc["selected_instruments"]:
        raise ValueError("selection count does not match selected_instruments")
    return {
        "source": "spot-radar/scanner",
        "snapshot_id": doc["snapshot_id"],
        "selection_sha256": doc["source"]["selection_sha256"],
        "server_time_ms": doc["server_time_ms"],
        "scanner_sha256": hashlib.sha256(bytes(raw)).hexdigest(),
        "symbols": symbols,
    }


def _catalogue(entry):
    """entry = {"raw": bytes|None, "received_ms": int|None, "error": str|None}."""
    if not isinstance(entry, dict) or set(entry) != {"raw", "received_ms", "error"}:
        raise ValueError("invalid catalogue entry")
    meta = {"available": False, "sha256": None, "received_ms": entry["received_ms"],
            "error": entry["error"], "bytes_retained": entry["raw"] is not None}
    if entry["raw"] is None:
        if not isinstance(entry["error"], str) or not _CODE.fullmatch(entry["error"]):
            raise ValueError("an unavailable catalogue needs an explicit error code")
        return meta, None
    if entry["error"] is not None:
        raise ValueError("a supplied catalogue cannot carry an error")
    meta["sha256"] = hashlib.sha256(bytes(entry["raw"])).hexdigest()
    try:
        body = strict_json(entry["raw"])
    except (ValueError, UnicodeError):
        meta.update(error="MALFORMED_CATALOGUE")
        return meta, None
    meta["available"] = True
    return meta, body


def _mexc_index(body):
    if not isinstance(body, dict) or not isinstance(body.get("symbols"), list):
        return None
    return {s.get("symbol"): s for s in body["symbols"] if isinstance(s, dict)}


def _kraken_index(pairs_body, assets_body):
    if not all(isinstance(b, dict) and b.get("error") == [] and isinstance(b.get("result"), dict)
               for b in (pairs_body, assets_body)):
        return None
    return pairs_body["result"], assets_body["result"]


def _mexc_side(index, symbol, base, quote):
    if index is None:
        return {"state": "SOURCE_UNAVAILABLE", "native_symbol": None, "native_status": None}
    entry = index.get(symbol)
    if entry is None:
        return {"state": "NOT_LISTED", "native_symbol": None, "native_status": None}
    if base is not None and (entry.get("baseAsset") != base or entry.get("quoteAsset") != quote):
        return {"state": "IDENTITY_MISMATCH", "native_symbol": symbol,
                "native_status": str(entry.get("status"))}
    trading = entry.get("status") == "1" and entry.get("isSpotTradingAllowed") is True
    return {"state": "LISTED" if trading else "LISTED_NOT_TRADING", "native_symbol": symbol,
            "native_status": f"status={entry.get('status')} spot={entry.get('isSpotTradingAllowed')}",
            "base_asset": entry.get("baseAsset"), "quote_asset": entry.get("quoteAsset")}


def _kraken_side(index, base, quote):
    empty = {"native_symbol": None, "response_key": None, "native_status": None,
             "alias_evidence": None, "other_quotes": []}
    if index is None:
        return {"state": "SOURCE_UNAVAILABLE", **empty}
    pairs, assets = index
    targets = {base: None}
    if base in KRAKEN_ALIASES:
        targets[KRAKEN_ALIASES[base]] = base
    base_keys = {k: a.get("altname") for k, a in assets.items()
                 if isinstance(a, dict) and a.get("altname") in targets}
    if len(set(base_keys.values())) > 1:
        return {"state": "AMBIGUOUS_ALIAS", **empty}
    if not base_keys:
        return {"state": "BASE_NOT_LISTED", **empty}
    if len(base_keys) > 1:
        return {"state": "AMBIGUOUS_ALIAS", **empty}
    (base_key, altname), = base_keys.items()
    evidence = None
    if altname != base:
        evidence = f"kraken.Assets:{base_key}.altname={altname}"
    alt_of = {k: a.get("altname") for k, a in assets.items() if isinstance(a, dict)}
    spot = {k: p for k, p in pairs.items()
            if isinstance(p, dict) and p.get("base") == base_key and not k.endswith(".d")}
    exact = {k: p for k, p in spot.items() if alt_of.get(p.get("quote")) == quote}
    others = sorted({alt_of.get(p.get("quote")) for p in spot.values()} - {quote, None})
    if len(exact) > 1:
        return {"state": "AMBIGUOUS_ALIAS", **empty}
    if not exact:
        return {"state": "QUOTE_NOT_LISTED", **empty, "alias_evidence": evidence,
                "other_quotes": others}
    (key, pair), = exact.items()
    online = pair.get("status") == "online"
    return {"state": "LISTED" if online else "LISTED_NOT_ONLINE",
            "native_symbol": pair.get("altname"), "response_key": key,
            "native_status": f"status={pair.get('status')} wsname={pair.get('wsname')}",
            "alias_evidence": evidence, "other_quotes": others}


def build_coverage(selection, catalogues, identity_reviews=None):
    """Return a MarketVenueCoverage v1.0.0 document; totals always equal the selection."""
    identity_reviews = dict(identity_reviews or {})
    for base, reason in identity_reviews.items():
        if not isinstance(reason, str) or not _CODE.fullmatch(reason):
            raise ValueError("identity review reasons must be explicit codes")
    if set(catalogues) != set(CATALOGUES):
        raise ValueError("all three catalogue entries are required")
    metas, bodies = {}, {}
    for name in CATALOGUES:
        metas[name], bodies[name] = _catalogue(catalogues[name])
    mexc = _mexc_index(bodies["mexc_exchange_info"]) if bodies["mexc_exchange_info"] is not None else None
    if bodies["mexc_exchange_info"] is not None and mexc is None:
        metas["mexc_exchange_info"].update(available=False, error="UNEXPECTED_SHAPE")
    kraken = None
    if bodies["kraken_asset_pairs"] is not None and bodies["kraken_assets"] is not None:
        kraken = _kraken_index(bodies["kraken_asset_pairs"], bodies["kraken_assets"])
        if kraken is None:
            for name in ("kraken_asset_pairs", "kraken_assets"):
                metas[name].update(available=False, error="UNEXPECTED_SHAPE_OR_ERROR")

    seen, rows = set(), []
    for item in selection["symbols"]:
        symbol = item["native_symbol"]
        if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
            raise ValueError("invalid selected symbol")
        if symbol in seen:
            raise ValueError("duplicate symbol in selection")
        seen.add(symbol)
        base, quote = item["base_asset"], item["quote_asset"]
        m = _mexc_side(mexc, symbol, base, quote)
        if base is None and m.get("base_asset"):
            base, quote = m["base_asset"], m["quote_asset"]
        if base is None:
            k = {"state": "SOURCE_UNAVAILABLE" if kraken is None else "NOT_EVALUATED",
                 "native_symbol": None, "response_key": None, "native_status": None,
                 "alias_evidence": None, "other_quotes": []}
        else:
            k = _kraken_side(kraken, base, quote)
        if base is None:
            category, reason = "MAPPING_TO_VERIFY", "BASE_UNRESOLVED"
        elif base in identity_reviews and m["state"] == "LISTED" and k["state"] == "LISTED":
            category, reason = "MAPPING_TO_VERIFY", identity_reviews[base]
        elif m["state"] == "LISTED" and k["state"] == "LISTED":
            category, reason = "EXACT_COMMON_PAIR", None
        elif "IDENTITY_MISMATCH" == m["state"] or "AMBIGUOUS_ALIAS" == k["state"]:
            category, reason = "MAPPING_TO_VERIFY", m["state"] if m["state"] == "IDENTITY_MISMATCH" else k["state"]
        elif "SOURCE_UNAVAILABLE" in (m["state"], k["state"]):
            side = "mexc" if m["state"] == "SOURCE_UNAVAILABLE" else "kraken"
            category, reason = "SOURCE_UNAVAILABLE", f"{side.upper()}_CATALOGUE_UNAVAILABLE"
        elif m["state"] == "LISTED":
            category, reason = "MEXC_ONLY", "KRAKEN_" + k["state"]
        elif k["state"] == "LISTED":
            category, reason = "KRAKEN_ONLY", "MEXC_" + m["state"]
        else:
            category, reason = "NO_VENUE_LISTED", f"MEXC_{m['state']}+KRAKEN_{k['state']}"
        bindings = []
        if category == "EXACT_COMMON_PAIR":
            ins = spot_instrument(base, quote)
            bindings = [
                Binding("mexc", symbol, symbol, ins).as_dict(),
                Binding("kraken", k["native_symbol"], k["response_key"], ins,
                        k["alias_evidence"]).as_dict(),
            ]
        rows.append({
            "native_symbol": symbol,
            "instrument_id": None if base is None else instrument_id(spot_instrument(base, quote)),
            "base_asset": base, "quote_asset": quote, "market_kind": "SPOT",
            "mexc": {key: m.get(key) for key in ("state", "native_symbol", "native_status")},
            "kraken": k,
            "coverage": category, "reason": reason, "bindings": bindings,
        })
    totals = {c: sum(r["coverage"] == c for r in rows) for c in CATEGORIES}
    if sum(totals.values()) != len(selection["symbols"]) or len(rows) != len(seen):
        raise ValueError("totals do not cover the selection")
    return {
        "schema_version": "1.0.0",
        "product": "MarketVenueCoverage",
        "authority": "OBSERVATIONAL_TELEMETRY",
        "execution_authority": False,
        "selection": {k: selection[k] for k in selection if k != "symbols"}
        | {"count": len(selection["symbols"])},
        "catalogues": metas,
        "identity_reviews": dict(sorted(identity_reviews.items())),
        "replayable": "scanner_sha256" in selection
        and all(m["bytes_retained"] for m in metas.values()),
        "rows": rows,
        "totals": totals,
    }
