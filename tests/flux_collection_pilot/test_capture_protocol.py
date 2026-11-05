"""Runner scenarios through the normal entry point (CampaignRunner) with a simulated transport and injected time."""

import json

import pytest

from observability.flux_collection_pilot import protocol as P
from observability.flux_collection_pilot.memory import MemoryGuard
from observability.flux_collection_pilot.runner import CampaignConfig, CampaignRunner, ConnectionBudget, ConnectionCapExceeded
from observability.flux_collection_pilot.simulated import BOOK0, FakeClock, Script, ScriptedFactory
from observability.flux_collection_pilot.store import CampaignStore, read_raw_file, verify_campaign
from observability.flux_collection_pilot.transport import AccessRefused, ConnectFailed
from .helpers import S, final, healthy_items, run, script, trigger

pytestmark = pytest.mark.filterwarnings("ignore")


def raw_lines(path, sid):
    return read_raw_file(path / ("%s.raw.jsonl" % sid))[0]


# --- protocol shape ------------------------------------------------------------------------
def test_full_protocol_two_connections_planned_cut_and_global_duration(tmp_path):
    res, factory, path = run(tmp_path, [script(healthy_items(62)), script(healthy_items(130))])
    assert (res.end_reason, res.complete, len(factory.built)) == (P.DURATION_CAP, True, 2)
    f = final(path)
    assert f["ended_mono_ns"] - f["started_mono_ns"] == 180 * S  # exact global cap on the monotonic clock
    s1, s2 = (json.loads((path / n).read_bytes()) for n in ("s01.receipt.json", "s02.receipt.json"))
    assert s1["end_reason"] == P.PLANNED_CUT and s1["ended_mono_ns"] - s1["opened_mono_ns"] == 60 * S
    assert s2["end_reason"] == P.DURATION_CAP
    # frames scheduled after the cap were never read: 2 + 120 heartbeats + 59 updates (the 120 s update is 1 ns late)
    assert len(raw_lines(path, "S02")) == 181
    assert verify_campaign(path)["status"] == "COMPLETE_VERIFIED"
    assert all(t.subscribed and len(t.subscribed) == 3 and "jwt" not in "".join(t.subscribed) for t in factory.built)


def test_new_session_starts_without_inherited_counters(tmp_path):
    # session 2's counters restart at 0: that is NOT a rewind, because nothing is carried across sessions
    res, _, path = run(tmp_path, [script(healthy_items(62)), script(healthy_items(130))])
    assert res.complete
    seq = json.loads((path / "s02.receipt.json").read_bytes())["sequence"]
    assert seq["hypotheses"]["PER_CHANNEL"] == {"consistent": True, "first_refutation": None}
    assert not [a for a in seq["anomalies"] if a["domain"] == "PER_CHANNEL"]
    # the other candidate domains are refuted by this (channel-numbered) synthetic feed: kept as data, not hidden
    assert seq["hypotheses"]["PER_CONNECTION"]["consistent"] is False


def test_unhealthy_first_session_at_cut_stops_everything_no_reconnect(tmp_path):
    res, factory, path = run(tmp_path, [script(healthy_items(70, snapshot=False)), script(healthy_items(130))])
    assert (res.end_reason, res.complete, len(factory.built)) == (P.SESSION_UNHEALTHY_AT_CUT, False, 1)
    assert trigger(path)["detail"] == {"heartbeats": 60, "snapshots": 0}


def test_connection_cap_refuses_a_third_and_a_one_connection_cap_blocks_the_reconnect(tmp_path):
    b = ConnectionBudget(2)
    assert (b.acquire(), b.acquire()) == (1, 2)
    with pytest.raises(ConnectionCapExceeded):
        b.acquire()
    caps = P.Caps(max_connections=1)
    res, factory, _ = run(tmp_path, [script(healthy_items(62)), script(healthy_items(10))], caps=caps)
    assert (res.end_reason, len(factory.built), res.complete) == (P.CONNECTION_CAP, 1, False)


def test_peer_close_after_reconnect_is_a_safety_stop_never_a_third_connection(tmp_path):
    s2 = script(healthy_items(20))
    s2.close(21 * S)
    res, factory, _ = run(tmp_path, [script(healthy_items(62)), s2])
    assert (res.end_reason, len(factory.built), res.complete) == (P.CONNECTION_LOST, 2, False)


