"""Offline analysis through its normal entry point (a campaign directory)."""

import json
import subprocess
import sys
from decimal import Decimal

import pytest

from observability.flux_collection_pilot import analysis, protocol as P
from observability.flux_collection_pilot.sequence import SequenceTracker
from observability.flux_collection_pilot.simulated import EPOCH_NS, Feed
from .helpers import S, write_campaign

def B(*lv):
    return [("bid" if s == "b" else "offer", p, q) for s, p, q in lv]


def stamp(raws, start=EPOCH_NS):
    return [(start + i * S, 10 * S + i * S, r) for i, r in enumerate(raws)]


def fp(bids, asks):
    return analysis.fingerprint(P.PRODUCT, bids, asks)


# --- gaps, repeats, rewinds -----------------------------------------------------------------
def test_gap_invalidates_at_the_suspect_message_and_nothing_is_published_from_an_invalid_state(tmp_path):
    f = Feed()
    raws = [f.snapshot(B(("b", "100", "2"), ("b", "99.5", "1"), ("a", "101", "3"))),
            f.update(B(("b", "100", "5"))),
            (f.skip("l2_data"), f.update(B(("b", "99.5", "7"))))[1],   # seq 3: one message missing
            f.update(B(("b", "100", "9"))),
            f.snapshot(B(("b", "100", "4"), ("a", "101", "3")))]       # a fresh snapshot of the same session
    rep = analysis.analyze(write_campaign(tmp_path, "g", {"S01": stamp(raws)}))
    b = rep["sessions"]["S01"]["book"]
    assert b["invalidations"][0]["idx"] == 2 and "SEQUENCE_GAP expected=2 got=3" in b["invalidations"][0]["reason"]
    assert b["published_idx"] == [0, 1, 4]            # nothing published for idx 2 and 3
    assert (b["updates_ignored_without_valid_book"], b["resyncs"], b["final_state"]) == (2, 1, "LIVE")
    assert b["final_fingerprint"] == fp([("100", "4")], [("101", "3")])  # no level survives the invalid period


@pytest.mark.parametrize("bad_seq, kind", [(1, "REPEAT"), (0, "REWIND")])
def test_repeat_and_rewind_are_not_applied_and_invalidate_the_book(tmp_path, bad_seq, kind):
    f = Feed()
    raws = [f.snapshot(B(("b", "100", "2"), ("a", "101", "3"))), f.update(B(("b", "100", "5"))),
            f.update(B(("b", "100", "8")), seq=bad_seq), f.update(B(("b", "100", "9")))]
    rep = analysis.analyze(write_campaign(tmp_path, "r", {"S01": stamp(raws)}))
    b = rep["sessions"]["S01"]["book"]
    assert "SEQUENCE_%s expected=2 got=%d" % (kind, bad_seq) in b["invalidations"][0]["reason"]
    assert b["published_idx"] == [0, 1] and b["final_state"] == "INVALID" and b["final_fingerprint"] is None
    assert [a["kind"] for a in rep["sessions"]["S01"]["sequence"]["anomalies"] if a["domain"] == "PER_CHANNEL"] == [kind]


def test_other_channels_never_fill_a_hole_under_per_channel_but_do_under_the_connection_policy(tmp_path):
    f = Feed("CONNECTION")  # one counter shared by every channel, as the AsyncAPI text suggests
    raws = [f.snapshot(B(("b", "100", "2"), ("a", "101", "3"))), f.heartbeat(), f.update(B(("b", "100", "5")))]
    path = write_campaign(tmp_path, "c", {"S01": stamp(raws)})
    chan = analysis.analyze(path, policy="PER_CHANNEL")["sessions"]["S01"]
    assert chan["book"]["final_state"] == "INVALID" and chan["book"]["published_idx"] == [0]
    conn = analysis.analyze(path, policy="PER_CONNECTION")["sessions"]["S01"]
    assert conn["book"]["final_state"] == "LIVE" and conn["book"]["published_idx"] == [0, 2]
    h = conn["sequence"]["hypotheses"]
    assert h["PER_CONNECTION"]["consistent"] and not h["PER_CHANNEL"]["consistent"]  # refuted, not "confirmed"
    assert h["PER_CHANNEL"]["first_refutation"]["index"] == 2


def test_sequence_domains_are_tracked_side_by_side_and_a_tracker_is_per_session():
    t = SequenceTracker()
    for i, (ch, seq) in enumerate([("l2_data", 0), ("market_trades", 0), ("l2_data", 1), ("heartbeats", 0)]):
        t.observe(i, ch, seq, ("BTC-USD",) if ch != "heartbeats" else ())
    r = t.report()["hypotheses"]
    assert r["PER_CHANNEL"]["consistent"] and r["PER_CHANNEL_PRODUCT"]["consistent"]
    assert not r["PER_CONNECTION"]["consistent"] and not r["PER_PRODUCT"]["consistent"]
    assert SequenceTracker().observe(0, "l2_data", 0)["kind"] == "BASELINE"  # a new tracker has no memory


