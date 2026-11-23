"""Scanner V1 contract: intersection of four markets on fixed synthetic catalogues."""
import json
import unittest

from observability.scanner_universe.catalogues import MARKETS, parse_all
from observability.scanner_universe.schema import validate_publication
from observability.scanner_universe.universe import FRESHNESS_MAX_AGE_MS, compute_universe, requalify

from ._factory import T0, documents, kraken_assets, kraken_pairs, kraken_perp, mexc_perp, mexc_spot


def universe(now=T0 + 60_000, previous=None, **kw):
    doc = compute_universe(parse_all(documents(**kw)), now, previous)
    assert validate_publication(doc) == [], validate_publication(doc)
    return doc


def keys(doc):
    return [p["key"] for p in doc["pairs"]]


def exclusion(doc, key):
    return next(e for e in doc["exclusions"] if e["key"] == key)["reasons"]


class FourValidMarkets(unittest.TestCase):
    def test_pair_with_four_valid_proofs_enters(self):
        doc = universe()
        self.assertEqual(doc["status"], "VERIFIED")
        self.assertEqual(keys(doc), ["BTC/USDT"])
        proofs = doc["pairs"][0]["proofs"]
        self.assertEqual(set(proofs), set(MARKETS))
        self.assertEqual({m: p["native_symbol"] for m, p in proofs.items()}, {
            "MEXC_SPOT": "BTCUSDT", "MEXC_PERPETUAL": "BTC_USDT",
            "KRAKEN_SPOT": "XBTUSDT", "KRAKEN_PERPETUAL": "PF_BTCUSDT"})
        for proof in proofs.values():
            self.assertEqual((proof["base"], proof["quote"]), ("BTC", "USDT"))
            self.assertEqual(proof["collected_ms"], T0)
            self.assertIn("status", proof)
        self.assertEqual(proofs["MEXC_PERPETUAL"]["contract_type"], "LINEAR_PERPETUAL")
        self.assertEqual(proofs["MEXC_PERPETUAL"]["settlement_asset"], "USDT")
        self.assertEqual(proofs["KRAKEN_SPOT"]["native_base"], "XXBT")

    def test_kraken_alias_is_explicit(self):
        # XBT -> BTC only through the tested alias table; an unknown alias never matches.
        doc = universe(kp=kraken_pairs(("XXBT", "USDT")))
        self.assertEqual(keys(doc), ["BTC/USDT"])
        doc = universe(kp=kraken_pairs({"base": "WBT", "quote": "USDT"}), ka=kraken_assets({"WBT": "WBT"}))
        self.assertEqual(doc["status"], "VERIFIED_EMPTY")


class MissingMarket(unittest.TestCase):
    def test_each_market_missing_removes_the_pair(self):
        other = {"ms": mexc_spot(("ETH", "USDT")), "mp": mexc_perp(("ETH", "USDT")),
                 "kp": kraken_pairs(("XETH", "USDT")), "kf": kraken_perp(("ETH", "USDT"))}
        names = dict(zip(("ms", "mp", "kp", "kf"), MARKETS))
        for arg, market in names.items():
            with self.subTest(missing=market):
                doc = universe(**{arg: other[arg]})
                self.assertEqual(doc["status"], "VERIFIED_EMPTY")
                self.assertEqual(keys(doc), [])
                self.assertEqual(exclusion(doc, "BTC/USDT")[market], "ABSENT")

    def test_three_markets_only_is_excluded_not_shown(self):
        doc = universe(ms=mexc_spot(("BTC", "USDT"), ("SOL", "USDT")), mp=mexc_perp(("BTC", "USDT"), ("SOL", "USDT")),
                       kp=kraken_pairs(("XXBT", "USDT"), ("SOL", "USDT")))
        self.assertEqual(keys(doc), ["BTC/USDT"])
        self.assertEqual(exclusion(doc, "SOL/USDT")["KRAKEN_PERPETUAL"], "ABSENT")


class NotTradable(unittest.TestCase):
    def test_suspended_instrument_on_any_market_is_excluded(self):
        cases = {
            "MEXC_SPOT": {"ms": mexc_spot(("BTC", "USDT", "2", True))},
            "MEXC_PERPETUAL": {"mp": mexc_perp({"baseCoin": "BTC", "quoteCoin": "USDT", "state": 4})},
            "KRAKEN_SPOT": {"kp": kraken_pairs(("XXBT", "USDT", "cancel_only"))},
            "KRAKEN_PERPETUAL": {"kf": kraken_perp({"base": "BTC", "quote": "USDT", "suspended": True})},
        }
        for market, kw in cases.items():
            with self.subTest(market=market):
                doc = universe(**kw)
                self.assertEqual(keys(doc), [])
                self.assertEqual(exclusion(doc, "BTC/USDT")[market], "NOT_TRADABLE")

    def test_spot_trading_disallowed_and_hidden_contract(self):
        self.assertEqual(keys(universe(ms=mexc_spot(("BTC", "USDT", "1", False)))), [])
        self.assertEqual(keys(universe(mp=mexc_perp({"baseCoin": "BTC", "quoteCoin": "USDT", "isHidden": True}))), [])
        self.assertEqual(keys(universe(kf=kraken_perp({"base": "BTC", "quote": "USDT", "tradeable": False}))), [])


