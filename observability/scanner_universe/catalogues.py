"""Pure parsers of the four official public instrument catalogues (Scanner V1).

No network, file, clock or runtime access. Each parser receives the raw bytes
of an official public response plus its reception time and returns one
``MarketCatalogue``: a completeness verdict for the whole catalogue and one
evidence record per native instrument.

Sources (official public REST endpoints, no credential):

- MEXC Spot        ``GET https://api.mexc.com/api/v3/exchangeInfo``
- MEXC Perpetual   ``GET https://contract.mexc.com/api/v1/contract/detail``
- Kraken Spot      ``GET https://api.kraken.com/0/public/AssetPairs``
                   + ``GET https://api.kraken.com/0/public/Assets`` (asset altnames)
- Kraken Perpetual ``GET https://futures.kraken.com/derivatives/api/v3/instruments``

Completeness: a catalogue is COMPLETE only when the envelope is the expected
unfiltered success shape, it lists at least one instrument, no native symbol is
duplicated and every entry carries well-typed identity and status fields. One
unreadable entry makes the catalogue INCOMPLETE, because the missing instrument
could have belonged to the universe.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal

MARKETS = ("MEXC_SPOT", "MEXC_PERPETUAL", "KRAKEN_SPOT", "KRAKEN_PERPETUAL")
MARKET_LABELS = {
    "MEXC_SPOT": ("mexc", "SPOT"),
    "MEXC_PERPETUAL": ("mexc", "PERPETUAL"),
    "KRAKEN_SPOT": ("kraken", "SPOT"),
    "KRAKEN_PERPETUAL": ("kraken", "PERPETUAL"),
}
# Raw documents needed by each market, in request order.
ENDPOINTS = {
    "mexc_spot_exchange_info": "https://api.mexc.com/api/v3/exchangeInfo",
    "mexc_contract_detail": "https://contract.mexc.com/api/v1/contract/detail",
    "kraken_asset_pairs": "https://api.kraken.com/0/public/AssetPairs",
    "kraken_assets": "https://api.kraken.com/0/public/Assets",
    "kraken_futures_instruments": "https://futures.kraken.com/derivatives/api/v3/instruments",
}
MARKET_DOCUMENTS = {
    "MEXC_SPOT": ("mexc_spot_exchange_info",),
    "MEXC_PERPETUAL": ("mexc_contract_detail",),
    "KRAKEN_SPOT": ("kraken_asset_pairs", "kraken_assets"),
    "KRAKEN_PERPETUAL": ("kraken_futures_instruments",),
}
# Explicit, tested asset aliases. Applied to Kraken native asset names only
# (MEXC publishes BTC/DOGE directly). USD, USDT and USDC are never aliased.
KRAKEN_ASSET_ALIASES = {"XBT": "BTC", "XDG": "DOGE"}
MAX_RAW_BYTES = 8_000_000

COMPLETE, INCOMPLETE, UNAVAILABLE = "COMPLETE", "INCOMPLETE", "UNAVAILABLE"
# Exclusion reasons of one native instrument (None = admissible).
EXCLUSION_REASONS = (
    "NOT_TRADABLE", "NOT_PERPETUAL", "AMBIGUOUS_MAPPING", "AMBIGUOUS_CONTRACT",
    "DUPLICATE_KEY", "DARK_POOL_PAIR",
)
CONTRACT_TYPES = ("SPOT", "LINEAR_PERPETUAL", "INVERSE_PERPETUAL", "FIXED_MATURITY", "UNKNOWN")
_ASSET = re.compile(r"[A-Z0-9]{1,20}")


@dataclass(frozen=True)
class Evidence:
    """One native instrument as stated by one official catalogue."""

    market: str
    native_symbol: str
    base: str | None
    quote: str | None
    native_base: str
    native_quote: str
    status: str
    contract_type: str
    settlement_asset: str | None
    settlement_basis: str
    collected_ms: int
    exclusion: str | None = None

    @property
    def key(self) -> str | None:
        return None if self.base is None or self.quote is None else f"{self.base}/{self.quote}"

    def as_dict(self) -> dict:
        exchange, market_type = MARKET_LABELS[self.market]
        return {
            "exchange": exchange, "market_type": market_type, "native_symbol": self.native_symbol,
            "base": self.base, "quote": self.quote,
            "native_base": self.native_base, "native_quote": self.native_quote,
            "status": self.status, "contract_type": self.contract_type,
            "settlement_asset": self.settlement_asset, "settlement_basis": self.settlement_basis,
            "collected_ms": self.collected_ms, "exclusion": self.exclusion,
        }


@dataclass(frozen=True)
class MarketCatalogue:
    market: str
    state: str
    reason: str | None
    collected_ms: int | None
    raw_sha256: dict
    records: tuple = field(default_factory=tuple)

    def summary(self) -> dict:
        excluded: dict[str, int] = {}
        for record in self.records:
            if record.exclusion:
                excluded[record.exclusion] = excluded.get(record.exclusion, 0) + 1
        return {
            "market": self.market, "state": self.state, "reason": self.reason,
            "collected_ms": self.collected_ms, "raw_sha256": dict(sorted(self.raw_sha256.items())),
            "instruments": len(self.records),
            "admissible": sum(r.exclusion is None for r in self.records),
            "excluded": dict(sorted(excluded.items())),
        }


def strict_json(raw: bytes):
    """Bounded UTF-8 JSON; duplicate keys and NaN/Infinity refused; floats kept exact."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_RAW_BYTES:
        raise ValueError("payload missing or too large")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate field")
            out[key] = value
        return out

    def constant(_):
        raise ValueError("non-finite number")

    return json.loads(bytes(raw).decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=constant, parse_float=Decimal)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(bytes(raw)).hexdigest()


