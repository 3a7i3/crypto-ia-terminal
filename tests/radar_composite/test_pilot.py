"""Offline trial of the L3 pilot: fake clock and synthetic venues, no network."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from observability.radar_composite import pilot
from observability.radar_composite.pilot import (
    DRY_RUN_PROFILES, PAIRS, FakeClock, FakeExchanges, Pilot, Refused,
    UrllibTransport, planned_requests, radar_margin_check, replay, urls,
)
from observability.radar_composite.schema import validate_composite

T0 = 1_795_128_000_000 - 120_000


def run(pair="BTC", script=None, radar_check=None, pairs=None, **profile):
    tmp = tempfile.TemporaryDirectory()
    out = Path(tmp.name) / "evidence"
    clock = FakeClock(T0)
    venues = FakeExchanges(pair, clock, script=script, **(profile or DRY_RUN_PROFILES[pair]))
    with mock.patch.dict(pilot.PAIRS, pairs or {}):
        p = Pilot(pair, out, venues, clock, evidence_kind="SYNTHETIC", radar_check=radar_check)
        code = p.run()
    return tmp, out, p, code


class Budgets(unittest.TestCase):
    def test_btc_completes_within_budget(self):
        tmp, out, p, code = run("BTC")
        with tmp:
            m = json.loads((out / "manifest.json").read_text())
            self.assertEqual((code, m["status"], m["stop_code"]), (0, "COMPLETED", None))
            self.assertEqual(p.seq, planned_requests("BTC"))
            self.assertEqual(p.seq, 129)
            self.assertLessEqual(p.seq, 150)
            self.assertLessEqual(m["elapsed_ms"], 720_000)
            self.assertEqual(m["window_start_ms"] % 300_000, 0)
            s = replay(out)
            self.assertEqual(s["totals"]["planned"], 60)
            self.assertEqual(s["totals"]["evaluated"], 60)
            for w in range(2):
                pub = json.loads((out / "replay" / f"window_{w}_primary.json").read_text())
                self.assertTrue(validate_composite(pub))
                self.assertEqual(pub["evidence_kind"], "SYNTHETIC")

    def test_atom_sparse_profile(self):
        tmp, out, p, code = run("ATOM")
        with tmp:
            self.assertEqual((code, p.seq), (0, 189))
            self.assertLessEqual(p.seq, 220)
            s = replay(out)
            self.assertEqual(s["totals"]["planned"], 90)
            for w in s["windows"]:
                cats = w["instants_by_category"]
                self.assertEqual(sum(cats.values()), 30, "an instant is counted once")
                self.assertIn("STALE_TRADE", w["source_reasons"]["kraken"])
                age = [w["sensitivity"]["age_varies_skew_fixed_5s"][f"{a}s"] for a in (5, 10, 30, 60)]
                self.assertEqual(age, sorted(age), "a looser age never loses instants")
                self.assertEqual(age[0], w["comparable"])
            self.assertLess(s["totals"]["comparable"], s["totals"]["evaluated"])

    def test_request_budget_stop(self):
        small = {"BTC": {**PAIRS["BTC"], "max_requests": 50}}
        tmp, out, p, code = run("BTC", pairs=small)
        with tmp:
            self.assertEqual((code, p.stop_code, p.seq), (2, "BUDGET_REQUESTS_EXHAUSTED", 50))
            s = replay(out)
            self.assertLess(s["totals"]["evaluated"], 60)
            self.assertEqual(s["totals"]["planned"], 60)

    def test_duration_stop(self):
        short = {"BTC": {**PAIRS["BTC"], "max_seconds": 120}}
        tmp, out, p, code = run("BTC", pairs=short)
        with tmp:
            self.assertEqual((code, p.stop_code), (2, "BUDGET_DURATION_EXHAUSTED"))


class StopConditions(unittest.TestCase):
    def test_http_429_stops_immediately(self):
        tmp, out, p, code = run("BTC", script={20: (429, b"{}")})
        with tmp:
            self.assertEqual((code, p.stop_code, p.seq), (2, "HTTP_429", 20))
            lines = (out / "requests.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 20)
            s = replay(out)
            self.assertEqual(s["status"], "STOPPED")
            self.assertGreater(s["windows"][0]["instants_by_category"]["NOT_EVALUATED"], 0)

    def test_403_and_418(self):
        for status in (403, 418):
            tmp, out, p, code = run("BTC", script={7: (status, b"")})
            with tmp:
                self.assertEqual(p.stop_code, f"HTTP_{status}")

    def test_three_consecutive_failures(self):
        tmp, out, p, code = run("BTC", script={8: (None, b""), 9: (500, b""), 10: (None, b"")})
        with tmp:
            self.assertEqual((p.stop_code, p.seq), ("THREE_CONSECUTIVE_FAILURES", 10))

    def test_failures_not_consecutive_continue(self):
        tmp, out, p, code = run("BTC", script={8: (None, b""), 10: (None, b"")})
        with tmp:
            self.assertEqual(code, 0)
            s = replay(out)
            self.assertEqual(s["totals"]["evaluated"], 60)

    def test_kraken_rate_limit_body(self):
        body = b'{"error":["EGeneral:Too many requests"],"result":{}}'
        tmp, out, p, code = run("BTC", script={9: (200, body)})
        with tmp:
            self.assertEqual(p.stop_code, "KRAKEN_RATE_LIMIT")

    def test_margin_not_established_sends_nothing(self):
        tmp, out, p, code = run("BTC", radar_check=lambda: (False, "RADAR_COLLECTOR_CHANGED"))
        with tmp:
            self.assertEqual((code, p.stop_code, p.seq), (2, "MEXC_MARGIN_NOT_ESTABLISHED", 0))

    def test_preflight_identity(self):
        info = json.dumps({"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
                                        "status": "2", "isSpotTradingAllowed": False}]}).encode()
        tmp, out, p, code = run("BTC", script={2: (200, info)})
        with tmp:
            self.assertEqual((code, p.stop_code), (3, "PREFLIGHT_MEXC_IDENTITY"))
        pairs = json.dumps({"error": [], "result": {"XBTUSD": {"altname": "XBTUSD", "base": "XXBT",
                                                               "status": "online"}}}).encode()
        tmp, out, p, code = run("BTC", script={4: (200, pairs)})
        with tmp:
            self.assertEqual(p.stop_code, "PREFLIGHT_KRAKEN_IDENTITY")


class Evidence(unittest.TestCase):
    def test_context_kept_and_tamper_detected(self):
        tmp, out, p, code = run("BTC")
        with tmp:
            first = json.loads((out / "requests.jsonl").read_text().splitlines()[0])
            for key in ("url", "status", "sent_ms", "received_ms", "body_sha256", "venue", "endpoint"):
                self.assertIn(key, first)
            m = json.loads((out / "manifest.json").read_text())
            self.assertIn("pilot.py", m["code"]["files_sha256"])
            self.assertEqual(m["parameters_primary"]["max_inter_source_skew_ms"], 5000)
            self.assertEqual(m["budget"]["planned_requests"], 129)
            raw = out / first["body_file"]
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), first["body_sha256"])
            raw.write_bytes(b"tampered")
            with self.assertRaises(Refused):
                replay(out)

    def test_replay_is_deterministic_and_counts_rereceptions(self):
        tmp, out, p, code = run("BTC")
        with tmp:
            a = replay(out)
            b = replay(out)
            self.assertEqual(a, b)
            pub = json.loads((out / "replay" / "window_0_primary.json").read_text())
            self.assertGreater(pub["counts"]["duplicates_by_venue"]["kraken"], 0)

    def test_existing_evidence_dir_refused(self):
        tmp, out, p, code = run("BTC")
        with tmp:
            with self.assertRaises(Refused):
                Pilot("BTC", out, None, FakeClock(T0))

    def test_polls_precede_instants(self):
        tmp, out, p, code = run("BTC")
        with tmp:
            for line in (out / "requests.jsonl").read_text().splitlines():
                e = json.loads(line)
                if e["endpoint"] == "trades":
                    instant = int(e["purpose"].split("@")[1])
                    # MEXC first, then Kraken; both answered before the instant.
                    self.assertGreaterEqual(e["sent_ms"], instant - 1500)
                    self.assertLess(e["received_ms"], instant)


class AllowList(unittest.TestCase):
    def test_transport_refuses_unlisted_urls(self):
        t = UrllibTransport(urls("BTC").values())
        with self.assertRaises(Refused):
            t("https://api.mexc.com/api/v3/order")

    def test_endpoints_are_public_get_only(self):
        for u in list(urls("BTC").values()) + list(urls("ATOM").values()):
            self.assertTrue(u.startswith(("https://api.mexc.com/api/v3/", "https://api.kraken.com/0/public/")))

    def test_radar_margin_check(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "collector.py"
            f.write_bytes(b'ALLOWED = {"/api/v3/time": set()}')
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            self.assertTrue(radar_margin_check(f, digest)()[0])
            self.assertEqual(radar_margin_check(f, "0" * 64)()[0], False)
            f.write_bytes(b'"/api/v3/trades"')
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            self.assertEqual(radar_margin_check(f, digest)(), (False, "RADAR_USES_TRADES_ENDPOINT"))
            self.assertEqual(radar_margin_check(Path(d) / "absent", digest)()[0], False)


if __name__ == "__main__":
    unittest.main()