class Contracts(unittest.TestCase):
    def test_contract_with_maturity_is_not_a_perpetual(self):
        doc = universe(kf=kraken_perp({"symbol": "FF_BTCUSDT_261225", "base": "BTC", "quote": "USDT",
                                       "lastTradingTime": "2026-12-25T16:00:00.000Z"}))
        self.assertEqual(keys(doc), [])
        self.assertEqual(exclusion(doc, "BTC/USDT")["KRAKEN_PERPETUAL"], "NOT_PERPETUAL")
        doc = universe(mp=mexc_perp({"baseCoin": "BTC", "quoteCoin": "USDT", "futureType": 2}))
        self.assertEqual(exclusion(doc, "BTC/USDT")["MEXC_PERPETUAL"], "NOT_PERPETUAL")

    def test_inverse_perpetual_keeps_settlement_apart_from_quote(self):
        doc = universe(ms=mexc_spot(("BTC", "USD")), mp=mexc_perp({"baseCoin": "BTC", "quoteCoin": "USD", "settleCoin": "BTC"}),
                       kp=kraken_pairs(("XXBT", "ZUSD")), kf=kraken_perp(("BTC", "USD")))
        self.assertEqual(keys(doc), ["BTC/USD"])
        mexc = doc["pairs"][0]["proofs"]["MEXC_PERPETUAL"]
        self.assertEqual((mexc["quote"], mexc["settlement_asset"], mexc["contract_type"]), ("USD", "BTC", "INVERSE_PERPETUAL"))

    def test_unknown_settlement_is_ambiguous(self):
        doc = universe(mp=mexc_perp({"baseCoin": "BTC", "quoteCoin": "USDT", "settleCoin": "ETH"}))
        self.assertEqual(exclusion(doc, "BTC/USDT")["MEXC_PERPETUAL"], "AMBIGUOUS_CONTRACT")


class Quotes(unittest.TestCase):
    def test_usd_never_completes_usdt(self):
        doc = universe(kf=kraken_perp(("BTC", "USD")))
        self.assertEqual(doc["status"], "VERIFIED_EMPTY")
        self.assertEqual(exclusion(doc, "BTC/USDT")["KRAKEN_PERPETUAL"], "ABSENT")
        self.assertNotIn("BTC/USD", keys(doc))

    def test_usdc_and_usdt_stay_distinct(self):
        doc = universe(kp=kraken_pairs(("XXBT", "USDC")))
        self.assertEqual(keys(doc), [])


class Ambiguity(unittest.TestCase):
    def test_two_native_markets_for_one_key_are_excluded(self):
        # Kraken lists XBT/USDT and a separate BTC asset with its own BTC/USDT pair.
        doc = universe(kp=kraken_pairs(("XXBT", "USDT"), {"base": "BTC", "quote": "USDT", "altname": "BTCUSDT"}))
        self.assertEqual(keys(doc), [])
        self.assertEqual(exclusion(doc, "BTC/USDT")["KRAKEN_SPOT"], "DUPLICATE_KEY")

    def test_symbol_that_disagrees_with_its_fields(self):
        doc = universe(mp=mexc_perp({"baseCoin": "BTC", "quoteCoin": "USDT", "symbol": "BTC2_USDT"}))
        self.assertEqual(exclusion(doc, "BTC/USDT")["MEXC_PERPETUAL"], "AMBIGUOUS_MAPPING")
        doc = universe(kp=kraken_pairs({"base": "XXBT", "quote": "USDT", "wsname": "BTC/USDT"}))
        self.assertEqual(exclusion(doc, "BTC/USDT")["KRAKEN_SPOT"], "AMBIGUOUS_MAPPING")

    def test_non_ascii_native_symbol_is_kept_but_never_keyed(self):
        # Real MEXC catalogues list symbols such as GOLD(XAUT)USDT or non-ASCII names.
        doc = universe(ms=mexc_spot(("BTC", "USDT"), ("GOLD(XAUT)", "USDT"), ("牛来", "USDT")))
        self.assertEqual(doc["status"], "VERIFIED")
        catalogue = parse_all(documents(ms=mexc_spot(("GOLD(XAUT)", "USDT"))))["MEXC_SPOT"]
        self.assertEqual(catalogue.state, "COMPLETE")
        self.assertEqual((catalogue.records[0].key, catalogue.records[0].exclusion), (None, "AMBIGUOUS_MAPPING"))

    def test_perpetual_without_base_quote_fields(self):
        raw = json.loads(kraken_perp(("BTC", "USDT")))
        raw["instruments"].append({"symbol": "PI_XBTUSD", "type": "futures_inverse", "tradeable": True})
        doc = parse_all(documents(kf=json.dumps(raw).encode()))["KRAKEN_PERPETUAL"]
        pi = next(r for r in doc.records if r.native_symbol == "PI_XBTUSD")
        self.assertEqual((pi.key, pi.exclusion), (None, "AMBIGUOUS_MAPPING"))


