"""Offline trial of the BBO pilot: fake clock, synthetic venues, replay, schema, stops."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from observability.radar_composite import bbo_book as bk
from observability.radar_composite import bbo_pilot as bp
from observability.radar_composite import pilot as l3
from observability.radar_composite.bbo_schema import validate_bbo
from tests.radar_composite.test_bbo_wire import NoNetwork


def dry(pair="BTC", **kw):
    tmp = tempfile.TemporaryDirectory()
    out = Path(tmp.name) / "evidence"
    pilot, code = bp.dry_run(pair, out, **kw)
    return tmp, out, pilot, code


class DryRun(NoNetwork):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.out, cls.pilot, cls.code = dry("BTC")
        cls.summary = bp.replay(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_completes_within_budgets(self):
        m = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual((self.code, m["status"], m["stop_code"]), (0, "COMPLETED", None))
        self.assertLessEqual(m["elapsed_ms"], 780_000)
        for key, used in m["rest_used"].items():
            self.assertLessEqual(used, m["budget"]["rest"][key], key)
        self.assertEqual(m["window_start_ms"] % 300_000, 0)
        self.assertEqual(m["evidence_kind"], "SYNTHETIC")

    def test_breaks_are_detected_and_resolved(self):
        flux = self.summary["flux"]
        self.assertEqual([b["reason"] for b in flux["mexc"]["breaks"]], ["VERSION_GAP"])
        self.assertEqual([b["reason"] for b in flux["kraken"]["breaks"]], ["CHECKSUM_MISMATCH"])
        self.assertEqual((flux["mexc"]["unresolved_breaks"], flux["kraken"]["unresolved_breaks"]), (0, 0))
        self.assertEqual([j["outcome"] for j in flux["mexc"]["join_log"]], ["JOINED", "JOINED"])
        self.assertEqual(self.summary["resyncs"], {"mexc": 1, "kraken": 1})

    def test_complete_and_29_of_30_windows(self):
        w0, w1 = self.summary["windows"]
        self.assertEqual((w0["composite"], w0["candles"]["composite"]), (30, "COMPLETE"))
        self.assertEqual((w1["composite"], w1["candles"]["composite"]), (29, "INCOMPLETE"))
        self.assertEqual(w1["by_category"]["SINGLE_SOURCE"], 1)
        self.assertEqual(w1["by_source_state"]["kraken"]["FRESHNESS_UNKNOWN"], 1)
        pub = json.loads((self.out / "replay" / "window_1_primary.json").read_text())
        self.assertEqual(pub["candles"]["composite"]["open"], None)
        self.assertEqual(pub["candles"]["mexc"]["status"], "COMPLETE")  # mono-source series kept
        t = self.summary["totals"]
        self.assertEqual((t["composite"], t["evaluated"], t["complete_composite_candles"]), (59, 60, 1))
        self.assertEqual(t["verdict_pre_registered"], "COMPOSITE_VIABLE_AT_PRIMARY")

    def test_sensitivity_grid(self):
        w = self.summary["windows"][1]
        self.assertEqual(set(w["sensitivity_composite"]),
                         {f"L{ls}s_G{g}bps" for ls in (1, 2, 5, 10) for g in (10, 25, 50, 100)})
        self.assertEqual(w["sensitivity_composite"]["L2s_G50bps"], w["composite"])
        self.assertEqual(w["sensitivity_composite"]["L5s_G50bps"], 30)  # 4 s silence < 5 s
        self.assertEqual(set(w["sensitivity_flux_eligible"]), {"L1s", "L2s", "L5s", "L10s"})

    def test_replay_is_deterministic(self):
        first = {p.name: p.read_bytes() for p in (self.out / "replay").iterdir()}
        bp.replay(self.out)
        second = {p.name: p.read_bytes() for p in (self.out / "replay").iterdir()}
        self.assertEqual(first, second)

    def test_publications_validate(self):
        for w in range(2):
            pub = json.loads((self.out / "replay" / f"window_{w}_primary.json").read_text())
            self.assertEqual(validate_bbo(pub), [])

    def test_raw_frames_kept_with_receipt_times(self):
        lines = (self.out / "events.jsonl").read_text().splitlines()
        e = json.loads(lines[-1])
        self.assertTrue({"seq", "recv_wall_ms", "recv_mono_ms", "t_ms", "sha256", "offset", "bytes"} <= set(e))
        kinds = {json.loads(x)["kind"] for x in lines}
        self.assertTrue({"rest", "rest_depth", "ws_open", "ws_message", "sent"} <= kinds)


class Degraded(NoNetwork):
    def test_atom_reconnect_and_excessive_gap(self):
        tmp, out, _pilot, code = dry("ATOM")
        with tmp:
            s = bp.replay(out)
            self.assertEqual(code, 0)
            self.assertEqual(s["reconnects"]["mexc"], 1)
            self.assertEqual([b["reason"] for b in s["flux"]["mexc"]["breaks"]], ["DISCONNECTED"])
            w2 = s["windows"][2]
            self.assertGreaterEqual(w2["by_category"]["EXCESSIVE_GAP"], 25)
            self.assertEqual(w2["candles"]["composite"], "INCOMPLETE")
            self.assertEqual(w2["sensitivity_composite"]["L2s_G100bps"], 30)
            # Kraken ATOM rarely changes: heartbeats keep it verified, never fresher
            self.assertGreater(s["flux"]["kraken"]["of_which_unchanged_verified"], 0)


class Stops(NoNetwork):
    def test_frame_budget_stop_and_replay_marks_not_evaluated(self):
        tmp, out, _pilot, code = dry("BTC", caps={"max_frames": 400})
        with tmp:
            m = json.loads((out / "manifest.json").read_text())
            self.assertEqual((code, m["status"], m["stop_code"]), (2, "STOPPED", "BUDGET_FRAMES_EXHAUSTED"))
            s = bp.replay(out)
            self.assertEqual(s["totals"]["evaluated"], 0)
            self.assertEqual(s["windows"][0]["by_category"]["NOT_EVALUATED"], 30)
            self.assertEqual(s["totals"]["verdict_pre_registered"], "NO_EVALUATED_INSTANT")

    def test_mid_window_stop(self):
        tmp, out, _pilot, code = dry("BTC", caps={"max_frames": 2500})
        with tmp:
            s = bp.replay(out)
            self.assertEqual(code, 2)
            ev = s["totals"]["evaluated"]
            self.assertTrue(0 < ev < 60, ev)
            self.assertEqual(sum(w["by_category"]["NOT_EVALUATED"] for w in s["windows"]), 60 - ev)

    def test_resync_budget(self):
        prof = copy.deepcopy(bp.SIM_PROFILES["BTC"])
        prof["faults"] = [("kraken_bad_checksum", 0, 10_000 * k) for k in range(1, 6)]
        tmp, out, _pilot, code = dry("BTC", profile=prof)
        with tmp:
            m = json.loads((out / "manifest.json").read_text())
            self.assertEqual((code, m["stop_code"]), (2, "KRAKEN_RESYNC_BUDGET_EXHAUSTED"))
            self.assertEqual(m["resyncs"]["kraken"], 4)
            bp.replay(out)

    def test_http_stop(self):
        class Refusing(bp.FakeVenues):
            def rest(self, url):
                if url == self.depth_url:
                    return 429, {}, b"", "HTTP_429"
                return super().rest(url)
        clock = l3.FakeClock(bp.DRY_RUN_START_MS - 120_000)
        with tempfile.TemporaryDirectory() as d:
            p = bp.BboPilot("BTC", Path(d) / "e", Refusing("BTC", clock, start_ms=bp.DRY_RUN_START_MS),
                            clock, evidence_kind="SYNTHETIC")
            self.assertEqual(p.run(start_ms=bp.DRY_RUN_START_MS), 2)
            self.assertEqual(p.stop_code, "HTTP_429")

    def test_margin_refusal_is_a_preflight_stop(self):
        clock = l3.FakeClock(bp.DRY_RUN_START_MS - 120_000)
        with tempfile.TemporaryDirectory() as d:
            p = bp.BboPilot("BTC", Path(d) / "e", bp.FakeVenues("BTC", clock), clock,
                            evidence_kind="SYNTHETIC", radar_check=lambda: (False, "X"))
            code = p.run(start_ms=bp.DRY_RUN_START_MS)
            self.assertEqual((code, p.stop_code), (2, "MEXC_MARGIN_NOT_ESTABLISHED"))
            m = json.loads((Path(d) / "e" / "manifest.json").read_text())
            self.assertFalse(any(k.startswith("mexc.depth") and v for k, v in m["rest_used"].items()))

    def test_margin_check_reads_the_collector(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "collector.py"
            f.write_bytes(b"url = '/api/v3/klines'\n")
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            self.assertTrue(bp.bbo_margin_check(f, digest)()[0])
            self.assertEqual(bp.bbo_margin_check(f, "0" * 64)()[0], False)
            f.write_bytes(b"url = '/api/v3/depth'\n")
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            self.assertEqual(bp.bbo_margin_check(f, digest)(), (False, "RADAR_USES_DEPTH_ENDPOINT"))


class Evidence(NoNetwork):
    def setUp(self):
        super().setUp()
        self.tmp, self.out, _, _ = dry("BTC", caps={"max_frames": 900})
        self.addCleanup(self.tmp.cleanup)

    def _refused(self):
        with self.assertRaises(l3.Refused):
            bp.replay(self.out)

    def test_tampered_frame_byte(self):
        raw = bytearray((self.out / "frames.bin").read_bytes())
        raw[len(raw) // 2] ^= 1
        (self.out / "frames.bin").write_bytes(bytes(raw))
        self._refused()

    def test_removed_event_line(self):
        lines = (self.out / "events.jsonl").read_text().splitlines(keepends=True)
        del lines[10]
        (self.out / "events.jsonl").write_text("".join(lines))
        self._refused()

    def test_resealed_but_inconsistent_line(self):
        # An attacker re-sealing the manifest still breaks the per-frame hash.
        path = self.out / "events.jsonl"
        lines = path.read_text().splitlines(keepends=True)
        e = json.loads(lines[20])
        e["t_ms"] -= 5_000  # tries to make a frame look older
        lines[20] = json.dumps(e, sort_keys=True) + "\n"
        path.write_text("".join(lines))
        m = json.loads((self.out / "manifest.json").read_text())
        m["sealed"]["events_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.out / "manifest.json").write_text(json.dumps(m))
        self._refused()

    def test_unsealed_evidence_refused(self):
        m = json.loads((self.out / "manifest.json").read_text())
        m["sealed"] = None
        (self.out / "manifest.json").write_text(json.dumps(m))
        self._refused()

    def test_existing_directory_refused(self):
        with self.assertRaises(l3.Refused):
            bp.dry_run("BTC", self.out)


class Schema(NoNetwork):
    @classmethod
    def setUpClass(cls):
        cls.tmp, out, _, _ = dry("BTC")
        bp.replay(out)
        cls.pubs = [json.loads((out / "replay" / f"window_{w}_primary.json").read_text()) for w in range(2)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def bad(self, w, mutate):
        pub = copy.deepcopy(self.pubs[w])
        mutate(pub)
        return validate_bbo(pub)

    def test_rejections(self):
        def ohlc_on_incomplete(p):
            p["candles"]["composite"].update(open="1", high="1", low="1", close="1")

        def composite_on_single(p):
            pt = next(x for x in p["points"] if x["category"] == "SINGLE_SOURCE")
            pt["category"] = "COMPOSITE"

        def values_on_excluded(p):
            pt = next(x for x in p["points"] if x["category"] == "SINGLE_SOURCE")
            pt["sources"]["kraken"]["bid"] = "1"

        def wrong_mid(p):
            p["points"][0]["composite_mid"] = "1"

        def crossed(p):
            s = p["points"][0]["sources"]["mexc"]
            s["bid"], s["ask"] = s["ask"], s["bid"]

        def threshold(p):
            p["parameters"]["gap_max_bps"] = "1"

        cases = [(1, ohlc_on_incomplete, "composite:INCOMPLETE_HAS_OHLC"),
                 (1, composite_on_single, "CATEGORY_INCONSISTENT"),
                 (1, values_on_excluded, "VALUES_ON_EXCLUDED_SOURCE"),
                 (0, wrong_mid, "P0:COMPOSITE_MID"),
                 (0, crossed, "P0:mexc:CROSSED_OR_LOCKED"),
                 (0, threshold, "CATEGORY_INCONSISTENT")]
        for w, mutate, code in cases:
            errors = self.bad(w, mutate)
            self.assertTrue(any(code in e for e in errors), (code, errors[:4]))

    def test_extra_key_rejected(self):
        self.assertEqual(self.bad(0, lambda p: p.update(extra=1)), ["TOP_KEYS"])


class RuntimeLock(NoNetwork):
    def test_run_requires_the_confirmation_token(self):
        with tempfile.TemporaryDirectory() as d:
            code = bp.main(["run", "--pair", "BTC", "--out", str(Path(d) / "e"),
                            "--radar-collector", "/nonexistent", "--radar-collector-sha256", "0" * 64,
                            "--confirm-public-collection", "yes"])
            self.assertEqual(code, 4)
            self.assertFalse((Path(d) / "e").exists())

    def test_websocket_allow_list(self):
        with self.assertRaises(l3.Refused):
            bp.WsConnection("wss://example.invalid/ws")

    def test_rest_allow_list_is_closed(self):
        urls = set(bp.rest_urls("BTC").values())
        self.assertEqual(len(urls), 6)
        self.assertIn("https://api.mexc.com/api/v3/depth?symbol=BTCUSDT&limit=5000", urls)
        self.assertFalse(any("trades" in u for u in urls))

    def test_cli_dry_run_and_replay(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(bp.main(["dry-run", "--pair", "BTC", "--out", str(Path(d) / "e")]), 0)
            self.assertEqual(bp.main(["replay", str(Path(d) / "e")]), 0)

    def test_states_and_categories_are_closed_sets(self):
        self.assertEqual(len(bk.SOURCE_STATES), 7)
        self.assertEqual(len(bk.CATEGORIES), 5)


if __name__ == "__main__":
    unittest.main()
