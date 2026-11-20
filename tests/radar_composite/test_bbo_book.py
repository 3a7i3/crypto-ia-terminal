"""Offline tests of the BBO books, per-instant states, composite and candles."""
import json
import unittest
from decimal import Decimal

from observability.radar_composite import bbo_book as bk
from observability.radar_composite import bbo_wire as wire
from tests.radar_composite.test_bbo_wire import NoNetwork

CH = "spot@public.aggre.depth.v3.api.pb@100ms@BTCUSDT"

# Official example of the Kraken WS v2 checksum guide (BTC/USD), checksum 3310070434.
KRAKEN_BIDS = [("45283.5", "0.10000000"), ("45283.4", "1.54582015"), ("45282.1", "0.10000000"),
               ("45281.0", "0.10000000"), ("45280.3", "1.54592586"), ("45279.0", "0.07990000"),
               ("45277.6", "0.03310103"), ("45277.5", "0.30000000"), ("45277.3", "1.54602737"),
               ("45276.6", "0.15445238")]
KRAKEN_ASKS = [("45285.2", "0.00100000"), ("45286.4", "1.54571953"), ("45286.6", "1.54571109"),
               ("45289.6", "1.54560911"), ("45290.2", "0.15890660"), ("45291.8", "1.54553491"),
               ("45294.7", "0.04454749"), ("45296.1", "0.35380000"), ("45297.5", "0.09945542"),
               ("45299.5", "0.18772827")]
KRAKEN_OFFICIAL_CHECKSUM = 3310070434


class Feed:
    """Builds recorded-like events for an Engine."""

    def __init__(self, symbol="BTC/USD"):
        self.engine = bk.Engine("BTCUSDT", CH, symbol)
        self.seq = 0
        self.actions = []

    def ev(self, t, venue, kind, payload=b"", opcode=None, status=None):
        self.seq += 1
        e = {"seq": self.seq, "t_ms": t, "venue": venue, "kind": kind, "payload": payload,
             "opcode": opcode, "status": status}
        self.actions += self.engine.apply(e)
        return e

    def mexc_diff(self, t, frm, to, bids=(), asks=()):
        body = wire.encode_aggre_depths(list(asks), list(bids), frm, to)
        return self.ev(t, "mexc", "ws_message", wire.encode_mexc_push(CH, "BTCUSDT", body), wire.OP_BINARY)

    def mexc_snapshot(self, t, last, bids, asks, status=200):
        return self.ev(t, "mexc", "rest_depth", json.dumps(
            {"lastUpdateId": last, "bids": [list(b) for b in bids], "asks": [list(a) for a in asks]}).encode(),
            status=status)

    def mexc_pong(self, t):
        return self.ev(t, "mexc", "ws_message", b'{"id":0,"code":0,"msg":"PONG"}', wire.OP_TEXT)

    def kraken(self, t, kind, bids, asks, checksum=None, symbol="BTC/USD"):
        if checksum is None:
            checksum = self.expected_checksum(kind, bids, asks)
        def lv(xs):
            return "[" + ",".join(f'{{"price":{p},"qty":{q}}}' for p, q in xs) + "]"
        raw = (f'{{"channel":"book","type":"{kind}","data":[{{"symbol":"{symbol}","bids":{lv(bids)},'
               f'"asks":{lv(asks)},"checksum":{checksum},"timestamp":"2023-10-06T17:35:55.440295Z"}}]}}')
        return self.ev(t, "kraken", "ws_message", raw.encode(), wire.OP_TEXT)

    def expected_checksum(self, kind, bids, asks):
        book = bk._Book()
        src = self.engine.sources["kraken"]
        if kind == "update":
            book.bids, book.asks = dict(src.book.bids), dict(src.book.asks)
        for p, q in bids:
            book.set_level("bid", p, q)
        for p, q in asks:
            book.set_level("ask", p, q)
        book.truncate(10)
        return bk.kraken_checksum([(v[1], v[2]) for _, v in book.sorted_asks()],
                                  [(v[1], v[2]) for _, v in book.sorted_bids()])

    def kraken_text(self, t, doc):
        return self.ev(t, "kraken", "ws_message", json.dumps(doc).encode(), wire.OP_TEXT)

    def state(self, venue, t, liveness=2000):
        return bk.source_state(self.engine.snapshot()[venue], t, liveness)


def mexc_synced(f, t=1000):
    f.ev(t, "mexc", "ws_open")
    f.mexc_diff(t + 10, 101, 102, bids=[("100.00", "1")], asks=[("100.02", "1")])
    f.mexc_snapshot(t + 20, 101, [("100.00", "2"), ("99.99", "1")], [("100.02", "3")])
    return f


