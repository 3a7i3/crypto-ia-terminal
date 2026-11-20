import json
import unittest
from pathlib import Path

from observability.radar_composite.m5 import replay


class CompositeTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads(Path(__file__).with_name("btc_m5.json").read_text())
        self.rows = self.packet["observations"]

    def test_exact_and_reproducible(self):
        result = replay(self.packet)
        self.assertEqual(result["ohlc"], dict(open="62001", high="62007", low="62001", close="62002"))
        self.assertEqual(result["valid_points"], 30)
        self.rows.reverse()
        self.assertEqual(result, replay(self.packet))

    def test_stale_even_if_just_received(self):
        self.rows[1]["trade_ms"] = self.rows[1]["slot_ms"] - 5001
        result = replay(self.packet)
        self.assertEqual(result["valid_points"], 29)
        self.assertEqual(result["gaps"][0]["excluded"], {"okx": "STALE_TRADE"})
        self.assertIsNone(result["ohlc"])

    def test_missing(self):
        self.rows.pop()
        result = replay(self.packet)
        self.assertEqual(result["gaps"][0]["excluded"], {"okx": "MISSING"})
        self.assertIsNone(result["ohlc"])

    def test_age_boundary_and_half_tick(self):
        self.rows[0].update(trade_ms=self.rows[0]["slot_ms"] - 5000, price="62000.00000001")
        self.assertEqual(replay(self.packet)["ohlc"]["open"], "62001.000000005")

    def test_duplicate(self):
        self.rows.append(self.rows[0])
        with self.assertRaises(ValueError):
            replay(self.packet)

    def test_incompatible_or_invalid(self):
        for field, value in (("symbol","BTC-USD"),("market","swap"),("price_kind","bid"),
                             ("price","NaN"),("price","0"),("trade_ms",None),
                             ("received_ms",self.rows[0]["slot_ms"]+1)):
            with self.subTest(field=field):
                old = self.rows[0][field]
                self.rows[0][field] = value
                with self.assertRaises(ValueError):
                    replay(self.packet)
                self.rows[0][field] = old

    def test_no_sources(self):
        self.rows.clear()
        result = replay(self.packet)
        self.assertEqual(len(result["gaps"]), 30)
        self.assertIsNone(result["ohlc"])