def unavailable(market: str, reason: str, raw_sha256: dict | None = None) -> MarketCatalogue:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", reason or ""):
        raise ValueError("an unavailable catalogue needs an explicit error code")
    return MarketCatalogue(market, UNAVAILABLE, reason, None, dict(raw_sha256 or {}))


def _incomplete(market, reason, collected_ms, hashes):
    return MarketCatalogue(market, INCOMPLETE, reason, collected_ms, hashes)


def _asset(value) -> str | None:
    return value if isinstance(value, str) and _ASSET.fullmatch(value) else None


def _native(value) -> bool:
    """A native symbol is kept as published (MEXC lists e.g. non-ASCII or
    ``GOLD(XAUT)USDT`` symbols); only non-printable or blank values are malformed.
    Such symbols cannot form a canonical key and end as AMBIGUOUS_MAPPING."""
    return isinstance(value, str) and 0 < len(value) <= 60 and value.isprintable() and not any(c.isspace() for c in value)


def _finish(market, collected_ms, hashes, records):
    """Mark keys stated twice by one market as ambiguous; never pick one silently."""
    seen: dict[str, int] = {}
    for record in records:
        if record.exclusion is None and record.key is not None:
            seen[record.key] = seen.get(record.key, 0) + 1
    final = tuple(
        Evidence(**{**r.__dict__, "exclusion": "DUPLICATE_KEY"})
        if r.exclusion is None and seen.get(r.key, 0) > 1 else r
        for r in records
    )
    return MarketCatalogue(market, COMPLETE, None, collected_ms, hashes, final)


_MALFORMED = object()


def _decode(market, raw, collected_ms, name):
    hashes = {name: sha256(raw)} if isinstance(raw, (bytes, bytearray)) else {}
    try:
        return hashes, strict_json(raw)
    except (ValueError, UnicodeError, RecursionError):
        return hashes, _MALFORMED