def kraken_synced(f, t=1000, bids=(("100.01", "1.00000000"),), asks=(("100.03", "1.00000000"),)):
    f.ev(t, "kraken", "ws_open")
    f.kraken(t + 10, "snapshot", list(bids), list(asks))
    return f


class KrakenChecksum(NoNetwork):
    def test_official_vector(self):
        self.assertEqual(bk.kraken_checksum(KRAKEN_ASKS, KRAKEN_BIDS), KRAKEN_OFFICIAL_CHECKSUM)

    def test_decimal_representation_matters(self):
        # Same values, trailing zeros dropped: different characters, different CRC.
        stripped = [(p, q.rstrip("0")) for p, q in KRAKEN_ASKS]
        self.assertNotEqual(bk.kraken_checksum(stripped, KRAKEN_BIDS), KRAKEN_OFFICIAL_CHECKSUM)

    def test_json_numeric_literals_are_kept_verbatim(self):
        doc = bk.kraken_json(b'{"price":45283.5,"qty":0.10000000,"n":3310070434}')
        self.assertEqual((doc["price"], doc["qty"], doc["n"]), ("45283.5", "0.10000000", "3310070434"))
        self.assertIsInstance(doc["qty"], bk.Num)
        with self.assertRaises(ValueError):
            bk.kraken_json(b'{"price":NaN}')

    def test_official_vector_through_the_engine_from_json_numbers(self):
        f = Feed()
        f.ev(0, "kraken", "ws_open")
        f.kraken(10, "snapshot", KRAKEN_BIDS, KRAKEN_ASKS, checksum=KRAKEN_OFFICIAL_CHECKSUM)
        self.assertEqual(f.engine.sources["kraken"].continuity, "SYNCED")
        self.assertEqual(f.state("kraken", 10), bk.VALID)

    def test_mismatch_drops_the_book_until_a_validated_snapshot(self):
        f = kraken_synced(Feed())
        f.kraken(2000, "update", [("100.02", "1.00000000")], [], checksum=12345)
        src = f.engine.sources["kraken"]
        self.assertEqual((src.continuity, src.lost_reason), ("CONTINUITY_LOST", "CHECKSUM_MISMATCH"))
        self.assertIn(("kraken", "NEED_RESUBSCRIBE"), f.actions)
        self.assertEqual(f.state("kraken", 2000), bk.CONTINUITY_LOST)
        # updates are ignored while lost, even with a matching checksum
        f.kraken(2100, "update", [("100.02", "2.00000000")], [], checksum=0)
        self.assertEqual(src.counters["update_ignored_not_synced"], 1)
        # heartbeat and pong confirm liveness only
        f.kraken_text(2200, {"channel": "heartbeat"})
        f.kraken_text(2300, {"method": "pong", "req_id": 1})
        self.assertEqual(f.state("kraken", 2300), bk.CONTINUITY_LOST)
        self.assertEqual(src.last_update_ms, 1010)
        # a snapshot with a wrong checksum does not readmit
        f.kraken(2400, "snapshot", [("100.01", "1.00000000")], [("100.03", "1.00000000")], checksum=1)
        self.assertEqual(f.state("kraken", 2400), bk.CONTINUITY_LOST)
        f.kraken(2500, "snapshot", [("100.01", "1.00000000")], [("100.03", "1.00000000")])
        self.assertEqual(f.state("kraken", 2500), bk.VALID)
        self.assertEqual(src.breaks, [{"t_ms": 2000, "reason": "CHECKSUM_MISMATCH", "resolved_at_ms": 2500}])

    def test_truncation_to_subscribed_depth(self):
        f = Feed()
        f.ev(0, "kraken", "ws_open")
        bids = [(f"{100 - i}.0", "1.0") for i in range(10)]
        asks = [(f"{101 + i}.0", "1.0") for i in range(10)]
        f.kraken(10, "snapshot", bids, asks)
        f.kraken(20, "update", [("100.5", "1.0")], [])  # pushes 91.0 out of the top 10
        src = f.engine.sources["kraken"]
        self.assertEqual(len(src.book.bids), 10)
        self.assertNotIn(Decimal("91.0"), src.book.bids)
        self.assertEqual(src.continuity, "SYNCED")


