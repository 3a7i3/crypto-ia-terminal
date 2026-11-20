import copy
import json
import random
import unittest
from pathlib import Path

from observability.radar_composite.composite import compute
from observability.radar_composite.m5 import replay
from observability.radar_composite.schema import validate_composite
from tests.radar_composite._factory import (
    START, instants, packet, poll, series, trade,
)


def reasons(result, venue):
    return [p["sources"][venue]["reason"] for p in result["points"]]


class CompleteWindow(unittest.TestCase):
    def setUp(self):
        self.trades = series("mexc", 62000, lag=700) + series("kraken", 62002, lag=698)
        self.result = compute(packet(self.trades))

    def test_thirty_valid_points_give_one_complete_candle(self):
        r = self.result
        self.assertTrue(validate_composite(r))
        self.assertEqual(r["series"]["composite"]["status"], "COMPLETE")
        self.assertEqual(r["series"]["composite"]["valid_points"], 30)
        self.assertEqual(r["series"]["composite"]["ohlc"],
                         {"open": "62001", "high": "62030", "low": "62001", "close": "62030"})
        self.assertEqual({p["status"] for p in r["points"]}, {"COMPOSITE"})
        self.assertEqual(r["points"][0]["contributors"], ["mexc", "kraken"])
        self.assertEqual(r["points"][0]["inter_source_skew_ms"], 2)

    def test_four_times_are_kept_distinct(self):
        src = self.result["points"][3]["sources"]["kraken"]
        instant = instants()[3]
        self.assertEqual(src["trade_ms"], instant - 698)
        self.assertEqual(src["first_received_ms"], instant - 100)
        self.assertEqual(src["trade_age_ms"], 698)
        self.assertEqual(src["receipt_lag_ms"], 598)
        self.assertEqual(self.result["points"][3]["instant_ms"], instant)

    def test_order_independent_and_hashed(self):
        shuffled = copy.deepcopy(self.trades)
        random.Random(7).shuffle(shuffled)
        other = compute(packet(shuffled))
        self.assertEqual(other["points"], self.result["points"])
        self.assertEqual(other["series"], self.result["series"])
        self.assertEqual(compute(packet(self.trades))["input_sha256"], self.result["input_sha256"])

    def test_spread_sign_positive_when_kraken_above_mexc(self):
        p = self.result["points"][0]
        self.assertEqual(p["spread_abs"], "2")
        self.assertEqual(p["spread_bps"], "0.32258065")  # 2/62000*1e4 = 0.322580645...
        below = compute(packet(series("mexc", 62002) + series("kraken", 62000)))
        self.assertEqual(below["points"][0]["spread_abs"], "-2")
        self.assertTrue(below["points"][0]["spread_bps"].startswith("-0.32257"))


