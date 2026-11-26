"""Groupe B — qualité scientifique (R0-B, R0-C étape 1). SYNTHETIC, hors réseau."""
from tests.radar_selection._helpers import clone, codes, doc, ev, market, observation


def test_B01_valid_l2_status_follows_its_proof():
    e = ev("calm")
    perp = market(e, "kraken:perp:BTC/USD")
    l2 = perp["criteria"]["l2_quality"]
    assert (l2["state"], l2["proof"], l2["status"]) == ("AVAILABLE", "PROVEN", "VERIFIED")
    assert l2["evidence_ref"].startswith("SYN:")
    assert perp["criteria"]["spread_depth"]["depth"]["basis"] == "L2"
    assert market(ev("calm", mission="L2_DEPTH_STUDY"), "kraken:perp:BTC/USD")["admissibility"]["decision"] == "ADMISSIBLE"
    # Technical compatibility is never presented as proven integrity.
    ref = market(e, "kraken:spot:BTC/USDT")["criteria"]["l2_quality"]
    assert (ref["proof"], ref["status"]) == ("TO_QUALIFY", "TECHNICALLY_COMPATIBLE")
    ref_l2 = market(ev("calm", mission="L2_DEPTH_STUDY"), "kraken:spot:BTC/USDT")
    assert ref_l2["admissibility"]["decision"] == "A_QUALIFIER"
    assert "L2_TO_QUALIFY_AFTER_AUTHORIZATION" in codes(ref_l2)
    # A VERIFIED claim without evidence reference is not accepted.
    d = clone(doc("calm"))
    observation(d, "kraken", "PERPETUAL", "PF_XBTUSD")["l2"]["evidence_ref"] = None
    claim = market(ev(d), "kraken:perp:BTC/USD")["criteria"]["l2_quality"]
    assert (claim["state"], claim["reason"]) == ("UNKNOWN", "L2_CLAIM_WITHOUT_EVIDENCE")


def test_B02_absent_l2_is_unknown_never_zero():
    e = ev("calm")
    m = market(e, "mexc:spot:ETH/USDT")
    l2 = m["criteria"]["l2_quality"]
    assert (l2["state"], l2["proof"], l2["reason"]) == ("UNKNOWN", "UNKNOWN", "L2_NOT_PROVIDED")
    assert "l2" not in m["score"]["components"] and "l2" in m["score"]["missing"]
    assert m["score"]["quality"] == "INCOMPLETE"
    m2 = market(ev("calm", mission="L2_DEPTH_STUDY"), "mexc:spot:ETH/USDT")
    assert m2["admissibility"]["decision"] == "UNKNOWN" and "L2_NOT_PROVEN" in codes(m2)


def test_B03_interrupted_continuity_degrades():
    e = ev("gaps")
    partial = market(e, "kraken:spot:BTC/USD")["criteria"]["continuity"]
    assert partial["class"] == "PARTIAL" and partial["gaps"] == 1 and partial["longest_gap"] == 12
    assert market(e, "kraken:spot:BTC/USD")["admissibility"]["decision"] == "A_QUALIFIER"
    insufficient = market(e, "kraken:spot:ETH/USDT")
    assert insufficient["criteria"]["continuity"]["class"] == "INSUFFICIENT"
    assert "CONTINUITY_INSUFFICIENT" in codes(insufficient)
    ref = market(e, "kraken:spot:BTC/USDT")["criteria"]["continuity"]
    assert (ref["class"], ref["covered"], ref["gaps"]) == ("VIABLE", 27, 2)
    full = market(ev("calm"), "kraken:spot:BTC/USDT")["criteria"]["continuity"]
    assert full["ratio"] == "1.0000" and full["class"] == "GOOD"
    assert ref["ratio"] < full["ratio"]


