import json
import unittest

from observability.radar_composite.composite import compute
from observability.radar_composite.decoders import (
    decode_kraken_trades, decode_mexc_trades, poll_record,
)
from tests.radar_composite._factory import (
    KRAKEN, MEXC, instants, kraken_payload, mexc_payload, packet,
)

MEXC_ROWS = [
    {"id": None, "price": "62000.10", "qty": "0.002", "quoteQty": "124.0002",
     "time": 1795127999300, "isBuyerMaker": True, "isBestMatch": True, "tradeType": "ASK"},
    {"id": 123456, "price": "62000.20", "qty": "0.001", "quoteQty": "62.0002",
     "time": 1795127999400, "isBuyerMaker": False, "isBestMatch": True, "tradeType": "BID"},
]
KRAKEN_RAW = (
    b'{"error":[],"result":{"XBTUSDT":[["62002.50000","0.00047913",1795127999.3021,'
    b'"b","l","",98765]],"last":"1795127999302112345"}}'
)


class Mexc(unittest.TestCase):
    def decode(self, raw=None, **kw):
        args = dict(binding=MEXC, requested_symbol="BTCUSDT", received_ms=1795127999900,
                    evidence_kind="OBSERVATION")
        args.update(kw)
        return decode_mexc_trades(mexc_payload(MEXC_ROWS) if raw is None else raw, **args)

    def test_decodes_native_rows(self):
        a, b = self.decode()
        self.assertEqual((a["price"], a["trade_ms"], a["trade_id"], a["side"]),
                         ("62000.10", 1795127999300, None, "sell"))
        self.assertEqual((b["trade_id"], b["side"]), ("123456", "buy"))
        self.assertEqual(a["identity_evidence"], "REQUEST_CONTEXT")
        self.assertEqual((a["venue"], a["provider"]), ("mexc", "mexc"))
        self.assertEqual(len(a["payload_sha256"]), 64)

    def test_response_tied_to_requested_symbol(self):
        with self.assertRaises(ValueError):
            self.decode(requested_symbol="ETHUSDT")
        with self.assertRaises(ValueError):
            self.decode(binding=KRAKEN)

    def test_ticker_payload_is_not_a_trade(self):
        ticker = json.dumps({"symbol": "BTCUSDT", "lastPrice": "62000", "closeTime": 1795127999000})
        with self.assertRaises(ValueError):
            self.decode(ticker.encode())

    def test_strict_json(self):
        for raw in (b'[{"price":"1","price":"2"}]', b'[{"price":NaN}]', b"[" + b" " * 600_000 + b"]",
                    mexc_payload([{**MEXC_ROWS[0], "price": "-1"}]),
                    mexc_payload([{**MEXC_ROWS[0], "time": True}])):
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(ValueError):
                    self.decode(raw)

    def test_evidence_kind_explicit(self):
        with self.assertRaises(ValueError):
            self.decode(evidence_kind="LIVE")


class Kraken(unittest.TestCase):
    def decode(self, raw=KRAKEN_RAW, **kw):
        args = dict(binding=KRAKEN, requested_pair="XBTUSDT", received_ms=1795127999900,
                    evidence_kind="OBSERVATION")
        args.update(kw)
        return decode_kraken_trades(raw, **args)

    def test_decodes_native_key_and_exact_time(self):
        (t,) = self.decode()
        self.assertEqual((t["price"], t["qty"], t["side"], t["trade_id"]),
                         ("62002.50000", "0.00047913", "buy", "98765"))
        self.assertEqual(t["native_time"], "1795127999.3021")
        self.assertEqual(t["trade_ms"], 1795127999302)
        self.assertEqual(t["identity_evidence"], "NATIVE_KEY_ECHO")
        self.assertEqual(t["native_symbol"], "XBTUSDT")

    def test_foreign_or_extra_key_refused(self):
        for raw in (KRAKEN_RAW.replace(b"XBTUSDT", b"ETHUSDT"),
                    kraken_payload("XBTUSDT", []).replace(b'"last"', b'"XBTUSD":[],"last"'),
                    b'{"error":["EGeneral:Too many requests"],"result":{}}'):
            with self.subTest(raw=raw[:40]):
                with self.assertRaises(ValueError):
                    self.decode(raw)
        with self.assertRaises(ValueError):
            self.decode(requested_pair="XBTUSD")

    def test_row_shape(self):
        bad = KRAKEN_RAW.replace(b'"b"', b'"x"')
        with self.assertRaises(ValueError):
            self.decode(bad)


class Polls(unittest.TestCase):
    def test_fetch_error_needs_reason(self):
        with self.assertRaises(ValueError):
            poll_record(MEXC, provider="mexc", requested_ms=1, received_ms=2, status="FETCH_ERROR")
        p = poll_record(MEXC, provider="mexc", requested_ms=1, received_ms=2,
                        status="FETCH_ERROR", reason="HTTP_429")
        self.assertEqual(p["reason"], "HTTP_429")
        with self.assertRaises(ValueError):
            poll_record(MEXC, provider="mexc", requested_ms=3, received_ms=2, status="OK")


class EndToEnd(unittest.TestCase):
    def test_decoded_payloads_feed_the_composite(self):
        trades = []
        for k, instant in enumerate(instants()):
            m = [{"id": None, "price": str(62000 + k), "qty": "0.01", "quoteQty": "1",
                  "time": instant - 700, "isBuyerMaker": False}]
            trades += decode_mexc_trades(mexc_payload(m), binding=MEXC, requested_symbol="BTCUSDT",
                                         received_ms=instant - 100, evidence_kind="SYNTHETIC")
            seconds = (instant - 698) / 1000
            raw = kraken_payload("XBTUSDT", [[str(62002 + k), "0.01", seconds, "s", "m", "", 1000 + k]])
            trades += decode_kraken_trades(raw, binding=KRAKEN, requested_pair="XBTUSDT",
                                           received_ms=instant - 100, evidence_kind="SYNTHETIC")
        r = compute(packet(trades))
        self.assertEqual(r["series"]["composite"]["status"], "COMPLETE")
        self.assertEqual(r["series"]["composite"]["ohlc"]["open"], "62001")

    def test_real_decoded_trades_cannot_enter_a_synthetic_packet(self):
        real = decode_mexc_trades(mexc_payload(MEXC_ROWS), binding=MEXC, requested_symbol="BTCUSDT",
                                  received_ms=1795127999900, evidence_kind="OBSERVATION")
        with self.assertRaises(ValueError):
            compute(packet(real, kind="SYNTHETIC"))


if __name__ == "__main__":
    unittest.main()