class Freshness(unittest.TestCase):
    def test_stale_source_cannot_be_certified(self):
        doc = universe(now=T0 + FRESHNESS_MAX_AGE_MS + 1)
        self.assertEqual(doc["status"], "UNVERIFIABLE")
        self.assertEqual(doc["pairs"], [])
        self.assertEqual({b["reason"] for b in doc["blocking_sources"]}, {"STALE"})

    def test_bound_is_inclusive(self):
        self.assertEqual(universe(now=T0 + FRESHNESS_MAX_AGE_MS)["status"], "VERIFIED")

    def test_future_reception_is_refused(self):
        self.assertEqual(universe(now=T0 - 60_000)["status"], "UNVERIFIABLE")

    def test_serving_time_withdraws_pairs_into_dated_reference(self):
        doc = universe()
        served = requalify(doc, T0 + FRESHNESS_MAX_AGE_MS + 1)
        self.assertEqual(validate_publication(served), [])
        self.assertEqual((served["status"], served["pairs"]), ("UNVERIFIABLE", []))
        self.assertEqual(served["reference"], {"universe_sha256": doc["universe_sha256"], "status": "VERIFIED",
                                               "computed_ms": doc["computed_ms"], "keys": ["BTC/USDT"], "current": False})
        self.assertEqual(requalify(doc, T0 + 60_000)["status"], "VERIFIED")


class Completeness(unittest.TestCase):
    def test_incomplete_catalogue_never_yields_verified_empty(self):
        broken = {
            "truncated JSON": {"ms": mexc_spot(("BTC", "USDT"))[:-20]},
            "malformed entry": {"mp": json.dumps({"success": True, "code": 0, "data": [{"symbol": "BTC_USDT"}]}).encode()},
            "empty list": {"kf": json.dumps({"result": "success", "instruments": []}).encode()},
            "exchange error": {"kp": json.dumps({"error": ["EService:Unavailable"], "result": {}}).encode()},
            "duplicate native": {"ms": json.dumps({"symbols": [json.loads(mexc_spot(("BTC", "USDT")))["symbols"][0]] * 2}).encode()},
        }
        for name, kw in broken.items():
            with self.subTest(name):
                doc = universe(**kw)
                self.assertEqual(doc["status"], "UNVERIFIABLE")
                self.assertEqual(doc["pairs"], [])
                self.assertTrue(doc["blocking_sources"][0]["reason"].startswith("INCOMPLETE:"))

    def test_unavailable_source_names_the_market_and_keeps_dated_reference(self):
        previous = universe()
        doc = universe(kf="HTTP_503", previous=previous, now=T0 + 120_000)
        self.assertEqual(doc["status"], "UNVERIFIABLE")
        self.assertEqual(doc["blocking_sources"], [{"market": "KRAKEN_PERPETUAL", "reason": "UNAVAILABLE:HTTP_503"}])
        self.assertEqual(doc["reference"]["keys"], ["BTC/USDT"])
        self.assertIs(doc["reference"]["current"], False)

    def test_four_complete_without_common_pair_is_a_valid_empty_universe(self):
        doc = universe(ms=mexc_spot(("ADA", "USDT")), mp=mexc_perp(("SOL", "USDT")),
                       kp=kraken_pairs(("ATOM", "USDT")), kf=kraken_perp(("ETH", "USDT")))
        self.assertEqual((doc["status"], doc["pairs"], doc["blocking_sources"]), ("VERIFIED_EMPTY", [], []))
        self.assertTrue(all(s["current"] for s in doc["sources"]))


class SchemaGuards(unittest.TestCase):
    def test_tampered_publications_are_refused(self):
        doc = universe()
        three = json.loads(json.dumps(doc))
        del three["pairs"][0]["proofs"]["KRAKEN_PERPETUAL"]
        self.assertIn("PAIR_PROOFS_NOT_FOUR", validate_publication(three))
        mixed = json.loads(json.dumps(doc))
        mixed["pairs"][0]["proofs"]["KRAKEN_PERPETUAL"]["quote"] = "USD"
        self.assertIn("PROOF_KEY", validate_publication(mixed))
        empty_but_broken = universe(kf="HTTP_503")
        empty_but_broken["status"] = "VERIFIED_EMPTY"
        self.assertIn("VERIFIED_EMPTY_INCONSISTENT", validate_publication(empty_but_broken))
        dated = json.loads(json.dumps(doc))
        dated["pairs"][0]["proofs"]["MEXC_PERPETUAL"]["contract_type"] = "FIXED_MATURITY"
        self.assertIn("PROOF_CONTRACT_TYPE", validate_publication(dated))

    def test_deterministic(self):
        self.assertEqual(universe(), universe())


if __name__ == "__main__":
    unittest.main()