class FreshnessAndTime(unittest.TestCase):
    def test_stale_source(self):
        kraken = series("kraken", 62002, skip=range(16, 30))
        r = compute(packet(series("mexc") + kraken))
        k = reasons(r, "kraken")
        self.assertEqual(k[:16], [None] * 16)
        self.assertEqual(set(k[16:]), {"STALE_TRADE"})
        self.assertEqual(r["series"]["composite"]["status"], "INCOMPLETE")
        self.assertIsNone(r["series"]["composite"]["ohlc"])
        self.assertEqual(r["series"]["single_venue"]["mexc"]["status"], "COMPLETE")
        self.assertEqual(r["points"][20]["status"], "SINGLE_VENUE_ONLY")
        self.assertEqual(r["points"][20]["pair_reason"], "SOURCE_EXCLUDED")
        self.assertTrue(validate_composite(r))

    def test_late_receipt_is_not_staleness(self):
        kraken = series("kraken", 62002)
        instant = instants()[10]
        kraken[10]["received_ms"] = instant + 300
        r = compute(packet(series("mexc") + kraken))
        self.assertEqual(r["points"][10]["sources"]["kraken"]["reason"], "LATE_RECEIPT")
        self.assertIsNone(r["points"][11]["sources"]["kraken"]["reason"])
        self.assertEqual(r["exclusions_by_venue"]["kraken"], {"LATE_RECEIPT": 1})
        # 29 valid points out of 30: no composite candle, the gap stays visible.
        self.assertEqual(r["series"]["composite"]["valid_points"], 29)
        self.assertEqual(r["series"]["composite"]["status"], "INCOMPLETE")
        self.assertIsNone(r["series"]["composite"]["ohlc"])
        self.assertTrue(validate_composite(r))

    def test_clock_inconsistency(self):
        kraken = series("kraken", 62002)
        instant = instants()[5]
        kraken[5].update(trade_ms=instant - 50 + 2_000, received_ms=instant - 50)
        r = compute(packet(series("mexc") + kraken))
        self.assertEqual(r["points"][5]["sources"]["kraken"]["reason"], "CLOCK_INCONSISTENT")
        self.assertEqual(r["exclusions_by_venue"]["kraken"], {"CLOCK_INCONSISTENT": 1})

    def test_two_fresh_trades_beyond_skew_tolerance(self):
        r = compute(packet(series("mexc", lag=100, receipt=50) +
                           series("kraken", 62002, lag=4_000, receipt=50),
                           max_inter_source_skew_ms=500))
        p = r["points"][0]
        self.assertEqual([s["state"] for s in p["sources"].values()], ["ELIGIBLE", "ELIGIBLE"])
        self.assertEqual(p["pair_reason"], "EVENTS_NOT_SYNCHRONIZED")
        self.assertEqual(p["inter_source_skew_ms"], 3_900)
        self.assertIsNone(p["spread_bps"])
        self.assertEqual(r["pair_exclusions"], {"EVENTS_NOT_SYNCHRONIZED": 30})
        self.assertEqual(r["series"]["single_venue"]["kraken"]["status"], "COMPLETE")

    def test_age_boundary_inclusive(self):
        r = compute(packet(series("mexc", lag=5_000) + series("kraken", 62002, lag=5_000)))
        self.assertEqual(r["series"]["composite"]["valid_points"], 30)
        r = compute(packet(series("mexc", lag=5_001) + series("kraken", 62002)))
        self.assertEqual(set(reasons(r, "mexc")), {"STALE_TRADE"})


class Outages(unittest.TestCase):
    def test_outage_in_the_middle(self):
        kraken = series("kraken", 62002, skip=range(12, 18))
        polls = [poll("kraken", i - 900, i - 400, "FETCH_ERROR", "HTTP_503") for i in instants()[12:18]]
        r = compute(packet(series("mexc") + kraken, polls))
        mid = r["points"][14]["sources"]["kraken"]
        self.assertEqual((mid["reason"], mid["last_poll_status"]), ("STALE_TRADE", "FETCH_ERROR"))
        self.assertEqual(r["series"]["composite"]["valid_points"], 24)
        self.assertEqual(r["series"]["composite"]["status"], "INCOMPLETE")
        self.assertEqual(r["counts"]["fetch_errors_by_venue"], {"mexc": 0, "kraken": 6})
        self.assertTrue(validate_composite(r))

    def test_failed_reads_from_start_are_fetch_errors_not_absence(self):
        polls = [poll("kraken", i - 900, i - 400, "FETCH_ERROR", "TIMEOUT") for i in instants()]
        r = compute(packet(series("mexc"), polls))
        self.assertEqual(set(reasons(r, "kraken")), {"FETCH_ERROR"})

    def test_mexc_only(self):
        r = compute(packet(series("mexc")))
        self.assertEqual(set(reasons(r, "kraken")), {"NO_OBSERVATION"})
        self.assertEqual(r["series"]["composite"]["valid_points"], 0)
        self.assertEqual(r["series"]["single_venue"]["mexc"]["status"], "COMPLETE")
        self.assertEqual(r["series"]["single_venue"]["mexc"]["label"], "MEXC seule · pas un composite")
        self.assertNotEqual(r["series"]["composite"]["label"], r["series"]["single_venue"]["mexc"]["label"])
        self.assertTrue(validate_composite(r))

    def test_kraken_only(self):
        r = compute(packet(series("kraken", 62002)))
        self.assertEqual(set(reasons(r, "mexc")), {"NO_OBSERVATION"})
        self.assertEqual(r["series"]["single_venue"]["kraken"]["status"], "COMPLETE")
        self.assertIsNone(r["series"]["single_venue"]["mexc"]["ohlc"])
        self.assertEqual(r["series"]["composite"]["status"], "INCOMPLETE")

    def test_no_source(self):
        r = compute(packet([]))
        self.assertEqual({p["status"] for p in r["points"]}, {"NO_ELIGIBLE_SOURCE"})
        for s in [r["series"]["composite"], *r["series"]["single_venue"].values()]:
            self.assertIsNone(s["ohlc"])
        self.assertTrue(validate_composite(r))

    def test_single_venue_coverage_is_never_called_composite(self):
        r = compute(packet(series("mexc"), venues=("mexc",)))
        self.assertEqual(r["series"]["composite"]["status"], "NOT_APPLICABLE_SINGLE_VENUE_COVERAGE")
        self.assertEqual(r["series"]["single_venue"]["mexc"]["status"], "COMPLETE")
        self.assertEqual(r["coverage"], {"kind": "SINGLE_VENUE", "venues": ["mexc"]})
        self.assertTrue(validate_composite(r))


