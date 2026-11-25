"""Groupe A — univers des marchés (R0-A). SYNTHETIC, hors réseau."""
from tests.radar_selection._helpers import clone, codes, doc, ev, market


def test_A01_automatic_import_of_several_instruments():
    e = ev("calm")
    sources = {m["catalogue"]["source_market"] for m in e["markets"]}
    assert sources == {"KRAKEN_SPOT", "KRAKEN_PERPETUAL", "MEXC_SPOT", "MEXC_PERPETUAL"}
    assert e["counts"]["discovered"] == len(e["markets"]) == 23
    # Every authorised market is evaluated without any manual pre-selection.
    assert e["counts"]["evaluated"] == e["counts"]["authorized"] == 21
    assert all(m["lifecycle"]["discovered"] for m in e["markets"])


def test_A02_kraken_and_mexc_btc_usdt_spot_are_distinct():
    e = ev("calm")
    k, m = market(e, "kraken:spot:BTC/USDT"), market(e, "mexc:spot:BTC/USDT")
    assert k["market_id"] != m["market_id"]
    assert (k["venue"], k["native_symbol"], k["catalogue"]["source_market"]) == ("kraken", "XBTUSDT", "KRAKEN_SPOT")
    assert (m["venue"], m["native_symbol"], m["catalogue"]["source_market"]) == ("mexc", "BTCUSDT", "MEXC_SPOT")
    assert k["score"] != m["score"]


def test_A03_btc_usd_never_merged_with_btc_usdt():
    e = ev("calm")
    usd, usdt = market(e, "kraken:spot:BTC/USD"), market(e, "kraken:spot:BTC/USDT")
    assert (usd["quote"], usdt["quote"]) == ("USD", "USDT")
    assert usd["native_symbol"] == "XBTUSD" and usdt["native_symbol"] == "XBTUSDT"
    assert len({m["market_id"] for m in e["markets"]}) == len(e["markets"])


def test_A04_spot_and_perpetual_stay_distinct():
    e = ev("calm")
    spot, perp = market(e, "mexc:spot:BTC/USDT"), market(e, "mexc:perp:BTC/USDT")
    assert (spot["market_type"], spot["contract_type"]) == ("SPOT", "SPOT")
    assert (perp["market_type"], perp["contract_type"]) == ("PERPETUAL", "LINEAR_PERPETUAL")
    assert perp["settlement_asset"] == "USDT" and spot["settlement_asset"] is None
    assert market(e, "kraken:spot:BTC/USD")["market_type"] != market(e, "kraken:perp:BTC/USD")["market_type"]


def test_A05_insufficient_identity_is_unknown_or_explicitly_refused():
    d = clone(doc("calm"))
    d["catalogues"]["mexc_spot_exchange_info"]["body"]["symbols"].append(
        {"symbol": "btcUSDT", "baseAsset": "btc", "quoteAsset": "USDT", "status": "1",
         "isSpotTradingAllowed": True, "fullName": "fixture"})
    e = ev(d)
    unknown = market(e, "mexc:spot:?btcUSDT")
    assert unknown["lifecycle"]["authorized"] is None
    assert unknown["admissibility"]["decision"] == "UNKNOWN"
    assert "IDENTITY_INSUFFICIENT" in codes(unknown)
    assert unknown["score"] is None
    # A Kraken wsname that contradicts its fields is refused explicitly.
    dot = market(ev("incoherent"), "kraken:spot:DOT/USDT")
    assert dot["admissibility"]["decision"] == "NON_ADMISSIBLE"
    assert "CATALOGUE_AMBIGUOUS_MAPPING" in codes(dot)


def test_A06_non_authorised_instruments_are_excluded():
    e = ev("calm")
    usdc = market(e, "kraken:spot:USDC/USDT")
    assert usdc["lifecycle"]["authorized"] is False
    assert usdc["admissibility"]["decision"] == "NON_ADMISSIBLE"
    assert "ASSET_CLASS_NOT_AUTHORIZED" in codes(usdc)
    d = clone(doc("calm"))
    d["policy"]["market_types"] = ["SPOT"]
    d["policy"]["deny"] = ["mexc:spot:SOL/USDT"]
    e2 = ev(d)
    for m in e2["markets"]:
        if m["market_type"] == "PERPETUAL":
            assert "MARKET_TYPE_NOT_AUTHORIZED" in codes(m) and m["score"] is None
    assert "DENIED_BY_POLICY" in codes(market(e2, "mexc:spot:SOL/USDT"))
    assert all(c["market_type"] == "SPOT" and c["market_id"] != "mexc:spot:SOL/USDT" for c in e2["candidates"])


def test_A07_removed_instrument_kept_and_qualified():
    e = ev("gaps")
    luna = market(e, "mexc:spot:LUNA/USDT")
    assert luna["catalogue"]["lifecycle"] == "RETIRED" and luna["change"] == "RETIRED"
    assert luna["lifecycle"]["discovered"] is False
    assert "MARKET_RETIRED_FROM_CATALOGUE" in codes(luna)
    assert market(e, "mexc:spot:WIF/USDT")["change"] == "ADDED"
    assert market(e, "kraken:spot:BTC/USDT")["change"] == "UNCHANGED"
    assert market(e, "mexc:perp:BTC/USDT")["change"] == "METADATA_CHANGED"
    # The source of a previously listed market is unavailable: not "retired".
    d = clone(doc("incoherent"))
    d["previous_universe"] = [{"market_id": "mexc:perp:BTC/USDT", "native_symbol": "BTC_USDT",
                               "contract_type": "LINEAR_PERPETUAL", "settlement_asset": "USDT"}]
    m = market(ev(d), "mexc:perp:BTC/USDT")
    assert m["catalogue"]["lifecycle"] == "SOURCE_NOT_CURRENT" and m["change"] == "SOURCE_NOT_CURRENT"
    assert m["admissibility"]["decision"] in ("UNKNOWN", "NON_ADMISSIBLE")
    assert "SOURCE_CATALOGUE_NOT_CURRENT" in codes(m)


def test_A08_empty_universe_is_verified_without_crash():
    d = clone(doc("calm"))
    for name, entry in d["catalogues"].items():
        entry.update(received_ms=None, error="SYNTHETIC_UNAVAILABLE", body=None)
    d["observations"] = []
    e = ev(d)
    assert e["markets"] == [] and e["candidates"] == []
    assert e["candidates_empty_reason"] == "NO_ADMISSIBLE_MARKET_FOR_MISSION"
    assert e["counts"]["discovered"] == 0
    assert all(s["catalogue_state"] == "UNAVAILABLE" for s in e["sources"])
    # R-REF: no mandatory reference is published, present or not (radar-evaluation/1.2.0).
    assert "reference" not in e