class MexcJoin(NoNetwork):
    """First join (official procedure) tested apart from continuity after it."""

    def test_snapshot_requested_after_first_cached_diff(self):
        f = Feed()
        f.ev(0, "mexc", "ws_open")
        f.mexc_diff(10, 101, 102)
        self.assertEqual(f.actions, [("mexc", "NEED_SNAPSHOT")])
        self.assertEqual(f.state("mexc", 10), bk.NOT_INITIALIZED)

    def test_join_applies_cached_diffs_after_snapshot(self):
        f = Feed()
        f.ev(0, "mexc", "ws_open")
        f.mexc_diff(10, 101, 102, bids=[("100.00", "5")])
        f.mexc_diff(20, 103, 105, asks=[("100.01", "1")])
        f.mexc_snapshot(30, 102, [("100.00", "1")], [("100.02", "1")])
        src = f.engine.sources["mexc"]
        self.assertEqual(src.join_log[-1]["outcome"], "JOINED")
        self.assertEqual(src.join_log[-1]["applied_diffs"], 1)  # 101-102 dropped (toVersion <= 102)
        self.assertEqual(src.top, (Decimal("100.00"), Decimal(1), Decimal("100.01"), Decimal(1)))
        self.assertEqual(src.last_to, 105)
        self.assertEqual(f.state("mexc", 30), bk.VALID)

    def test_snapshot_older_than_first_diff_is_refetched(self):
        f = Feed()
        f.ev(0, "mexc", "ws_open")
        f.mexc_diff(10, 101, 102)
        f.actions.clear()
        f.mexc_snapshot(20, 100, [("100.00", "1")], [("100.02", "1")])
        src = f.engine.sources["mexc"]
        self.assertEqual(src.join_log[-1]["outcome"], "SNAPSHOT_OLDER_THAN_FIRST_DIFF")
        self.assertEqual(f.actions, [("mexc", "NEED_SNAPSHOT")])
        self.assertEqual(f.state("mexc", 20), bk.NOT_INITIALIZED)

    def test_gap_between_snapshot_and_first_remaining_diff_reinitialises(self):
        f = Feed()
        f.ev(0, "mexc", "ws_open")
        f.mexc_diff(10, 101, 102)
        f.mexc_diff(20, 103, 110)
        f.mexc_snapshot(30, 102, [("100.00", "1")], [("100.02", "1")])  # joins: 103 == 102+1
        self.assertEqual(f.engine.sources["mexc"].continuity, "SYNCED")
        # official step 5: the first diff after the snapshot does not follow it
        g = Feed()
        g.ev(0, "mexc", "ws_open")
        g.mexc_diff(10, 105, 106)
        g.mexc_snapshot(20, 106, [("100.00", "1")], [("100.02", "1")])  # nothing left: waits
        g.actions.clear()
        g.mexc_diff(30, 108, 109)  # expected 107
        src = g.engine.sources["mexc"]
        self.assertEqual(src.join_log[-1]["outcome"], "FIRST_DIFF_AFTER_SNAPSHOT_GAP")
        self.assertEqual(g.actions, [("mexc", "NEED_SNAPSHOT")])
        self.assertEqual(g.state("mexc", 30), bk.NOT_INITIALIZED)

    def test_cache_restarts_at_an_internal_gap(self):
        f = Feed()
        f.ev(0, "mexc", "ws_open")
        f.mexc_diff(10, 101, 102)
        f.mexc_diff(20, 105, 106)
        src = f.engine.sources["mexc"]
        self.assertEqual(src.counters["buffer_gap"], 1)
        self.assertEqual([(d["from"], d["to"]) for d in src.buffer], [(105, 106)])
        f.mexc_snapshot(30, 104, [("100.00", "1")], [("100.02", "1")])
        self.assertEqual(src.join_log[-1]["outcome"], "SNAPSHOT_OLDER_THAN_FIRST_DIFF")

    def test_snapshot_newer_than_cache_waits_for_next_diff(self):
        f = Feed()
        f.ev(0, "mexc", "ws_open")
        f.mexc_diff(10, 101, 102)
        f.mexc_snapshot(20, 104, [("100.00", "1")], [("100.02", "1")])
        self.assertEqual(f.state("mexc", 20), bk.NOT_INITIALIZED)
        f.mexc_diff(30, 103, 104)  # still <= lastUpdateId: dropped
        self.assertEqual(f.state("mexc", 30), bk.NOT_INITIALIZED)
        f.mexc_diff(40, 105, 105, bids=[("100.01", "1")])
        self.assertEqual(f.state("mexc", 40), bk.VALID)
        self.assertEqual(f.engine.sources["mexc"].top[0], Decimal("100.01"))

    def test_failed_snapshot_fetch(self):
        f = Feed()
        f.ev(0, "mexc", "ws_open")
        f.mexc_diff(10, 101, 102)
        f.actions.clear()
        f.ev(20, "mexc", "rest_depth", b"", status=None)
        self.assertEqual(f.engine.sources["mexc"].join_log[-1]["outcome"], "SNAPSHOT_FETCH_FAILED")
        self.assertEqual(f.actions, [("mexc", "NEED_SNAPSHOT")])


