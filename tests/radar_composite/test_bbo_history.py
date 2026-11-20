"""BBO composite history publication: builder, validator, Operator API reader and GET route.

Synthetic data only: dry-run evidence built in a temporary directory and the
committed synthetic fixture. No network, no VPS, no real evidence.
"""
import copy
import json
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from observability.operator_api.bbo_history_reader import BboHistoryReader
from observability.radar_composite import bbo_history as h
from observability.radar_composite import bbo_pilot as bp

FIXTURE = Path(__file__).resolve().parents[2] / "observability/radar_composite/fixtures/bbo_composite_history_synthetic.json"
NOW = datetime(2026, 11, 20, 8, 0, 0, tzinfo=timezone.utc)


def _dry(tmp, pair):
    out = Path(tmp) / f"BBO-{pair}-DRY"
    bp.dry_run(pair, out)
    bp.replay(out)
    archive = Path(tmp) / f"BBO-{pair}-DRY.tar.gz"
    with tarfile.open(archive, "w:gz") as t:
        t.add(out, arcname=out.name)
    return out, archive


class Builder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.btc = _dry(cls.tmp.name, "BTC")
        cls.atom = _dry(cls.tmp.name, "ATOM")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_publication_copies_replayed_values_without_recomputation(self):
        doc = h.build([self.btc[0], self.atom[0]], [self.btc[1], self.atom[1]], "R", now=NOW)
        self.assertEqual(h.validate_history(doc), [])
        self.assertEqual([p["pair"] for p in doc["pairs"]], ["BTC", "ATOM"])
        btc = doc["pairs"][0]
        summary = json.loads((self.btc[0] / "replay" / "summary.json").read_text())
        self.assertEqual({k: btc["coverage"][k] for k in ("planned", "evaluated", "composite")},
                         {k: summary["totals"][k] for k in ("planned", "evaluated", "composite")})
        for w in btc["windows"]:
            pub = json.loads((self.btc[0] / "replay" / f"window_{w['index']}_primary.json").read_text())
            self.assertEqual(w["candle"], pub["candles"]["composite"])  # exact strings, untouched
            self.assertEqual(w["venue_candles"], {v: pub["candles"][v] for v in ("mexc", "kraken")})
        self.assertEqual(doc["label"], "Composite de milieux de carnet · Spot · Historique")
        self.assertEqual(doc["evidence_kind"], "SYNTHETIC")

    def test_incomplete_candle_publishes_no_invented_ohlc(self):
        doc = h.build([self.btc[0]], [self.btc[1]], "R", now=NOW)
        incomplete = [w["candle"] for w in doc["pairs"][0]["windows"] if w["candle"]["status"] == "INCOMPLETE"]
        self.assertTrue(incomplete)
        self.assertTrue(all(c[k] is None for c in incomplete for k in ("open", "high", "low", "close")))

    def test_tampered_evidence_or_mismatched_archive_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, archive = _dry(tmp, "BTC")
            with self.assertRaises(h.HistoryError):
                h.build([out], [self.atom[1]], "R", now=NOW)
            with open(out / "events.jsonl", "ab") as f:
                f.write(b"\n")
            with self.assertRaises(h.HistoryError):
                h.build([out], [archive], "R", now=NOW)

    def test_window_publication_disagreeing_with_summary_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, archive = _dry(tmp, "BTC")
            p = out / "replay" / "window_0_primary.json"
            pub = json.loads(p.read_text())
            pub["window"]["start_ms"] += 1
            p.write_text(json.dumps(pub))
            with self.assertRaises(h.HistoryError):
                h.build([out], [archive], "R", now=NOW)


class Validator(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(FIXTURE.read_text())

    def test_committed_fixture_is_valid_and_synthetic(self):
        self.assertEqual(h.validate_history(self.doc), [])
        self.assertEqual(self.doc["evidence_kind"], "SYNTHETIC")

    def test_arithmetic_and_flag_invariants(self):
        cases = {
            "count": lambda d: d["pairs"][0]["coverage"].update(composite=60),
            "category": lambda d: d["pairs"][0]["windows"][0]["by_category"].update(COMPOSITE=31),
            "candle": lambda d: d["pairs"][0]["windows"][0]["candle"].update(high="1"),
            "invented_ohlc": lambda d: d["pairs"][0]["windows"][1]["candle"].update(open="1", high="1", low="1", close="1"),
            "a_order": lambda d: d["pairs"][1]["hypotheses"]["A_ORDER"].update(majority_unchanged_verified=False),
            "sensitivity": lambda d: d["pairs"][1]["sensitivity_composite_totals"].update(L2s_G10bps=90),
            "extra_field": lambda d: d["pairs"][0].update(score=1),
            "provenance": lambda d: d["pairs"][0]["provenance"].update(archive_sha256="x"),
            "order": lambda d: d["pairs"][0]["windows"].reverse(),
            "label": lambda d: d.update(label="Live"),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                doc = copy.deepcopy(self.doc)
                mutate(doc)
                self.assertTrue(h.validate_history(doc), name)


class Reader(unittest.TestCase):
    def test_unconfigured_missing_malformed_and_invalid_are_typed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(BboHistoryReader("").read().error_code, "BBO_HISTORY_NOT_CONFIGURED")
            self.assertEqual(BboHistoryReader(str(Path(tmp) / "none.json")).read().error_code, "BBO_HISTORY_MISSING")
            bad = Path(tmp) / "bad.json"
            bad.write_text('{"a": 1, "a": 2}')
            self.assertEqual(BboHistoryReader(str(bad)).read().error_code, "BBO_HISTORY_MALFORMED_JSON")
            doc = json.loads(FIXTURE.read_text())
            doc["pairs"][0]["coverage"]["composite"] += 1
            bad.write_text(json.dumps(doc))
            self.assertEqual(BboHistoryReader(str(bad)).read().error_code, "BBO_HISTORY_INVALID_SCHEMA")
            big = Path(tmp) / "big.json"
            big.write_bytes(b" " * 200_001)
            self.assertEqual(BboHistoryReader(str(big)).read().error_code, "BBO_HISTORY_TOO_LARGE")
            link = Path(tmp) / "link.json"
            link.symlink_to(FIXTURE)
            self.assertEqual(BboHistoryReader(str(link)).read().error_code, "BBO_HISTORY_INVALID_PATH")

    def test_served_unchanged_with_historical_serving_label(self):
        r = BboHistoryReader(str(FIXTURE)).read()
        self.assertTrue(r.ok)
        served = {k: v for k, v in r.snapshot.items() if k != "serving"}
        self.assertEqual(served, json.loads(FIXTURE.read_text()))
        self.assertEqual(r.snapshot["serving"], {"freshness_classification": "HISTORICAL_NOT_LIVE"})


class Route(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:  # pragma: no cover - fastapi is a CI dependency
            self.skipTest("fastapi not installed")
        from observability.operator_api import app as api
        self.api, self.client = api, TestClient(api.app)
        self.addCleanup(api.configure_bbo_history_reader, None)

    def test_get_only_route_serves_publication_or_typed_503(self):
        url = "/api/operator/v1/bbo-composite-history"
        self.api.configure_bbo_history_reader("")
        res = self.client.get(url)
        self.assertEqual((res.status_code, res.json()), (503, {"error_code": "BBO_HISTORY_NOT_CONFIGURED"}))
        self.assertEqual(res.headers["cache-control"], "no-store")
        self.api.configure_bbo_history_reader(str(FIXTURE))
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["pairs"][0]["pair"], "BTC")
        self.assertEqual(self.client.post(url).status_code, 405)


if __name__ == "__main__":
    unittest.main()