def parse_mexc_spot(raw: bytes, collected_ms: int) -> MarketCatalogue:
    market = "MEXC_SPOT"
    hashes, body = _decode(market, raw, collected_ms, "mexc_spot_exchange_info")
    if body is _MALFORMED:
        return _incomplete(market, "MALFORMED_JSON", collected_ms, hashes)
    if not isinstance(body, dict) or not isinstance(body.get("symbols"), list):
        return _incomplete(market, "UNEXPECTED_SHAPE", collected_ms, hashes)
    if not body["symbols"]:
        return _incomplete(market, "EMPTY_CATALOGUE", collected_ms, hashes)
    records, natives = [], set()
    for entry in body["symbols"]:
        if not isinstance(entry, dict):
            return _incomplete(market, "MALFORMED_ENTRY", collected_ms, hashes)
        symbol, base, quote = entry.get("symbol"), entry.get("baseAsset"), entry.get("quoteAsset")
        status, allowed = entry.get("status"), entry.get("isSpotTradingAllowed")
        if not _native(symbol) or not isinstance(base, str) or not isinstance(quote, str) \
                or not isinstance(status, str) or not isinstance(allowed, bool):
            return _incomplete(market, "MALFORMED_ENTRY", collected_ms, hashes)
        if symbol in natives:
            return _incomplete(market, "DUPLICATE_NATIVE_SYMBOL", collected_ms, hashes)
        natives.add(symbol)
        b, q = _asset(base), _asset(quote)
        exclusion = None
        if b is None or q is None or b == q or symbol != base + quote:
            exclusion = "AMBIGUOUS_MAPPING"
        elif not (status == "1" and allowed):
            exclusion = "NOT_TRADABLE"
        records.append(Evidence(market, symbol, b, q, base, quote,
                                f"status={status} isSpotTradingAllowed={str(allowed).lower()}",
                                "SPOT", None, "NOT_APPLICABLE_SPOT", collected_ms, exclusion))
    return _finish(market, collected_ms, hashes, records)


def parse_mexc_perpetual(raw: bytes, collected_ms: int) -> MarketCatalogue:
    market = "MEXC_PERPETUAL"
    hashes, body = _decode(market, raw, collected_ms, "mexc_contract_detail")
    if body is _MALFORMED:
        return _incomplete(market, "MALFORMED_JSON", collected_ms, hashes)
    if not isinstance(body, dict) or body.get("success") is not True or body.get("code") != 0 \
            or not isinstance(body.get("data"), list):
        return _incomplete(market, "UNEXPECTED_SHAPE", collected_ms, hashes)
    if not body["data"]:
        return _incomplete(market, "EMPTY_CATALOGUE", collected_ms, hashes)
    records, natives = [], set()
    for entry in body["data"]:
        if not isinstance(entry, dict):
            return _incomplete(market, "MALFORMED_ENTRY", collected_ms, hashes)
        symbol = entry.get("symbol")
        base, quote, settle = entry.get("baseCoin"), entry.get("quoteCoin"), entry.get("settleCoin")
        state, future_type, hidden = entry.get("state"), entry.get("futureType"), entry.get("isHidden", False)
        if not _native(symbol) or not all(isinstance(v, str) for v in (base, quote, settle)) \
                or type(state) is not int or type(future_type) is not int or not isinstance(hidden, bool):
            return _incomplete(market, "MALFORMED_ENTRY", collected_ms, hashes)
        if symbol in natives:
            return _incomplete(market, "DUPLICATE_NATIVE_SYMBOL", collected_ms, hashes)
        natives.add(symbol)
        b, q, s = _asset(base), _asset(quote), _asset(settle)
        # MEXC futureType: 1 = perpetual, 2 = delivery. settleCoin tells linear vs inverse.
        if future_type != 1:
            contract = "FIXED_MATURITY" if future_type == 2 else "UNKNOWN"
        elif s is not None and s == q:
            contract = "LINEAR_PERPETUAL"
        elif s is not None and s == b:
            contract = "INVERSE_PERPETUAL"
        else:
            contract = "UNKNOWN"
        exclusion = None
        if b is None or q is None or b == q or symbol != f"{base}_{quote}":
            exclusion = "AMBIGUOUS_MAPPING"
        elif future_type != 1:
            exclusion = "NOT_PERPETUAL"
        elif contract == "UNKNOWN":
            exclusion = "AMBIGUOUS_CONTRACT"
        elif state != 0 or hidden:
            exclusion = "NOT_TRADABLE"
        records.append(Evidence(market, symbol, b, q, base, quote,
                                f"state={state} futureType={future_type} isHidden={str(hidden).lower()}",
                                contract, s, "SOURCE_FIELD_settleCoin", collected_ms, exclusion))
    return _finish(market, collected_ms, hashes, records)


