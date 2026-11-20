import json
import unittest

from observability.radar_composite.coverage import build_coverage, selection_from_scanner
from observability.radar_composite.schema import validate_coverage

# Invented catalogues in the native response shapes (no real capture).
MEXC_INFO = {"timezone": "CST", "serverTime": 1, "rateLimits": [], "exchangeFilters": [], "symbols": [
    {"symbol": s, "baseAsset": s[:-4], "quoteAsset": "USDT", "status": "1",
     "isSpotTradingAllowed": True, "fullName": n}
    for s, n in (("BTCUSDT", "Bitcoin"), ("DOGEUSDT", "DOGE"), ("ENAUSDT", "Ethena"),
                 ("MXUSDT", "MX Token"), ("BCHUSDT", "Bitcoin Cash Node"), ("ATOMUSDT", "COSMOS"))
] + [{"symbol": "ETHUSDT", "baseAsset": "ETH", "quoteAsset": "USDT", "status": "2",
      "isSpotTradingAllowed": False}]}
ASSETS = {"error": [], "result": {
    k: {"aclass": "currency", "altname": a, "status": "enabled"}
    for k, a in (("XXBT", "XBT"), ("XXDG", "XDG"), ("ENA", "ENA"), ("BCH", "BCH"),
                 ("XETH", "ETH"), ("SOL", "SOL"), ("ATOM", "ATOM"), ("USDT", "USDT"), ("ZUSD", "USD"))}}
PAIRS = {"error": [], "result": {
    k: {"altname": k, "wsname": w, "base": b, "quote": q, "status": s, "aclass_base": "currency"}
    for k, w, b, q, s in (
        ("XBTUSDT", "XBT/USDT", "XXBT", "USDT", "online"),
        ("XXBTZUSD", "XBT/USD", "XXBT", "ZUSD", "online"),
        ("XDGUSDT", "XDG/USDT", "XXDG", "USDT", "online"),
        ("ENAUSD", "ENA/USD", "ENA", "ZUSD", "online"),
        ("BCHUSDT", "BCH/USDT", "BCH", "USDT", "online"),
        ("ETHUSDT", "ETH/USDT", "XETH", "USDT", "online"),
        ("SOLUSDT", "SOL/USDT", "SOL", "USDT", "online"),
        ("ATOMUSDT", "ATOM/USDT", "ATOM", "USDT", "cancel_only"),
    )}}
SELECTED = ["BTCUSDT", "DOGEUSDT", "ENAUSDT", "MXUSDT", "BCHUSDT", "ETHUSDT", "SOLUSDT", "ATOMUSDT"]


def scanner(unavailable=()):
    rows = [{"identity": {"exchange": "mexc", "market": "spot", "native_symbol": s},
             "base_asset": s[:-4], "quote_asset": "USDT"} for s in SELECTED if s not in unavailable]
    return json.dumps({
        "schema_version": "spot-radar/1.0.0", "snapshot_id": "a" * 64,
        "server_time_ms": "1795136877929",
        "source": {"selection_sha256": "b" * 64},
        "selected_instruments": len(SELECTED),
        "rows": rows, "unavailable": [{"symbol": s, "reason": "X"} for s in unavailable],
    }).encode()


def entry(body):
    return {"raw": json.dumps(body).encode(), "received_ms": 1, "error": None}


def missing(code="HTTP_TIMEOUT"):
    return {"raw": None, "received_ms": None, "error": code}


def build(mexc=None, pairs=None, assets=None, reviews=None, unavailable=()):
    return build_coverage(
        selection_from_scanner(scanner(unavailable)),
        {"mexc_exchange_info": mexc or entry(MEXC_INFO),
         "kraken_asset_pairs": pairs or entry(PAIRS),
         "kraken_assets": assets or entry(ASSETS)},
        reviews if reviews is not None else {"BCH": "MEXC_NAME_BITCOIN_CASH_NODE_UNVERIFIED"},
    )


def by_symbol(doc):
    return {r["native_symbol"]: r for r in doc["rows"]}


