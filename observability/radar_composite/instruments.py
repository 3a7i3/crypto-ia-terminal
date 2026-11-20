"""Spot instrument identity and native venue bindings for last-trade observation.

Pure data. No network, file, runtime or exchange access. A binding is a
declaration whose alias must be backed by catalogue metadata (see coverage.py).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from observability.venue_quote_comparison import InstrumentKey

VENUES = ("mexc", "kraken")
REFERENCE_VENUE = "mexc"
PRICE_KIND = "LAST_TRADE"
EVIDENCE_KINDS = ("OBSERVATION", "SYNTHETIC")
# Kraken altnames that differ from the common ticker. Accepted only when the
# Kraken Assets catalogue shows an asset whose altname equals the alias.
KRAKEN_ALIASES = {"BTC": "XBT", "DOGE": "XDG"}
_ASSET = re.compile(r"[A-Z0-9]{1,20}")
_NATIVE = re.compile(r"[A-Za-z0-9/_.-]{1,40}")


def spot_instrument(base: str, quote: str) -> InstrumentKey:
    """Spot identity; USD and USDT are distinct quote assets, never merged."""
    for value in (base, quote):
        if not isinstance(value, str) or not _ASSET.fullmatch(value):
            raise ValueError("invalid asset id")
    if base == quote:
        raise ValueError("base and quote must differ")
    return InstrumentKey(base, quote, "SPOT", quote, "SPOT")


def instrument_dict(instrument: InstrumentKey) -> dict:
    return asdict(instrument)


def instrument_id(instrument: InstrumentKey | dict) -> str:
    """Same 24-hex identity rule as MarketVenueComparison groups."""
    data = instrument if isinstance(instrument, dict) else asdict(instrument)
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:24]


def instrument_from_dict(data: dict) -> InstrumentKey:
    if not isinstance(data, dict) or set(data) != {
        "base_asset_id", "quote_asset_id", "market_kind",
        "settlement_asset_id", "contract_identity",
    }:
        raise ValueError("invalid instrument")
    if data["market_kind"] != "SPOT" or data["contract_identity"] != "SPOT":
        raise ValueError("only SPOT instruments are admitted")
    key = spot_instrument(data["base_asset_id"], data["quote_asset_id"])
    if data["settlement_asset_id"] != key.settlement_asset_id:
        raise ValueError("spot settlement must equal quote asset")
    return key


@dataclass(frozen=True)
class Binding:
    """One native market of one venue for one CAT instrument."""

    venue: str
    native_symbol: str
    response_key: str
    instrument: InstrumentKey
    alias_evidence: str | None = None

    def __post_init__(self):
        if self.venue not in VENUES:
            raise ValueError("unknown venue")
        for value in (self.native_symbol, self.response_key):
            if not isinstance(value, str) or not _NATIVE.fullmatch(value):
                raise ValueError("invalid native symbol")
        if self.instrument.market_kind != "SPOT":
            raise ValueError("only SPOT bindings are admitted")
        if self.venue == "mexc":
            expected = self.instrument.base_asset_id + self.instrument.quote_asset_id
            if self.native_symbol != expected or self.response_key != expected:
                raise ValueError("MEXC native symbol must be BASEQUOTE")
            if self.alias_evidence is not None:
                raise ValueError("MEXC binding uses no alias")
        else:
            base = self.instrument.base_asset_id
            alias = KRAKEN_ALIASES.get(base)
            if alias is not None and not (
                isinstance(self.alias_evidence, str) and self.alias_evidence
            ):
                raise ValueError("Kraken alias requires catalogue evidence")
            if alias is None and self.alias_evidence is not None:
                raise ValueError("unexpected alias evidence")

    def as_dict(self) -> dict:
        return {
            "venue": self.venue,
            "native_symbol": self.native_symbol,
            "response_key": self.response_key,
            "instrument_id": instrument_id(self.instrument),
            "alias_evidence": self.alias_evidence,
        }


def binding_from_dict(data: dict, instrument: InstrumentKey) -> Binding:
    if not isinstance(data, dict) or set(data) != {
        "venue", "native_symbol", "response_key", "alias_evidence",
    }:
        raise ValueError("invalid binding")
    return Binding(
        data["venue"], data["native_symbol"], data["response_key"],
        instrument, data["alias_evidence"],
    )