class MexcContinuity(NoNetwork):
    def test_contiguous_diffs_keep_the_book(self):
        f = mexc_synced(Feed())
        f.mexc_diff(1100, 103, 104, bids=[("100.01", "1")])
        self.assertEqual(f.state("mexc", 1100), bk.VALID)

    def test_version_gap_then_pong_then_rebuild(self):
        f = mexc_synced(Feed())
        f.actions.clear()
        f.mexc_diff(1100, 105, 106)  # expected 103
        src = f.engine.sources["mexc"]
        self.assertEqual((src.continuity, src.lost_reason), ("CONTINUITY_LOST", "VERSION_GAP"))
        self.assertEqual(f.actions, [("mexc", "NEED_SNAPSHOT")])
        # PONG during the break: liveness only, never the book nor the quote time
        f.mexc_pong(1200)
        self.assertEqual(src.last_liveness_ms, 1200)
        self.assertEqual(src.last_update_ms, 1020)
        self.assertEqual(f.state("mexc", 1200), bk.CONTINUITY_LOST)
        f.mexc_snapshot(1300, 106, [("100.00", "1")], [("100.02", "1")])
        self.assertEqual(f.state("mexc", 1300), bk.CONTINUITY_LOST)
        f.mexc_diff(1400, 107, 107)
        self.assertEqual(f.state("mexc", 1400), bk.VALID)
        self.assertEqual(src.breaks[0]["resolved_at_ms"], 1400)

    def test_disconnect_drops_and_reconnect_requires_rejoin(self):
        f = mexc_synced(Feed())
        f.ev(1100, "mexc", "ws_close")
        self.assertEqual(f.state("mexc", 1100), bk.CONTINUITY_LOST)
        f.ev(1200, "mexc", "ws_open")
        f.mexc_pong(1300)
        self.assertEqual(f.state("mexc", 1300), bk.CONTINUITY_LOST)
        f.mexc_diff(1400, 300, 301)
        f.mexc_snapshot(1500, 300, [("100.00", "1")], [("100.02", "1")])
        self.assertEqual(f.state("mexc", 1500), bk.VALID)

    def test_gave_up_is_unavailable(self):
        f = mexc_synced(Feed())
        f.ev(1100, "mexc", "gave_up")
        self.assertEqual(f.state("mexc", 1100), bk.SOURCE_UNAVAILABLE)

    def test_foreign_symbol_is_not_applied(self):
        f = mexc_synced(Feed())
        body = wire.encode_aggre_depths([], [("200.00", "1")], 103, 103)
        f.ev(1100, "mexc", "ws_message", wire.encode_mexc_push(CH, "ETHUSDT", body), wire.OP_BINARY)
        self.assertEqual(f.engine.sources["mexc"].counters["foreign_frame"], 1)
        self.assertEqual(f.engine.sources["mexc"].top[0], Decimal("100.00"))


class States(NoNetwork):
    def test_stale_liveness_is_freshness_unknown(self):
        f = mexc_synced(Feed())
        self.assertEqual(f.state("mexc", 3020), bk.VALID)
        self.assertEqual(f.state("mexc", 3021), bk.FRESHNESS_UNKNOWN)

    def test_unchanged_but_verified_by_recent_pong(self):
        f = mexc_synced(Feed())
        f.mexc_pong(4000)
        self.assertEqual(f.state("mexc", 5000), bk.UNCHANGED_VERIFIED)
        snap = f.engine.snapshot()["mexc"]
        self.assertEqual(snap["last_update_ms"], 1020)  # quote time untouched by PONG
        self.assertEqual(f.state("mexc", 6001), bk.FRESHNESS_UNKNOWN)

    def test_crossed_and_locked_books(self):
        for ask in ("100.00", "99.99"):
            f = Feed()
            f.ev(0, "mexc", "ws_open")
            f.mexc_diff(10, 101, 101)
            f.mexc_snapshot(20, 101, [("100.00", "1")], [("101.00", "1")])
            f.mexc_diff(30, 102, 102, asks=[(ask, "1")])
            self.assertEqual(f.state("mexc", 30), bk.BOOK_INVALID)

    def test_never_connected_is_unavailable(self):
        self.assertEqual(Feed().state("kraken", 0), bk.SOURCE_UNAVAILABLE)