def test_caps_above_protocol_are_refused(tmp_path):
    clock = FakeClock()
    with pytest.raises(ValueError, match="CAPS_ABOVE_PROTOCOL"):
        CampaignRunner(CampaignConfig("x", "d", P.Caps(max_messages=100_001)), ScriptedFactory(clock, []), clock,
                       CampaignStore(tmp_path, "x", P.PROTOCOL_CAPS))


# --- caps ---------------------------------------------------------------------------------
def hb_stream(n, step_ns):
    items = [(i * step_ns + 1, lambda f: f.heartbeat()) for i in range(n)]
    return script(items)


def test_message_cap_boundary_at_limit_and_one_over(tmp_path):
    caps = P.Caps(max_messages=50)
    res, factory, path = run(tmp_path, [hb_stream(60, 10_000_000)], caps=caps)
    assert (res.end_reason, res.messages) == (P.MESSAGE_CAP, 50)
    assert len(raw_lines(path, "S01")) == 50
    assert len(factory.built[0]._queue) == 10  # message 51 was never read
    t = trigger(path)
    assert (t["reason"], t["idx"], t["raw_in_session_file"]) == (P.MESSAGE_CAP, 49, True)
    # one under the limit: no cap stop (the stream then ends by the peer closing)
    sc = hb_stream(49, 10_000_000).close(S)
    res2, _, _ = run(tmp_path, [sc], caps=caps, cid="c2")
    assert (res2.end_reason, res2.messages) == (P.CONNECTION_LOST, 49)


def test_message_cap_at_the_real_protocol_value_100000(tmp_path):
    res, factory, path = run(tmp_path, [hb_stream(100_001, 400_000)])
    assert (res.end_reason, res.messages) == (P.MESSAGE_CAP, 100_000)
    assert len(factory.built[0]._queue) == 1
    assert final(path)["bytes_written"] <= P.PROTOCOL_CAPS.max_disk_bytes


def test_disk_cap_keeps_the_trigger_message_and_reserves_room_for_the_final_receipt(tmp_path):
    caps = P.Caps(max_disk_bytes=20_000, reserve_bytes=12_000)
    res, _, path = run(tmp_path, [script(healthy_items(30))], caps=caps)
    assert (res.end_reason, res.complete) == (P.DISK_CAP, False)
    t = trigger(path)
    assert t["reason"] == P.DISK_CAP and t["raw_in_session_file"] is False and t["raw_b64"] and res.trigger["written"]
    total = sum(p.stat().st_size for p in path.iterdir())
    assert total <= caps.max_disk_bytes and res.bytes_written == total
    assert (path / "final.receipt.json").exists() and final(path)["end_reason"] == P.DISK_CAP
    # the refused message is not in the raw file, every earlier one is, in order
    idxs = [r["idx"] for r in raw_lines(path, "S01")]
    assert idxs == list(range(len(idxs))) and t["idx"] == len(idxs)


def test_memory_guard_cap_unverifiable_and_runner_integration(tmp_path):
    g = MemoryGuard(100, reader=lambda: 99)
    assert g.check() == (True, None, 99)
    assert MemoryGuard(100, reader=lambda: 100).check() == (False, "MEMORY_CAP", 100)
    assert MemoryGuard(100, reader=lambda: None).check() == (False, "MEMORY_UNVERIFIABLE", None)
    res, _, path = run(tmp_path, [script(healthy_items(5))], mem=MemoryGuard(100, reader=lambda: 100))
    assert (res.end_reason, res.messages) == (P.MEMORY_CAP, 0)
    res2, _, _ = run(tmp_path, [script(healthy_items(5))], mem=MemoryGuard(100, reader=lambda: None), cid="c2")
    assert res2.end_reason == P.MEMORY_UNVERIFIABLE
    calls = []

    def reader():
        calls.append(1)
        return 10 if len(calls) == 1 else 1000  # fine at session open, over the cap at the periodic check
    res3, _, _ = run(tmp_path, [hb_stream(400, 10_000_000)], mem=MemoryGuard(500, reader=reader), cid="c3")
    assert (res3.end_reason, res3.messages) == (P.MEMORY_CAP, 256)


def test_live_evidence_requires_a_memory_guard(tmp_path):
    clock = FakeClock()
    cfg = CampaignConfig("x", "d", evidence_kind="LIVE")
    with pytest.raises(ValueError, match="MEMORY_GUARD_REQUIRED_FOR_LIVE"):
        CampaignRunner(cfg, ScriptedFactory(clock, []), clock, CampaignStore(tmp_path, "x", P.PROTOCOL_CAPS))


