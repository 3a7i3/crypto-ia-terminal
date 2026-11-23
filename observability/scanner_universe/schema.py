"""Structural and semantic validation of a ``scanner-universe/1.0.0`` or ``1.1.0`` publication.

Used by the GET-only Operator API reader: a publication that fails any rule is
refused as INVALID_SCHEMA, never shown as an empty or partial universe.
"""
from __future__ import annotations

from .catalogues import CONTRACT_TYPES, MARKET_LABELS, MARKETS
from .universe import PERPETUAL_MARKETS, SCHEMA_VERSION, SCHEMA_VERSIONS, SPOT_MARKETS

STATUSES = ("VERIFIED", "VERIFIED_EMPTY", "UNVERIFIABLE")
_TOP = {
    "schema_version", "product", "authority", "execution_authority", "rule",
    "freshness_max_age_ms", "cadence_ms", "computed_ms", "status", "blocking_sources",
    "sources", "pairs", "pair_count", "exclusions", "exclusions_truncated", "reference",
    "universe_sha256",
}
_PROOF = {
    "exchange", "market_type", "native_symbol", "base", "quote", "native_base", "native_quote",
    "status", "contract_type", "settlement_asset", "settlement_basis", "collected_ms", "exclusion",
}


def _int(value) -> bool:
    return type(value) is int and value >= 0


def validate_publication(doc) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["NOT_OBJECT"]
    keys = set(doc) - {"served_ms"}
    v11 = doc.get("schema_version") == SCHEMA_VERSION
    if keys != (_TOP | {"assets", "asset_count"} if v11 else _TOP):
        return ["TOP_LEVEL_KEYS"]
    if doc["schema_version"] not in SCHEMA_VERSIONS or doc["product"] != "ScannerCommonUniverse":
        errors.append("VERSION")
    if doc["execution_authority"] is not False or doc["authority"] != "OBSERVATIONAL_TELEMETRY":
        errors.append("AUTHORITY")
    if doc["status"] not in STATUSES:
        return errors + ["STATUS"]
    if not all(_int(doc[k]) for k in ("freshness_max_age_ms", "cadence_ms", "computed_ms", "pair_count")):
        errors.append("INTEGERS")
    sources = doc["sources"]
    if not isinstance(sources, list) or [s.get("market") if isinstance(s, dict) else None for s in sources] != list(MARKETS):
        return errors + ["SOURCES"]
    for s in sources:
        if not isinstance(s.get("current"), bool) or s.get("catalogue_state") not in ("COMPLETE", "INCOMPLETE", "UNAVAILABLE"):
            errors.append("SOURCE_STATE")
        if s.get("current") and (s.get("catalogue_state") != "COMPLETE" or not _int(s.get("collected_ms"))):
            errors.append("SOURCE_CURRENT_WITHOUT_COMPLETE_CATALOGUE")
        if not _int(s.get("admissible")) or not _int(s.get("instruments")) or s["admissible"] > s["instruments"]:
            errors.append("SOURCE_COUNTS")
    pairs = doc["pairs"]
    if not isinstance(pairs, list) or len(pairs) != doc["pair_count"]:
        return errors + ["PAIRS"]
    all_current = all(s.get("current") is True for s in sources)
    if doc["status"] == "VERIFIED" and (not pairs or not all_current or doc["blocking_sources"]):
        errors.append("VERIFIED_INCONSISTENT")
    if doc["status"] == "VERIFIED_EMPTY" and (pairs or not all_current or doc["blocking_sources"]):
        errors.append("VERIFIED_EMPTY_INCONSISTENT")
    if doc["status"] == "UNVERIFIABLE" and (pairs or not doc["blocking_sources"]):
        errors.append("UNVERIFIABLE_INCONSISTENT")
    if doc["reference"] is not None and doc["reference"].get("current") is not False:
        errors.append("REFERENCE_MARKED_CURRENT")
    seen = set()
    for pair in pairs:
        if not isinstance(pair, dict) or set(pair) != {"key", "base", "quote", "proofs"}:
            errors.append("PAIR_SHAPE")
            continue
        if pair["key"] in seen or pair["key"] != f"{pair['base']}/{pair['quote']}":
            errors.append("PAIR_KEY")
        seen.add(pair["key"])
        proofs = pair["proofs"]
        if not isinstance(proofs, dict) or set(proofs) != set(MARKETS):
            errors.append("PAIR_PROOFS_NOT_FOUR")
            continue
        for market, proof in proofs.items():
            exchange, market_type = MARKET_LABELS[market]
            if not isinstance(proof, dict) or set(proof) != _PROOF:
                errors.append("PROOF_SHAPE")
                continue
            if (proof["exchange"], proof["market_type"]) != (exchange, market_type):
                errors.append("PROOF_MARKET")
            if (proof["base"], proof["quote"]) != (pair["base"], pair["quote"]):
                errors.append("PROOF_KEY")
            if proof["exclusion"] is not None or not _int(proof["collected_ms"]):
                errors.append("PROOF_NOT_ADMISSIBLE")
            if proof["contract_type"] not in CONTRACT_TYPES:
                errors.append("PROOF_CONTRACT")
            perpetual = proof["contract_type"] in ("LINEAR_PERPETUAL", "INVERSE_PERPETUAL")
            if (market_type == "PERPETUAL") != perpetual or (market_type == "SPOT") != (proof["contract_type"] == "SPOT"):
                errors.append("PROOF_CONTRACT_TYPE")
    if v11:
        errors += _validate_assets(doc, all_current)
    return sorted(set(errors))


_LISTING = {"native_symbol", "quote", "contract_type", "settlement_asset"}


def _validate_assets(doc, all_current) -> list[str]:
    errors = []
    assets = doc["assets"]
    if not isinstance(assets, list) or not _int(doc["asset_count"]) or len(assets) != doc["asset_count"]:
        return ["ASSETS"]
    if assets and (doc["status"] == "UNVERIFIABLE" or not all_current):
        errors.append("ASSETS_WITHOUT_CURRENT_SOURCES")
    seen = set()
    for asset in assets:
        if not isinstance(asset, dict) or set(asset) != {"base", "market_count", "quotes", "markets"}:
            errors.append("ASSET_SHAPE")
            continue
        markets = asset["markets"]
        if asset["base"] in seen or not isinstance(markets, dict) or not set(markets) <= set(MARKETS):
            errors.append("ASSET_KEY")
            continue
        seen.add(asset["base"])
        if asset["market_count"] != len(markets):
            errors.append("ASSET_MARKET_COUNT")
        if not (set(markets) & set(SPOT_MARKETS)) or not (set(markets) & set(PERPETUAL_MARKETS)):
            errors.append("ASSET_NOT_SPOT_AND_PERPETUAL")
        quotes = set()
        for market, rows in markets.items():
            if not isinstance(rows, list) or not rows:
                errors.append("ASSET_LISTING")
                continue
            for row in rows:
                if not isinstance(row, dict) or set(row) != _LISTING or not isinstance(row["native_symbol"], str) or not row["native_symbol"]:
                    errors.append("ASSET_LISTING")
                    continue
                spot = market in SPOT_MARKETS
                if (row["contract_type"] == "SPOT") != spot or (not spot and row["contract_type"] not in ("LINEAR_PERPETUAL", "INVERSE_PERPETUAL")):
                    errors.append("ASSET_CONTRACT_TYPE")
                quotes.add(row["quote"])
        if asset["quotes"] != sorted(quotes):
            errors.append("ASSET_QUOTES")
    return errors