def pair_at(mexc_mid_bid, mexc_mid_ask, kr_bid, kr_ask, t=1100, liveness=2000, gap=Decimal(50)):
    f = Feed()
    f.ev(0, "mexc", "ws_open")
    f.mexc_diff(10, 101, 102)
    f.mexc_snapshot(20, 101, [(mexc_mid_bid, "1")], [(mexc_mid_ask, "1")])
    f.ev(30, "kraken", "ws_open")
    f.kraken(40, "snapshot", [(kr_bid, "1.0")], [(kr_ask, "1.0")])
    f.mexc_pong(t)
    f.kraken_text(t, {"channel": "heartbeat"})
    return f, bk.evaluate_pair(f.engine.snapshot(), t, liveness, gap)


class Pair(NoNetwork):
    def test_two_valid_books(self):
        _, r = pair_at("99.99", "100.01", "100.09", "100.11")
        self.assertEqual(r["category"], bk.COMPOSITE)
        self.assertEqual(r["values"]["mexc"]["mid"], Decimal("100.00"))
        self.assertEqual(r["values"]["mexc"]["spread_bps"], Decimal(2))
        self.assertEqual(r["gap_bps"], Decimal(10))  # Kraken above MEXC: positive
        self.assertEqual(r["composite_mid"], Decimal("100.05"))

    def test_gap_threshold_is_closed(self):
        _, at = pair_at("99.99", "100.01", "100.49", "100.51")      # +50 bps exactly
        _, neg = pair_at("99.99", "100.01", "99.49", "99.51")       # -50 bps exactly
        _, over = pair_at("99.99", "100.01", "100.4901", "100.5101")  # +50.01 bps
        self.assertEqual((at["gap_bps"], at["category"]), (Decimal(50), bk.COMPOSITE))
        self.assertEqual((neg["gap_bps"], neg["category"]), (Decimal(-50), bk.COMPOSITE))
        self.assertEqual(over["category"], bk.EXCESSIVE_GAP)
        self.assertIsNone(over["composite_mid"])
        self.assertEqual(over["gap_bps"], Decimal("50.01"))

    def test_single_eligible_source_keeps_its_observation(self):
        f, _ = pair_at("99.99", "100.01", "100.09", "100.11")
        f.kraken(1200, "update", [("100.08", "1.0")], [], checksum=7)
        r = bk.evaluate_pair(f.engine.snapshot(), 1200, 2000, Decimal(50))
        self.assertEqual(r["category"], bk.SINGLE_SOURCE)
        self.assertEqual(r["states"], {"mexc": bk.VALID, "kraken": bk.CONTINUITY_LOST})
        self.assertEqual(r["values"]["mexc"]["mid"], Decimal("100.00"))
        self.assertIsNone(r["values"]["kraken"])
        self.assertIsNone(r["gap_bps"])

    def test_no_eligible_source(self):
        r = bk.evaluate_pair(Feed().engine.snapshot(), 0, 2000, Decimal(50))
        self.assertEqual(r["category"], bk.SOURCE_EXCLUDED)


class Replayability(NoNetwork):
    def test_later_frames_never_improve_an_earlier_instant(self):
        f = Feed()
        events = [
            {"seq": 1, "t_ms": 0, "venue": "mexc", "kind": "ws_open", "payload": b""},
            {"seq": 2, "t_ms": 10, "venue": "mexc", "kind": "ws_message", "opcode": wire.OP_BINARY,
             "payload": wire.encode_mexc_push(CH, "BTCUSDT", wire.encode_aggre_depths([], [], 101, 102))},
            {"seq": 3, "t_ms": 10_001, "venue": "mexc", "kind": "rest_depth", "status": 200,
             "payload": b'{"lastUpdateId":101,"bids":[["1.0","1"]],"asks":[["1.1","1"]]}'},
        ]
        snaps = bk.sample(f.engine, events, [10_000, 10_001])
        self.assertEqual(bk.source_state(snaps[0]["mexc"], 10_000, 2000), bk.NOT_INITIALIZED)
        self.assertEqual(bk.source_state(snaps[1]["mexc"], 10_001, 2000), bk.VALID)
        with self.assertRaises(ValueError):
            bk.sample(Feed().engine, list(reversed(events)), [10_000])

    def test_candles_29_and_30(self):
        full = [Decimal(100 + i % 3) for i in range(30)]
        c = bk.candle(full)
        self.assertEqual((c["status"], c["open"], c["high"], c["low"], c["close"]),
                         ("COMPLETE", Decimal(100), Decimal(102), Decimal(100), full[-1]))
        holed = full[:]
        holed[17] = None
        c = bk.candle(holed)
        self.assertEqual(c, {"status": "INCOMPLETE", "points": 29, "open": None, "high": None,
                             "low": None, "close": None})


if __name__ == "__main__":
    unittest.main()
