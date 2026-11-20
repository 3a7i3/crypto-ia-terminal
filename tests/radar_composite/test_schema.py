"""Regressions found in review of 47d0365: the validator accepted invalid publications."""
import copy
import unittest

from observability.radar_composite.composite import compute
from observability.radar_composite.schema import validate_composite
from tests.radar_composite._factory import packet, series


def published(**kw):
    return compute(packet(series("mexc") + series("kraken", 62002, lag=698), **kw))


class ContributorsMustBeEligible(unittest.TestCase):
    """Regression 1: a COMPOSITE point whose contributor is EXCLUDED was accepted."""

    def test_excluded_contributor_rejected(self):
        doc = published()
        self.assertTrue(validate_composite(doc))
        bad = copy.deepcopy(doc)
        bad["points"][0]["sources"]["kraken"].update(state="EXCLUDED", reason="STALE_TRADE")
        bad["series"]["single_venue"]["kraken"].update(valid_points=29, status="INCOMPLETE", ohlc=None)
        self.assertFalse(validate_composite(bad))

    def test_contributors_must_match_coverage(self):
        bad = copy.deepcopy(published())
        bad["points"][0]["contributors"] = ["mexc"]
        self.assertFalse(validate_composite(bad))

    def test_composite_point_beyond_skew_rejected(self):
        bad = copy.deepcopy(published())
        bad["parameters"]["max_inter_source_skew_ms"] = 1
        self.assertFalse(validate_composite(bad))


class OhlcAndNumbers(unittest.TestCase):
    """Regression 2: malformed OHLC and non-contract numbers were accepted."""

    def test_composite_and_single_venue_ohlc(self):
        doc = published()
        cases = {
            "non numeric": lambda c: c.update(open="abc"),
            "missing key": lambda c: c.pop("close"),
            "extra key": lambda c: c.update(volume="1"),
            "negative": lambda c: c.update(high="-1"),
            "exponent": lambda c: c.update(open="6.2001E+4"),
            "number not string": lambda c: c.update(open=62001),
            "high below low": lambda c: c.update(high="1"),
            "differs from sampled points": lambda c: c.update(close="62028"),
        }
        for path in (("composite",), ("single_venue", "mexc"), ("single_venue", "kraken")):
            for name, mutate in cases.items():
                with self.subTest(series=path, case=name):
                    bad = copy.deepcopy(doc)
                    target = bad["series"]
                    for key in path:
                        target = target[key]
                    mutate(target["ohlc"])
                    self.assertFalse(validate_composite(bad))
                    target["ohlc"] = None
                    self.assertFalse(validate_composite(bad), "COMPLETE without OHLC")

    def test_point_numbers(self):
        doc = published()
        cases = {
            "composite NaN": ("composite_price", "NaN"),
            "composite zero": ("composite_price", "0"),
            "spread_abs text": ("spread_abs", "two"),
            "spread_bps not 8 decimals": ("spread_bps", "0.32"),
            "skew float": ("inter_source_skew_ms", 2.0),
        }
        for name, (field, value) in cases.items():
            with self.subTest(name):
                bad = copy.deepcopy(doc)
                bad["points"][0][field] = value
                self.assertFalse(validate_composite(bad))

    def test_source_numbers_and_times(self):
        doc = published()
        cases = {
            "price NaN": ("price", "NaN"),
            "trade_ms bool": ("trade_ms", True),
            "age inconsistent": ("trade_age_ms", 1),
            "received after instant": ("first_received_ms", doc["points"][0]["instant_ms"] + 1),
        }
        for name, (field, value) in cases.items():
            with self.subTest(name):
                bad = copy.deepcopy(doc)
                bad["points"][0]["sources"]["mexc"][field] = value
                self.assertFalse(validate_composite(bad))

    def test_incomplete_series_cannot_carry_ohlc(self):
        doc = compute(packet(series("mexc") + series("kraken", 62002, skip=range(16, 30))))
        self.assertTrue(validate_composite(doc))
        bad = copy.deepcopy(doc)
        bad["series"]["composite"]["ohlc"] = {"open": "1", "high": "1", "low": "1", "close": "1"}
        self.assertFalse(validate_composite(bad))

    def test_single_venue_coverage(self):
        doc = compute(packet(series("mexc"), venues=("mexc",)))
        self.assertTrue(validate_composite(doc))
        bad = copy.deepcopy(doc)
        bad["series"]["single_venue"]["mexc"]["ohlc"]["low"] = "x"
        self.assertFalse(validate_composite(bad))


if __name__ == "__main__":
    unittest.main()
