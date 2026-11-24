"""Groupe C — sélection automatique (R0-C étape 2). SYNTHETIC, hors réseau."""
import random
from decimal import Decimal

from observability.radar_selection import contract as c
from observability.radar_selection.fixture import canonical
from observability.radar_selection.manual import empty_preferences
from tests.radar_selection._helpers import NAMES, clone, doc, ev, market, observation


def _ranking_view(e):
    return {"candidates": e["candidates"],
            "markets": {m["market_id"]: (m["admissibility"], m["score"], m["criteria"]) for m in e["markets"]}}


def test_C01_ranking_is_deterministic():
    for name in NAMES:
        a, b = ev(name), ev(name)
        assert canonical(a) == canonical(b)
        assert [x["market_id"] for x in a["candidates"]] == [x["market_id"] for x in b["candidates"]]


def test_C02_three_candidates_at_most():
    for name in NAMES:
        for mission in c.MISSIONS:
            assert len(ev(name, mission=mission)["candidates"]) <= 3
    # Larger universe: still three.
    d = clone(doc("calm"))
    body = d["catalogues"]["mexc_spot_exchange_info"]["body"]
    template = observation(d, "mexc", "SPOT", "ETHUSDT")
    for i in range(40):
        base = f"SYN{i:02d}"
        body["symbols"].append({"symbol": base + "USDT", "baseAsset": base, "quoteAsset": "USDT",
                                "status": "1", "isSpotTradingAllowed": True, "fullName": "fixture"})
        o = clone(template)
        o.update(native_symbol=base + "USDT", evidence_ref=f"SYN:big:{base}")
        d["observations"].append(o)
    e = ev(d)
    assert e["counts"]["admissible"] > 40 and len(e["candidates"]) == 3


def test_C03_ranking_independent_of_read_order():
    for name in NAMES:
        d = clone(doc(name))
        base = _ranking_view(ev(d))
        rng = random.Random(7)
        for _ in range(3):
            s = clone(d)
            rng.shuffle(s["observations"])
            s["catalogues"]["mexc_spot_exchange_info"]["body"]["symbols"].reverse()
            if s["catalogues"]["mexc_contract_detail"]["body"]:
                s["catalogues"]["mexc_contract_detail"]["body"]["data"].reverse()
            s["catalogues"]["kraken_futures_instruments"]["body"]["instruments"].reverse()
            pairs = s["catalogues"]["kraken_asset_pairs"]["body"]["result"]
            s["catalogues"]["kraken_asset_pairs"]["body"]["result"] = dict(reversed(list(pairs.items())))
            assert _ranking_view(ev(s)) == base, name


def test_C04_documented_preference_for_diverse_conditions():
    vol = ev("volatile")
    assert {x["regime"] for x in vol["candidates"]} == {"CALM", "ACTIVE", "VOLATILE"}
    assert all(x["selection_rule"] == "REGIME_SLOT" for x in vol["candidates"])
    calm = ev("calm")
    pepe = next(x for x in calm["candidates"] if x["market_id"] == "mexc:spot:PEPE/USDT")
    assert pepe["regime"] == "ACTIVE" and pepe["selection_rule"] == "REGIME_SLOT"
    # Pure score order would have taken three higher-scored CALM markets instead.
    scored = sorted((m for m in calm["markets"] if m["score"] and m["market_id"] != c.REFERENCE["market_id"]),
                    key=lambda m: (-Decimal(m["score"]["value"]), m["market_id"]))
    assert "mexc:spot:PEPE/USDT" not in [m["market_id"] for m in scored[:3]]
    # With one regime only, a different base asset is preferred over a higher score.
    bases = [x["base"] for x in calm["candidates"]]
    assert len(set(bases)) == len(bases)


def test_C05_no_non_admissible_market_presented_as_admissible():
    for name in NAMES:
        for mission in c.MISSIONS:
            e = ev(name, mission=mission)
            for x in e["candidates"]:
                assert market(e, x["market_id"])["admissibility"]["decision"] == "ADMISSIBLE"
                assert x["status"] == "PROPOSED_NOT_AUTHORIZED"
            for m in e["markets"]:
                assert (m["score"] is None) == (m["admissibility"]["decision"] != "ADMISSIBLE")