# --- reconnection ---------------------------------------------------------------------------
def test_reconnection_without_snapshot_invalidates_the_old_book_and_updates_alone_prime_nothing(tmp_path):
    f1, f2 = Feed(), Feed()
    s1 = [f1.snapshot(B(("b", "100", "2"), ("a", "101", "3"))), f1.update(B(("b", "100", "5")))]
    s2 = [f2.update(B(("b", "100", "6"))), f2.update(B(("a", "101", "1"))), f2.heartbeat()]
    rep = analysis.analyze(write_campaign(tmp_path, "n", {"S01": stamp(s1), "S02": stamp(s2)}))
    old, new = rep["sessions"]["S01"]["book"], rep["sessions"]["S02"]["book"]
    assert old["final_state"] == "LIVE"
    assert (new["final_state"], new["publications"], new["snapshots_applied"]) == ("NO_SNAPSHOT", 0, 0)
    assert new["updates_ignored_without_valid_book"] == 2 and new["levels"] == {"bids": 0, "asks": 0}
    assert new["final_fingerprint"] is None  # no usable book after the reconnection: resumption failed


def test_reconnection_with_a_valid_snapshot_builds_a_fresh_book_with_no_inherited_level(tmp_path):
    f1, f2 = Feed(), Feed()
    s1 = [f1.snapshot(B(("b", "100", "2"), ("b", "98", "9"), ("a", "101", "3"), ("a", "105", "8"))),
          f1.update(B(("b", "98", "0")))]
    s2 = [f2.snapshot(B(("b", "100", "1"), ("b", "99.5", "1"), ("a", "102", "4"))),
          f2.update(B(("b", "100", "7"), ("b", "99.5", "0"), ("a", "102.5", "2")))]   # replace qty, remove by zero, add
    path = write_campaign(tmp_path, "w", {"S01": stamp(s1), "S02": stamp(s2)})
    rep = analysis.analyze(path)
    new = rep["sessions"]["S02"]["book"]
    expected = fp([("100", "7")], [("102", "4"), ("102.5", "2")])
    assert new["final_fingerprint"] == expected and new["levels"] == {"bids": 1, "asks": 2}
    assert new["published_idx"] == [0, 1]
    # independent evidence: S02 alone, written as the only session of another campaign, gives the same book
    alone = analysis.analyze(write_campaign(tmp_path, "w2", {"S01": stamp(s2)}))
    assert alone["sessions"]["S01"]["book"]["final_fingerprint"] == expected
    # two independent readings (fresh objects, then another process) give the same fingerprint
    assert analysis.analyze(path)["report_sha256"] == rep["report_sha256"]
    out = subprocess.run([sys.executable, "-m", "observability.flux_collection_pilot", "replay", str(path)],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out)["report_sha256"] == rep["report_sha256"]


def test_fingerprint_ignores_number_formatting_and_keeps_distinct_books_distinct():
    assert fp([("100.0", "2.00")], [("101", "3")]) == fp([("100", "2")], [("101.000", "3")])
    assert fp([("100", "2")], [("101", "3")]) != fp([("100", "2")], [("101", "3.0001")])


def test_removing_an_absent_level_and_a_crossed_book_invalidate(tmp_path):
    f = Feed()
    raws = [f.snapshot(B(("b", "100", "2"), ("a", "101", "3"))), f.update(B(("b", "99", "0")))]
    b = analysis.analyze(write_campaign(tmp_path, "u", {"S01": stamp(raws)}))["sessions"]["S01"]["book"]
    assert b["invalidations"][0]["reason"] == "REMOVE_UNKNOWN_LEVEL" and b["published_idx"] == [0]
    f = Feed()
    raws = [f.snapshot(B(("b", "100", "2"), ("a", "101", "3"))), f.update(B(("b", "101", "1")))]
    b = analysis.analyze(write_campaign(tmp_path, "x", {"S01": stamp(raws)}))["sessions"]["S01"]["book"]
    assert b["invalidations"][0]["reason"] == "CROSSED_OR_LOCKED_BOOK" and b["published_idx"] == [0]


def test_a_malformed_message_invalidates_a_live_book(tmp_path):
    f = Feed()
    raws = [f.snapshot(B(("b", "100", "2"), ("a", "101", "3"))), b"{broken", f.update(B(("b", "100", "5")))]
    s = analysis.analyze(write_campaign(tmp_path, "m", {"S01": stamp(raws)}))["sessions"]["S01"]
    assert s["refused"] == {"INVALID_JSON": 1} and s["book"]["final_state"] == "INVALID" and s["book"]["published_idx"] == [0]