def parse_kraken_spot(pairs_raw: bytes, assets_raw: bytes, collected_ms: int) -> MarketCatalogue:
    market = "KRAKEN_SPOT"
    h1, pairs = _decode(market, pairs_raw, collected_ms, "kraken_asset_pairs")
    h2, assets = _decode(market, assets_raw, collected_ms, "kraken_assets")
    hashes = {**h1, **h2}
    if pairs is _MALFORMED or assets is _MALFORMED:
        return _incomplete(market, "MALFORMED_JSON", collected_ms, hashes)
    for body in (pairs, assets):
        if not isinstance(body, dict) or body.get("error") != [] or not isinstance(body.get("result"), dict):
            return _incomplete(market, "UNEXPECTED_SHAPE_OR_ERROR", collected_ms, hashes)
    if not pairs["result"] or not assets["result"]:
        return _incomplete(market, "EMPTY_CATALOGUE", collected_ms, hashes)
    altnames = {}
    for key, asset in assets["result"].items():
        if not isinstance(asset, dict) or not isinstance(asset.get("altname"), str):
            return _incomplete(market, "MALFORMED_ENTRY", collected_ms, hashes)
        altnames[key] = asset["altname"]
    records, natives = [], set()
    for key, pair in pairs["result"].items():
        if not isinstance(pair, dict):
            return _incomplete(market, "MALFORMED_ENTRY", collected_ms, hashes)
        alt, ws, base_key, quote_key, status = (pair.get(k) for k in ("altname", "wsname", "base", "quote", "status"))
        if not _native(alt) or not all(isinstance(v, str) for v in (base_key, quote_key, status)) \
                or not (ws is None or isinstance(ws, str)):
            return _incomplete(market, "MALFORMED_ENTRY", collected_ms, hashes)
        if alt in natives:
            return _incomplete(market, "DUPLICATE_NATIVE_SYMBOL", collected_ms, hashes)
        natives.add(alt)
        base_alt, quote_alt = altnames.get(base_key), altnames.get(quote_key)
        b = _asset(KRAKEN_ASSET_ALIASES.get(base_alt, base_alt)) if base_alt else None
        q = _asset(KRAKEN_ASSET_ALIASES.get(quote_alt, quote_alt)) if quote_alt else None
        exclusion = None
        if key.endswith(".d"):
            exclusion = "DARK_POOL_PAIR"
        elif b is None or q is None or b == q or (ws is not None and ws != f"{base_alt}/{quote_alt}"):
            exclusion = "AMBIGUOUS_MAPPING"
        elif status != "online":
            exclusion = "NOT_TRADABLE"
        records.append(Evidence(market, alt, b, q, base_key, quote_key, f"status={status} key={key}",
                                "SPOT", None, "NOT_APPLICABLE_SPOT", collected_ms, exclusion))
    return _finish(market, collected_ms, hashes, records)