def test_B04_missing_or_incoherent_timestamp_has_no_time_certification():
    missing = market(ev("gaps"), "kraken:spot:ATOM/USDT")
    assert missing["observation"]["time"]["state"] == "UNCERTIFIED"
    assert missing["criteria"]["continuity"]["state"] == "UNKNOWN"
    assert "TIME_UNCERTIFIED_TIMESTAMP_MISSING" in codes(missing)
    assert missing["score"] is None
    swapped = market(ev("incoherent"), "kraken:spot:SOL/USDT")
    assert swapped["observation"]["time"]["state"] == "INCOHERENT"
    assert swapped["admissibility"]["decision"] == "NON_ADMISSIBLE"
    d = clone(doc("calm"))
    o = observation(d, "mexc", "SPOT", "SOLUSDT")
    o["samples"][-1]["t_ms"] = d["evaluation_time_ms"] + 60_000
    future = market(ev(d), "mexc:spot:SOL/USDT")
    assert future["observation"]["time"]["reason"] == "TIMESTAMP_IN_FUTURE"
    assert future["admissibility"]["decision"] == "NON_ADMISSIBLE"


def test_B05_old_source_has_degraded_freshness():
    stale = market(ev("gaps"), "kraken:spot:SOL/USDT")
    assert stale["criteria"]["continuity"]["freshness"] == "STALE"
    assert stale["lifecycle"]["recent_data"] == "STALE"
    assert "SOURCE_STALE" in codes(stale) and stale["admissibility"]["decision"] == "A_QUALIFIER"
    # A stale catalogue degrades its metadata validity too.
    perp = market(ev("incoherent"), "kraken:perp:ETH/USD")
    assert perp["catalogue"]["metadata_current"] is False
    assert "CATALOGUE_METADATA_STALE" in codes(perp)


def test_B06_absent_spread_is_never_invented():
    m = market(ev("gaps"), "kraken:spot:ADA/USDT")
    sp = m["criteria"]["spread_depth"]["spread"]
    assert sp == {"state": "UNKNOWN", "reason": "BBO_NOT_PROVIDED", "basis": None}
    assert m["admissibility"]["decision"] == "UNKNOWN" and "BBO_NOT_PROVIDED" in codes(m)
    price = market(ev("gaps", mission="PRICE_STUDY"), "kraken:spot:ADA/USDT")
    assert price["admissibility"]["decision"] == "ADMISSIBLE"
    assert "spread" in price["score"]["missing"] and "spread" not in price["score"]["components"]


def test_B07_incomplete_depth_is_partial():
    m = market(ev("gaps"), "kraken:perp:BTC/USD")
    depth = m["criteria"]["spread_depth"]["depth"]
    assert (depth["state"], depth["reason"], depth["basis"]) == ("PARTIAL", "DEPTH_ONE_SIDE_MISSING", "L2")
    assert m["criteria"]["spread_depth"]["state"] == "PARTIAL"
    l2 = market(ev("gaps", mission="L2_DEPTH_STUDY"), "kraken:perp:BTC/USD")
    assert l2["admissibility"]["decision"] == "A_QUALIFIER"
    assert "L2_DEPTH_DEPTH_ONE_SIDE_MISSING" in codes(l2)


def test_B08_contradictory_values_are_refused():
    e = ev("incoherent")
    expected = {
        "kraken:spot:ETH/USDT": "CONTRADICTORY_VALUES_CROSSED_OR_LOCKED_BOOK",
        "kraken:spot:ADA/USDT": "CONTRADICTORY_VALUES_MID_PRICE_MISMATCH",
        "kraken:spot:BTC/USD": "IDENTITY_CONFLICT_DECLARED_QUOTE",
        "mexc:spot:ETH/USDT": "IDENTITY_CONFLICT_DECLARED_QUOTE",
        "kraken:spot:ATOM/USDT": "DUPLICATE_OBSERVATION",
    }
    for mid, code in expected.items():
        m = market(e, mid)
        assert m["admissibility"]["decision"] == "NON_ADMISSIBLE", mid
        assert code in codes(m), mid
        assert m["score"] is None
    crossed = market(e, "kraken:spot:ETH/USDT")["criteria"]
    assert crossed["continuity"]["state"] == "INVALID"
    assert "median_bps" not in crossed["spread_depth"]["spread"]
    orphans = {o["native_symbol"] for o in e["orphan_observations"]}
    assert orphans == {"GHOSTUSDT", "BTC_USDT"}