class Duplicates(unittest.TestCase):
    def test_rereception_keeps_execution_time_and_first_receipt(self):
        mexc = series("mexc")
        again = dict(mexc[0], received_ms=instants()[20] - 10)
        r = compute(packet(mexc + series("kraken", 62002) + [again]))
        self.assertEqual(r["counts"]["duplicates_by_venue"], {"mexc": 1, "kraken": 0})
        self.assertEqual(r["counts"]["trades_unique"], 60)
        self.assertEqual(r["series"]["composite"]["valid_points"], 30)

    def test_rereception_never_rejuvenates_a_stale_trade(self):
        mexc = series("mexc", skip=range(1, 30))
        again = dict(mexc[0], received_ms=instants()[10] - 10)
        r = compute(packet(mexc + [again] + series("kraken", 62002)))
        src = r["points"][10]["sources"]["mexc"]
        self.assertEqual(src["reason"], "STALE_TRADE")
        self.assertEqual(src["trade_ms"], instants()[0] - 700)
        self.assertEqual(src["first_received_ms"], instants()[0] - 100)

    def test_conflicting_duplicate_refused(self):
        mexc = series("mexc")
        bad = dict(mexc[0], price="1")
        with self.assertRaises(ValueError):
            compute(packet(mexc + [bad]))

    def test_trades_without_id_use_native_symbol_in_key(self):
        a = trade("mexc", "62000", START - 700, START - 100)
        b = dict(a, received_ms=START - 50)
        r = compute(packet([a, b]))
        self.assertEqual(r["counts"]["duplicates_by_venue"]["mexc"], 1)


class Refusals(unittest.TestCase):
    def assert_refused(self, mutate):
        p = packet(series("mexc") + series("kraken", 62002))
        mutate(p)
        with self.assertRaises(ValueError):
            compute(p)

    def test_refusals(self):
        cases = {
            "mixed evidence": lambda p: p["trades"][0].update(evidence_kind="OBSERVATION"),
            "real packet with synthetic trades": lambda p: p.update(kind="OBSERVATION"),
            "foreign symbol": lambda p: p["trades"][0].update(native_symbol="BTCUSDC"),
            "usd instrument": lambda p: p["instrument"].update(quote_asset_id="USD", settlement_asset_id="USD"),
            "perpetual": lambda p: p["instrument"].update(market_kind="PERPETUAL_LINEAR"),
            "alias without evidence": lambda p: p["bindings"][1].update(alias_evidence=None),
            "unaligned window": lambda p: p.update(start_ms=START + 1),
            "implicit parameters": lambda p: p["parameters"].pop("max_inter_source_skew_ms"),
            "grid not M5": lambda p: p["parameters"].update(points=29),
            "zero price": lambda p: p["trades"][0].update(price="0"),
            "venue outside coverage": lambda p: p["trades"][0].update(venue="okx"),
            "poll without reason": lambda p: p["polls"].append(
                dict(poll("mexc", START - 10, START - 5), status="FETCH_ERROR")),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                self.assert_refused(mutate)


class PrototypeParity(unittest.TestCase):
    def test_v2_reproduces_v1_reference_fixture(self):
        v1 = json.loads(Path(__file__).with_name("btc_m5.json").read_text())
        expected = replay(v1)
        trades = []
        for row in v1["observations"]:
            venue = "mexc" if row["venue"] == "mexc" else "kraken"
            trades.append(trade(venue, row["price"], row["trade_ms"], row["received_ms"]))
        r = compute(packet(trades))
        self.assertEqual(r["series"]["composite"]["ohlc"], expected["ohlc"])
        self.assertEqual(r["series"]["composite"]["valid_points"], expected["valid_points"])
        self.assertEqual([p["composite_price"] for p in r["points"]],
                         [s["price"] for s in expected["samples"]])


if __name__ == "__main__":
    unittest.main()
