"""Scanner V1.1: instruments grouped by base asset, quote currencies listed, never equated."""
import json
import unittest

from observability.scanner_universe.catalogues import parse_all
from observability.scanner_universe.schema import validate_publication
from observability.scanner_universe.universe import FRESHNESS_MAX_AGE_MS, compute_universe, requalify

from ._factory import T0, documents, kraken_pairs, kraken_perp, mexc_perp, mexc_spot


def universe(now=T0 + 60_000, **kw):
    doc = compute_universe(parse_all(documents(**kw)), now)
    assert validate_publication(doc) == [], validate_publication(doc)
    return doc


# Real-world shape (2026-11-23): MEXC in USDT, Kraken Perpetual in USD only.
REAL_SHAPE = dict(ms=mexc_spot(("BTC", "USDT"), ("ADA", "USDT")), mp=mexc_perp(("BTC", "USDT"), ("BTC", "USD")),
                  kp=kraken_pairs(("XXBT", "ZUSD"), ("XXBT", "USDT"), ("ADA", "ZUSD")), kf=kraken_perp(("BTC", "USD")))


class AssetsByBase(unittest.TestCase):
    def test_strict_pairs_stay_empty_while_asset_groups_four_markets_with_their_quotes(self):
        doc = universe(**REAL_SHAPE)
        self.assertEqual((doc["schema_version"], doc["status"], doc["pairs"]), ("scanner-universe/1.1.0", "VERIFIED_EMPTY", []))
        btc = next(a for a in doc["assets"] if a["base"] == "BTC")
        self.assertEqual(btc["market_count"], 4)
        self.assertEqual(btc["quotes"], ["USD", "USDT"])
        self.assertEqual({m: [(r["native_symbol"], r["quote"]) for r in rows] for m, rows in btc["markets"].items()}, {
            "MEXC_SPOT": [("BTCUSDT", "USDT")],
            "MEXC_PERPETUAL": [("BTC_USD", "USD"), ("BTC_USDT", "USDT")],
            "KRAKEN_SPOT": [("XBTUSD", "USD"), ("XBTUSDT", "USDT")],
            "KRAKEN_PERPETUAL": [("PF_BTCUSD", "USD")],
        })

    def test_a_base_needs_one_spot_and_one_perpetual(self):
        doc = universe(**REAL_SHAPE)
        self.assertNotIn("ADA", [a["base"] for a in doc["assets"]])  # Spot only on both exchanges
        doc = universe(ms=mexc_spot(("SOL", "USDT")), mp=mexc_perp(("SOL", "USDT")), kp=kraken_pairs(("ATOM", "USDT")), kf=kraken_perp(("ETH", "USD")))
        self.assertEqual([(a["base"], a["market_count"]) for a in doc["assets"]], [("SOL", 2)])

    def test_assets_sorted_by_market_count_then_base(self):
        doc = universe(ms=mexc_spot(("BTC", "USDT"), ("ETH", "USDT")), mp=mexc_perp(("BTC", "USDT"), ("ETH", "USDT")),
                       kp=kraken_pairs(("XXBT", "USDT")), kf=kraken_perp(("BTC", "USD")))
        self.assertEqual([(a["base"], a["market_count"]) for a in doc["assets"]], [("BTC", 4), ("ETH", 2)])

    def test_no_asset_without_four_current_sources(self):
        doc = universe(kf="HTTP_503", **{k: v for k, v in REAL_SHAPE.items() if k != "kf"})
        self.assertEqual((doc["status"], doc["assets"], doc["asset_count"]), ("UNVERIFIABLE", [], 0))
        served = requalify(universe(**REAL_SHAPE), T0 + FRESHNESS_MAX_AGE_MS + 1)
        self.assertEqual((served["status"], served["assets"]), ("UNVERIFIABLE", []))
        self.assertEqual(validate_publication(served), [])

    def test_currencies_and_stablecoins_are_classed_apart_and_listed_after_crypto(self):
        doc = universe(ms=mexc_spot(("BTC", "USDT"), ("EUR", "USDT"), ("USDC", "USDT")),
                       mp=mexc_perp(("BTC", "USDT"), ("EUR", "USDT"), ("USDC", "USDT")),
                       kp=kraken_pairs(("XXBT", "ZUSD")), kf=kraken_perp(("BTC", "USD")))
        self.assertEqual([(a["base"], a["asset_class"]) for a in doc["assets"]],
                         [("BTC", "CRYPTO"), ("USDC", "STABLECOIN"), ("EUR", "FIAT")])
        relabelled = json.loads(json.dumps(doc))
        relabelled["assets"][2]["asset_class"] = "CRYPTO"
        self.assertIn("ASSET_CLASS", validate_publication(relabelled))

    def test_schema_guards(self):
        doc = universe(**REAL_SHAPE)
        spot_only = json.loads(json.dumps(doc))
        spot_only["assets"][0]["markets"] = {"MEXC_SPOT": spot_only["assets"][0]["markets"]["MEXC_SPOT"]}
        spot_only["assets"][0]["market_count"] = 1
        spot_only["assets"][0]["quotes"] = ["USDT"]
        self.assertIn("ASSET_NOT_SPOT_AND_PERPETUAL", validate_publication(spot_only))
        merged = json.loads(json.dumps(doc))
        merged["assets"][0]["quotes"] = ["USDT"]
        self.assertIn("ASSET_QUOTES", validate_publication(merged))
        count = json.loads(json.dumps(doc))
        count["asset_count"] += 1
        self.assertIn("ASSETS", validate_publication(count))

    def test_a_1_0_0_publication_is_still_read(self):
        doc = universe(**REAL_SHAPE)
        old = {k: v for k, v in doc.items() if k not in ("assets", "asset_count")}
        old["schema_version"] = "scanner-universe/1.0.0"
        self.assertEqual(validate_publication(old), [])
        self.assertEqual(requalify(old, T0 + FRESHNESS_MAX_AGE_MS + 1).get("assets"), None)


if __name__ == "__main__":
    unittest.main()