# --- stops --------------------------------------------------------------------------------
def test_refused_access_at_open_and_midstream_local_loss_and_peer_close_all_stop_without_reconnect(tmp_path):
    cases = {
        "open_refused": (Script(refuse_open=AccessRefused("HTTP_403")), P.ACCESS_REFUSED),
        "open_failed": (Script(refuse_open=ConnectFailed("DNS")), P.CONNECT_FAILED),
        "policy_close": (script(healthy_items(3)).refuse(2 * S), P.ACCESS_REFUSED),
        "local_loss": (script(healthy_items(3)).loss(2 * S), P.LOCAL_LOSS),
        "peer_close": (script(healthy_items(3)).close(2 * S), P.CONNECTION_LOST),
    }
    for i, (name, (sc, reason)) in enumerate(cases.items()):
        res, factory, path = run(tmp_path, [sc, script(healthy_items(130))], cid="c%d" % i)
        assert (res.end_reason, res.complete, len(factory.built)) == (reason, False, 1), name
        assert trigger(path)["reason"] == reason and final(path)["complete"] is False


@pytest.mark.parametrize("gap_ns, expected", [(4_900_000_000, P.CONNECTION_LOST), (5_000_000_000, P.CONNECTION_LOST),
                                              (5_000_000_001, P.SILENCE_HEARTBEAT)])