# --- time inventory ---------------------------------------------------------------------------
def test_time_inventory_counts_missing_invalid_sentinel_and_after_cut_separately(tmp_path):
    f = Feed()
    future = "2099-01-01T00:00:00Z"
    raws = [
        f.snapshot(B(("b", "100", "2"), ("a", "101", "3"))),                                   # all OK
        f.update(B(("b", "100", "3")), event_time="1970-01-01T00:00:00Z", timestamp="1970-01-01T00:00:00Z"),
        f.update(B(("b", "100", "4")), event_time="0001-01-01T00:00:00Z", timestamp="0001-01-01T00:00:00Z"),
        f.update(B(("b", "100", "5")), event_time="not-a-time", timestamp="not-a-time"),
        f.update(B(("b", "100", "6")), event_time=None, timestamp=None),
        f.update(B(("b", "100", "7")), event_time=future, timestamp=future),
        f.trades([("t1", "1", "1", "BUY", "garbage")]),
        f.trades([("t2", "1", "1", "BUY", future)]),
    ]
    cut = EPOCH_NS + 100 * S
    rep = analysis.analyze(write_campaign(tmp_path, "t", {"S01": stamp(raws)}), cut_utc_ns=cut)
    send, ev, tr = (rep["time_totals"][k] for k in ("send_time", "l2_event_time", "trade_time"))
    assert ev == {"OK": 3, "MISSING": 1, "INVALID": 1, "SENTINEL_EPOCH": 2, "AFTER_CUT": 1, "AFTER_OWN_RECEIPT": 1}
    assert send["MISSING"] == 1 and send["INVALID"] == 1 and send["SENTINEL_EPOCH"] == 2 and send["AFTER_CUT"] == 1 and send["OK"] == 4
    assert tr["INVALID"] == 1 and tr["AFTER_CUT"] == 1
    assert rep["sessions"]["S01"]["time_locators"][0]["state"] in ("SENTINEL_EPOCH", "INVALID", "MISSING")
    # observer receipt times stay separate fields of the report (never merged with provider times)
    s = rep["sessions"]["S01"]
    assert s["first_recv_utc_ns"] != s["first_recv_mono_ns"]


# --- trades ---------------------------------------------------------------------------------
def test_duplicates_exact_once_and_contradictions_excluded_in_every_variant_across_sessions(tmp_path):
    f1, f2 = Feed(), Feed()
    def T(i, p, s, side="BUY", tm="2026-11-05T08:00:00Z"):
        return (i, p, s, side, tm)
    s1 = [f1.trades([T("a", "100", "1"), T("a", "100", "1"), T("b", "100", "2", "SELL"), T("c", "100", "4")]),
          f1.trades([T("d", "100", "8")])]
    s2 = [f2.trades([T("b", "100", "2", "SELL"), T("c", "100", "5"), T("e", "100", "16")], kind="snapshot"),  # b: exact dup across sessions; c: contradicts the first-seen variant
          f2.trades([T("d", "100", "8", tm="2026-11-05T08:00:01Z")])]                                  # d: only the time differs
    t = analysis.analyze(write_campaign(tmp_path, "d", {"S01": stamp(s1), "S02": stamp(s2)}))["trades"]
    assert (t["identities_seen"], t["identities_counted"], t["conflicting_identities"]) == (5, 3, 2)
    assert t["exact_duplicates_collapsed"] == 2          # a (within S01) and b (across sessions)
    assert Decimal(t["aggregates"]["volume_base"]) == Decimal("19")     # a 1 + b 2 + e 16: c and d excluded from every aggregate
    ids = {c["identity"][2]: c for c in t["conflicts"]}
    assert set(ids) == {"c", "d"} and all(len(c["variants"]) == 2 for c in ids.values())  # every variant stays consultable
    assert {v["size"] for v in ids["c"]["variants"]} == {"4", "5"}
    assert {v["locators"][0][:3] for v in ids["c"]["variants"]} == {"S01", "S02"}


def test_maker_side_is_kept_raw_and_the_aggressor_inversion_is_explicit_and_unattested(tmp_path):
    assert (analysis.derive_aggressor("BUY"), analysis.derive_aggressor("SELL")) == ("SELL", "BUY")
    assert analysis.derive_aggressor("buy") == analysis.derive_aggressor(None) == analysis.derive_aggressor("?") == "UNKNOWN"
    f = Feed()
    def T(i, s, side):
        return (i, "100", s, side, "2026-11-05T08:00:00Z")
    raws = [f.trades([T("1", "1", "BUY"), T("2", "3", "SELL")])]
    a = analysis.analyze(write_campaign(tmp_path, "s", {"S01": stamp(raws)}))["trades"]["aggregates"]
    assert a["volume_by_raw_maker_side"] == {"BUY": "1", "SELL": "3", "UNKNOWN": "0"}
    assert a["derived_taker_volume"] == {"BUY": "3", "SELL": "1"}      # inverted: maker SELL = taker BUY
    assert (a["derived_delta"], a["convention_attested"], a["cvd"]) == ("2", False, "NOT_COMPUTED")
    f = Feed()
    raws = [f.trades([T("1", "1", "BUY"), T("2", "3", "SELL"), T("3", "0.5", "ODD")])]
    a = analysis.analyze(write_campaign(tmp_path, "s2", {"S01": stamp(raws)}))["trades"]["aggregates"]
    assert a["derived_delta"] is None and a["derived_delta_bounds"] == ["1.5", "2.5"]  # unknown side widens, never defaults
    assert analysis.analyze(write_campaign(tmp_path, "s3", {"S01": stamp(raws)}))["side_convention"]["attested"] is False