def parse_kraken_perpetual(raw: bytes, collected_ms: int) -> MarketCatalogue:
    market = "KRAKEN_PERPETUAL"
    hashes, body = _decode(market, raw, collected_ms, "kraken_futures_instruments")
    if body is _MALFORMED:
        return _incomplete(market, "MALFORMED_JSON", collected_ms, hashes)
    if not isinstance(body, dict) or body.get("result") != "success" or not isinstance(body.get("instruments"), list):
        return _incomplete(market, "UNEXPECTED_SHAPE", collected_ms, hashes)
    if not body["instruments"]:
        return _incomplete(market, "EMPTY_CATALOGUE", collected_ms, hashes)
    records, natives = [], set()
    for entry in body["instruments"]:
        if not isinstance(entry, dict):
            return _incomplete(market, "MALFORMED_ENTRY", collected_ms, hashes)
        symbol, kind, tradeable = entry.get("symbol"), entry.get("type"), entry.get("tradeable")
        flags = {k: entry.get(k, False) for k in ("suspended", "isExpired", "postOnly")}
        if not _native(symbol) or not isinstance(kind, str) or not isinstance(tradeable, bool) \
                or not all(isinstance(v, bool) for v in flags.values()):
            return _incomplete(market, "MALFORMED_ENTRY", collected_ms, hashes)
        if symbol in natives:
            return _incomplete(market, "DUPLICATE_NATIVE_SYMBOL", collected_ms, hashes)
        natives.add(symbol)
        base, quote = entry.get("base"), entry.get("quote")
        native_base = base if isinstance(base, str) else ""
        native_quote = quote if isinstance(quote, str) else ""
        b = _asset(KRAKEN_ASSET_ALIASES.get(native_base, native_base)) if native_base else None
        q = _asset(native_quote) if native_quote else None
        dated = "lastTradingTime" in entry
        # PF_ = linear multi-collateral perpetual, PI_ = inverse perpetual; FF_/FI_ carry a maturity.
        if dated or symbol[:3] in ("FF_", "FI_"):
            contract = "FIXED_MATURITY"
        elif symbol.startswith("PF_") and kind == "flexible_futures":
            contract = "LINEAR_PERPETUAL"
        elif symbol.startswith("PI_") and kind == "futures_inverse":
            contract = "INVERSE_PERPETUAL"
        else:
            contract = "UNKNOWN"
        settlement = {"LINEAR_PERPETUAL": q, "INVERSE_PERPETUAL": b}.get(contract)
        basis = {"LINEAR_PERPETUAL": "KRAKEN_FLEXIBLE_MULTI_COLLATERAL_QUOTE",
                 "INVERSE_PERPETUAL": "KRAKEN_INVERSE_BASE"}.get(contract, "NOT_DETERMINED")
        exclusion = None
        if b is None or q is None or b == q or entry.get("pair", f"{native_base}:{native_quote}") != f"{native_base}:{native_quote}":
            exclusion = "AMBIGUOUS_MAPPING"
        elif contract == "FIXED_MATURITY":
            exclusion = "NOT_PERPETUAL"
        elif contract == "UNKNOWN":
            exclusion = "AMBIGUOUS_CONTRACT"
        elif not tradeable or any(flags.values()):
            exclusion = "NOT_TRADABLE"
        status = f"tradeable={str(tradeable).lower()} " + " ".join(f"{k}={str(v).lower()}" for k, v in flags.items())
        records.append(Evidence(market, symbol, b, q, native_base, native_quote, status + f" type={kind}",
                                contract, settlement, basis, collected_ms, exclusion))
    return _finish(market, collected_ms, hashes, records)


def parse_all(documents: dict) -> dict:
    """documents: name -> {"raw": bytes|None, "received_ms": int|None, "error": str|None}.

    Returns market -> MarketCatalogue. A market whose documents are not all
    present is UNAVAILABLE with the first error; it never becomes an empty list.
    """
    out = {}
    for market, names in MARKET_DOCUMENTS.items():
        missing = [n for n in names if not isinstance(documents.get(n), dict) or documents[n].get("raw") is None]
        if missing:
            entry = documents.get(missing[0]) or {}
            out[market] = unavailable(market, entry.get("error") or "DOCUMENT_MISSING")
            continue
        received = [documents[n]["received_ms"] for n in names]
        if not all(type(v) is int and v > 0 for v in received):
            out[market] = unavailable(market, "RECEPTION_TIME_MISSING")
            continue
        # The oldest reception bounds the market's evidence age.
        collected = min(received)
        raws = [documents[n]["raw"] for n in names]
        if market == "MEXC_SPOT":
            out[market] = parse_mexc_spot(raws[0], collected)
        elif market == "MEXC_PERPETUAL":
            out[market] = parse_mexc_perpetual(raws[0], collected)
        elif market == "KRAKEN_SPOT":
            out[market] = parse_kraken_spot(raws[0], raws[1], collected)
        else:
            out[market] = parse_kraken_perpetual(raws[0], collected)
    return out