def test_heartbeat_silence_of_five_seconds_with_simulated_clock(tmp_path, gap_ns, expected):
    items = [(S // 10, lambda f: f.snapshot(BOOK0)), (S, lambda f: f.heartbeat()),
             (S + gap_ns, lambda f: f.heartbeat())]
    sc = script(items).close(S + gap_ns + 2 * S)
    res, _, path = run(tmp_path, [sc])
    assert res.end_reason == expected
    if expected == P.SILENCE_HEARTBEAT:
        # the stop happened exactly 5 s after the last heartbeat, on the monotonic clock
        assert trigger(path)["detail"] == {"silence_ns": 5 * S}
        assert final(path)["ended_mono_ns"] - (final(path)["started_mono_ns"] + S) == 5 * S


def test_silence_counts_from_session_open_when_no_heartbeat_ever_arrives(tmp_path):
    res, _, path = run(tmp_path, [script([(S // 10, lambda f: f.snapshot(BOOK0))])])
    assert res.end_reason == P.SILENCE_HEARTBEAT and trigger(path)["detail"] == {"silence_ns": 5 * S}


def test_a_non_heartbeat_channel_does_not_reset_the_silence_budget(tmp_path):
    items = [(i * S, lambda f: f.trades([("t%d" % 0, "1", "1", "BUY", "auto")])) for i in range(1, 10)]
    res, _, _ = run(tmp_path, [script(items)])
    assert res.end_reason == P.SILENCE_HEARTBEAT


@pytest.mark.parametrize("name, make, reason", [
    ("not_json", lambda f: b"{nope", P.MALFORMED_MESSAGE),
    ("duplicate_key", lambda f: b'{"channel":"heartbeats","channel":"x","sequence_num":9}', P.MALFORMED_MESSAGE),
    ("float_number", lambda f: b'{"channel":"heartbeats","sequence_num":1.5}', P.MALFORMED_MESSAGE),
    ("other_product", lambda f: f.snapshot([("bid", "1", "1")], product="ETH-USD"), P.UNEXPECTED_PRODUCT),
    ("provider_error", lambda f: b'{"type":"error","message":"forbidden"}', P.PROVIDER_ERROR),
])
def test_format_anomalies_stop_and_keep_the_triggering_message(tmp_path, name, make, reason):
    sc = script([(S // 10, lambda f: f.snapshot(BOOK0)), (S // 2, make)])
    res, _, path = run(tmp_path, [sc])
    t = trigger(path)
    assert (res.end_reason, t["reason"], t["idx"], t["raw_in_session_file"]) == (reason, reason, 1, True)
    assert read_raw_file(path / "S01.raw.jsonl")[0][1]["bytes"] > 0


def test_oversized_message_is_not_stored_and_its_size_is_recorded(tmp_path):
    big = b'{"channel":"heartbeats","sequence_num":9,"pad":"' + b"x" * 600_000 + b'"}'
    res, _, path = run(tmp_path, [script([]).frame(S // 10, big)])
    t = trigger(path)
    assert res.end_reason == P.MESSAGE_TOO_LARGE and t["raw_bytes_total"] == len(big) and t["raw_truncated"] is True
    assert read_raw_file(path / "S01.raw.jsonl")[0] == []
    res2, _, path2 = run(tmp_path, [script([]).too_large(S // 10)], cid="c2")  # transport-side bound
    assert res2.end_reason == P.MESSAGE_TOO_LARGE and trigger(path2)["raw_bytes_total"] == 10**7


# --- sequence stops (trigger, exact reason, other channels fill no hole) ---------------------
def seq_items(bad):
    return [(S // 10, lambda f: f.snapshot(BOOK0)), (S // 2, lambda f: f.update([("bid", "100", "3")])), (S, bad)]


@pytest.mark.parametrize("kind, bad, expected, got", [
    ("GAP", lambda f: (f.skip("l2_data", 2), f.update([("bid", "100", "4")]))[1], 2, 4),
    ("REPEAT", lambda f: f.update([("bid", "100", "4")], seq=1), 2, 1),
    ("REWIND", lambda f: f.update([("bid", "100", "4")], seq=0), 2, 0),
])
def test_l2_gap_repeat_rewind_stop_with_trigger_and_exact_reason(tmp_path, kind, bad, expected, got):
    res, _, path = run(tmp_path, [script(seq_items(bad))])
    t = trigger(path)
    assert res.end_reason == P.L2_SEQUENCE_SUSPECT
    assert t["idx"] == 2 and t["detail"]["kind"] == kind and (t["detail"]["expected"], t["detail"]["got"]) == (expected, got)
    assert t["raw_in_session_file"] is True and len(raw_lines(path, "S01")) == 3  # trigger message is the last stored


def test_other_channel_counters_do_not_fill_an_l2_hole_under_the_default_policy(tmp_path):
    items = [(S // 10, lambda f: f.snapshot(BOOK0)), (S // 2, lambda f: f.heartbeat()),
             (S, lambda f: f.update([("bid", "100", "3")]))]
    res, _, path = run(tmp_path, [script(items, domain="CONNECTION")])  # provider-like single counter
    t = trigger(path)
    assert res.end_reason == P.L2_SEQUENCE_SUSPECT and t["detail"]["kind"] == "GAP"
    assert (t["detail"]["expected"], t["detail"]["got"], t["detail"]["domain"]) == (1, 2, "PER_CHANNEL")


def test_the_same_stream_is_accepted_when_the_operator_selects_the_connection_domain(tmp_path):
    scripts = [script(healthy_items(62), domain="CONNECTION"), script(healthy_items(130), domain="CONNECTION")]
    res, _, _ = run(tmp_path, scripts, policy="PER_CONNECTION")
    assert (res.end_reason, res.complete) == (P.DURATION_CAP, True)
    res2, _, path = run(tmp_path, [script(healthy_items(62), domain="CONNECTION")], cid="c2")
    assert res2.end_reason == P.L2_SEQUENCE_SUSPECT  # default policy: stops at the first interleaving


# --- time ---------------------------------------------------------------------------------
def test_utc_and_monotonic_receipts_are_distinct_fields_and_not_interchangeable(tmp_path):
    clock = FakeClock()
    clock.skew_ns = 7  # the UTC clock steps 7 ns more than the monotonic one at each advance
    res, _, path = run(tmp_path, [script(healthy_items(5)).close(6 * S)], clock=clock)
    recs = raw_lines(path, "S01")
    assert all("recv_utc_ns" in r and "recv_mono_ns" in r for r in recs)
    d_utc = recs[-1]["recv_utc_ns"] - recs[0]["recv_utc_ns"]
    d_mono = recs[-1]["recv_mono_ns"] - recs[0]["recv_mono_ns"]
    assert d_utc != d_mono and recs[0]["recv_utc_ns"] != recs[0]["recv_mono_ns"]


def test_backwards_monotonic_clock_is_a_safety_stop(tmp_path):
    class Back(FakeClock):
        def sample(self):
            i = super().sample()
            if self.samples == 6:
                self.mono -= 10
                return type(i)(i.utc_ns, i.monotonic_ns - 10)
            return i
    res, _, _ = run(tmp_path, [script(healthy_items(10))], clock=Back())
    assert res.end_reason == P.CLOCK_ANOMALY


def test_operator_clock_checks_are_recorded_as_supplied_or_flagged_not_supplied(tmp_path):
    _, _, path = run(tmp_path, [script(healthy_items(62)), script(healthy_items(130))])
    assert final(path)["observer_clock_checks"] == "NOT_SUPPLIED"
    assert "A-SEND-AS-OF" in final(path)["hypotheses_unproven"]
    assert "cgroup MemoryMax is NOT configured" in final(path)["limits"]["memory"]