def test_C06_unknown_criterion_never_becomes_a_favourable_score():
    d = clone(doc("calm"))
    known = market(ev(d), "mexc:spot:ETH/USDT")["score"]
    observation(d, "mexc", "SPOT", "ETHUSDT")["activity"] = None
    unknown = market(ev(d), "mexc:spot:ETH/USDT")["score"]
    assert "activity" in unknown["missing"] and "activity" not in unknown["components"]
    assert Decimal(unknown["value"]) < Decimal(known["value"])
    assert Decimal(unknown["max_reachable"]) == 100 - c.WEIGHTS["activity"] - c.WEIGHTS["l2"]
    # Zero observed trades is a measured 0, distinct from unknown.
    observation(d, "mexc", "SPOT", "ETHUSDT")["activity"] = {"kind": "TRADE_COUNT_WINDOW", "value": 0,
                                                             "evidence_ref": "SYN:zero"}
    zero = market(ev(d), "mexc:spot:ETH/USDT")["score"]
    assert zero["components"]["activity"] == 0 and "activity" not in zero["missing"]


def test_C07_reference_is_independent_of_automatic_ranking():
    for name in NAMES:
        e = ev(name)
        assert c.REFERENCE["market_id"] not in [x["market_id"] for x in e["candidates"]]
        assert e["reference"]["in_ranking"] is False
        assert e["reference"]["historical_admission"] == "NOT_YET_HISTORICALLY_ADMITTED"
    calm = ev("calm")
    ref_score = Decimal(calm["reference"]["score"])
    assert ref_score > min(Decimal(x["score"]) for x in calm["candidates"])  # would have ranked
    prefs = empty_preferences() | {"excluded": [c.REFERENCE["market_id"]]}
    excluded = ev("calm", prefs=prefs)
    assert excluded["candidates"] == calm["candidates"]
    assert excluded["reference"]["radar_decision"] == calm["reference"]["radar_decision"]


def test_C08_no_eligible_candidate_gives_justified_empty_list():
    d = clone(doc("calm"))
    d["observations"] = []
    e = ev(d)
    assert e["candidates"] == [] and e["candidates_empty_reason"] == "NO_ADMISSIBLE_MARKET_FOR_MISSION"
    assert e["counts"]["unknown"] >= e["counts"]["authorized"]
    admissible = [m["market_id"] for m in ev("incoherent")["markets"] if m["score"]]
    prefs = empty_preferences() | {"excluded": sorted(admissible)}
    e2 = ev("incoherent", prefs=prefs)
    assert e2["candidates"] == [] and e2["candidates_empty_reason"] == "ADMISSIBLE_MARKETS_ALL_EXCLUDED_OR_REFERENCE"


def test_C09_estimated_costs_distinct_from_measured():
    e = ev("calm")
    measured = market(e, "mexc:perp:BTC/USDT")["criteria"]["collection_cost"]
    estimated = market(e, "mexc:spot:BTC/USDT")["criteria"]["collection_cost"]
    assert measured["basis"] == "MEASURED" and "MEASUREMENT" in measured["provenance"]
    assert estimated["basis"] == "ESTIMATED" and "ESTIMATE" in estimated["provenance"]
    for x in e["candidates"]:
        assert x["cost"]["basis"] in ("ESTIMATED", "MEASURED") and x["cost"]["provenance"]
        assert ("Coût estimé, non mesuré" in x["limits"]) == (x["cost"]["basis"] == "ESTIMATED")
    partial = market(ev("gaps"), "mexc:spot:SOL/USDT")["criteria"]["collection_cost"]
    assert partial["state"] == "PARTIAL" and partial["missing"] == ["cpu_pct", "memory_mib"]
    unknown = market(ev("gaps"), "mexc:spot:BTC/USDT")
    assert unknown["criteria"]["collection_cost"]["state"] == "UNKNOWN" and "cost" in unknown["score"]["missing"]


def test_C10_ranking_reasons_are_reproducible_and_auditable():
    for name in NAMES:
        e1, e2 = ev(name), ev(name)
        assert [x["reason"] for x in e1["candidates"]] == [x["reason"] for x in e2["candidates"]]
        assert e1["ranking_version"] == c.RANKING_VERSION and e1["rules_version"] == c.RULES_VERSION
        for x in e1["candidates"]:
            assert x["selection_rule"] in ("REGIME_SLOT", "BASE_DIVERSITY", "SCORE")
            assert x["score"] in x["reason"]
        for m in e1["markets"]:
            s = m["score"]
            if s:
                total = sum(Decimal(c.WEIGHTS[k]) * Decimal(v) for k, v in s["components"].items()) / 100
                assert str(total.quantize(Decimal("0.01"))) == s["value"]
                assert set(s["components"]) | set(s["missing"]) == set(c.WEIGHTS)
        ranks = [x["rank"] for x in e1["candidates"]]
        assert ranks == list(range(1, len(ranks) + 1))