class Coverage(unittest.TestCase):
    def test_categories_and_totals(self):
        doc = build()
        rows = by_symbol(doc)
        self.assertTrue(validate_coverage(doc))
        self.assertEqual(rows["BTCUSDT"]["coverage"], "EXACT_COMMON_PAIR")
        self.assertEqual(rows["BTCUSDT"]["kraken"]["alias_evidence"], "kraken.Assets:XXBT.altname=XBT")
        self.assertEqual(rows["BTCUSDT"]["bindings"][1]["native_symbol"], "XBTUSDT")
        self.assertEqual(rows["DOGEUSDT"]["kraken"]["alias_evidence"], "kraken.Assets:XXDG.altname=XDG")
        self.assertEqual((rows["ENAUSDT"]["coverage"], rows["ENAUSDT"]["reason"]),
                         ("MEXC_ONLY", "KRAKEN_QUOTE_NOT_LISTED"))
        self.assertEqual(rows["ENAUSDT"]["kraken"]["other_quotes"], ["USD"])
        self.assertEqual(rows["MXUSDT"]["reason"], "KRAKEN_BASE_NOT_LISTED")
        self.assertEqual((rows["BCHUSDT"]["coverage"], rows["BCHUSDT"]["reason"]),
                         ("MAPPING_TO_VERIFY", "MEXC_NAME_BITCOIN_CASH_NODE_UNVERIFIED"))
        self.assertEqual((rows["ETHUSDT"]["coverage"], rows["ETHUSDT"]["reason"]),
                         ("KRAKEN_ONLY", "MEXC_LISTED_NOT_TRADING"))
        self.assertEqual((rows["SOLUSDT"]["coverage"], rows["SOLUSDT"]["reason"]),
                         ("KRAKEN_ONLY", "MEXC_NOT_LISTED"))
        self.assertEqual(rows["ATOMUSDT"]["reason"], "KRAKEN_LISTED_NOT_ONLINE")
        self.assertEqual(sum(doc["totals"].values()), len(SELECTED))
        self.assertEqual(doc["totals"]["EXACT_COMMON_PAIR"], 2)
        self.assertEqual([r["native_symbol"] for r in doc["rows"]], SELECTED)

    def test_bound_to_dated_selection(self):
        doc = build()
        self.assertEqual(doc["selection"]["snapshot_id"], "a" * 64)
        self.assertEqual(doc["selection"]["selection_sha256"], "b" * 64)
        self.assertEqual(doc["selection"]["count"], len(SELECTED))
        self.assertEqual(len(doc["selection"]["scanner_sha256"]), 64)
        self.assertTrue(doc["replayable"])

    def test_bch_without_review_would_be_exact(self):
        rows = by_symbol(build(reviews={}))
        self.assertEqual(rows["BCHUSDT"]["coverage"], "EXACT_COMMON_PAIR")

    def test_unavailable_catalogue_keeps_every_row(self):
        doc = build(pairs=missing())
        self.assertEqual(len(doc["rows"]), len(SELECTED))
        self.assertTrue(validate_coverage(doc))
        self.assertFalse(doc["replayable"])
        rows = by_symbol(doc)
        self.assertEqual(rows["MXUSDT"]["coverage"], "SOURCE_UNAVAILABLE")
        self.assertEqual(rows["MXUSDT"]["reason"], "KRAKEN_CATALOGUE_UNAVAILABLE")
        self.assertNotIn("MEXC_ONLY", {r["coverage"] for r in doc["rows"]})

    def test_malformed_or_error_catalogue_is_not_absence(self):
        bad = {"raw": b"{not json", "received_ms": 1, "error": None}
        doc = build(mexc=bad)
        self.assertEqual(doc["catalogues"]["mexc_exchange_info"]["error"], "MALFORMED_CATALOGUE")
        self.assertEqual(doc["totals"]["SOURCE_UNAVAILABLE"], len(SELECTED))
        err = entry({"error": ["EGeneral:Temporary lockout"], "result": {}})
        doc = build(pairs=err)
        self.assertEqual(doc["totals"]["SOURCE_UNAVAILABLE"], len(SELECTED))

    def test_ambiguous_alias(self):
        assets = json.loads(json.dumps(ASSETS))
        assets["result"]["BTCNEW"] = {"aclass": "currency", "altname": "BTC", "status": "enabled"}
        rows = by_symbol(build(assets=entry(assets)))
        self.assertEqual((rows["BTCUSDT"]["coverage"], rows["BTCUSDT"]["reason"]),
                         ("MAPPING_TO_VERIFY", "AMBIGUOUS_ALIAS"))

    def test_radar_unavailable_symbol_kept_and_resolved_from_catalogue(self):
        rows = by_symbol(build(unavailable=("DOGEUSDT",)))
        self.assertEqual(rows["DOGEUSDT"]["base_asset"], "DOGE")
        self.assertEqual(rows["DOGEUSDT"]["coverage"], "EXACT_COMMON_PAIR")
        rows = by_symbol(build(mexc=missing(), unavailable=("DOGEUSDT",)))
        self.assertEqual((rows["DOGEUSDT"]["coverage"], rows["DOGEUSDT"]["reason"]),
                         ("MAPPING_TO_VERIFY", "BASE_UNRESOLVED"))

    def test_duplicate_selection_refused(self):
        sel = selection_from_scanner(scanner())
        sel["symbols"].append(sel["symbols"][0])
        with self.assertRaises(ValueError):
            build_coverage(sel, {"mexc_exchange_info": entry(MEXC_INFO),
                                 "kraken_asset_pairs": entry(PAIRS), "kraken_assets": entry(ASSETS)})

    def test_unavailable_entry_needs_explicit_code(self):
        with self.assertRaises(ValueError):
            build(pairs={"raw": None, "received_ms": None, "error": None})


if __name__ == "__main__":
    unittest.main()
