"""CH1-02 step 1: Kraken-only replay of a sealed BBO journal. SYNTHETIC journals only.

The reference journal is produced offline by ``bbo_pilot.dry_run`` (fake clock, fake
venues, scheduled faults: one Kraken bad checksum, one Kraken silence). Nothing here
is provider output or runtime proof.
"""

from decimal import Decimal
import hashlib
import json

import pytest

from observability.market_flow import kraken_replay as kr
from observability.market_flow import perception as pc
from observability.radar_composite import bbo_book, bbo_pilot

CORPUS = "SYNTH-BBO-BTC"


@pytest.fixture(scope="module")
def journal(tmp_path_factory):
    out = tmp_path_factory.mktemp("bbo") / "run"
    _pilot, code = bbo_pilot.dry_run("BTC", out)
    assert code == 0
    return tuple((out / name).read_bytes() for name in ("manifest.json", "events.jsonl", "frames.bin"))


@pytest.fixture(scope="module")
def full(journal):
    out, seal = kr.replay(*journal, corpus_id=CORPUS, evidence_kind="SYNTHETIC")
    return out, json.loads(out), seal


def records(doc, kind):
    return [r["record"] for r in doc["records"] if r["type"] == kind]


def reseal(manifest_bytes, entries, frames):
    """Rebuild a consistent sealed journal from event entries (synthetic tampering helper)."""
    events = b"".join((json.dumps(e, sort_keys=True) + "\n").encode() for e in entries)
    manifest = json.loads(manifest_bytes)
    manifest["sealed"].update(events=len(entries), events_sha256=hashlib.sha256(events).hexdigest(),
                              frames_sha256=hashlib.sha256(frames).hexdigest())
    return json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n", events, frames


def entries_of(events_bytes):
    return [json.loads(line) for line in events_bytes.decode().splitlines()]


def append_kraken_text(journal, payload):
    manifest, events, frames = journal
    entries = entries_of(events)
    last = entries[-1]
    mono = last["recv_mono_ms"] + 10
    anchor = json.loads(manifest)["clock_anchor"]
    entries.append({"seq": last["seq"] + 1, "venue": "kraken", "kind": "ws_message", "opcode": 1,
                    "recv_wall_ms": mono, "recv_mono_ms": mono,
                    "t_ms": anchor["wall_ms"] + mono - anchor["mono_ms"], "offset": len(frames),
                    "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    return reseal(manifest, entries, frames + payload)


# ------------------------------------------------------------------ determinism and contract


def test_two_runs_give_the_same_bytes(journal, full):
    again, _ = kr.replay(*journal, corpus_id=CORPUS, evidence_kind="SYNTHETIC")
    assert again == full[0]
    assert hashlib.sha256(again).hexdigest() == hashlib.sha256(full[0]).hexdigest()


def test_every_record_satisfies_the_ch1_01_contract(full):
    _out, doc, _seal = full
    assert {r["type"] for r in doc["records"]} == {"RAW_EVENT", "BOOK_STATE", "QUALITY_REPORT"}
    for r in doc["records"]:
        pc.validate_record(r["type"], r["record"])
    raw = records(doc, "RAW_EVENT")
    assert {r["venue"] for r in raw} == {"kraken"}
    assert {(r["market_type"], r["native_symbol"]) for r in raw} == {("SPOT", "BTC/USDT")}
    assert doc["session"]["base"] == "BTC" and doc["session"]["quote"] == "USDT"
    assert doc["ignored_events_by_venue"]["mexc"] != "0"  # MEXC frames stay out of the projection


def test_receipt_order_and_states_follow_their_raw_event(full):
    doc = full[1]
    seqs = [int(r["record"].get("receipt_seq") or r["record"]["as_of_receipt_seq"]) for r in doc["records"]]
    assert seqs == sorted(seqs)
    raw_seqs = {r["receipt_seq"] for r in records(doc, "RAW_EVENT")}
    for state in records(doc, "BOOK_STATE"):
        assert state["as_of_receipt_seq"] in raw_seqs


def test_dimensions_that_this_journal_cannot_attest_stay_unknown(full):
    for q in records(full[1], "QUALITY_REPORT"):
        assert q["evidence_kind"] == "SYNTHETIC"
        assert (q["trade_coverage"]["state"], q["trade_coverage"]["reason"]) == ("UNKNOWN", "TRADE_CHANNEL_NOT_CAPTURED")
        assert (q["book_freshness"]["state"], q["book_freshness"]["reason"]) == ("UNKNOWN", "BOOK_FRESHNESS_NOT_ATTESTED")
        assert q["event_time_quality"]["state"] == "UNKNOWN"


def test_receipt_times_keep_their_millisecond_origin(full):
    doc = full[1]
    assert doc["session"]["receipt_time_resolution_ns"] == "1000000"
    for r in records(doc, "RAW_EVENT"):
        assert int(r["receive_utc_ns"]) % 1_000_000 == 0 and r["native_sequence"] is None


# ------------------------------------------------------------------ book and breaks


def test_checksum_break_invalidates_then_resyncs_only_through_a_snapshot(full):
    doc = full[1]
    assert [b["reason"] for b in doc["breaks"]] == ["CHECKSUM_MISMATCH"]
    brk, resolved = int(doc["breaks"][0]["receipt_seq"]), int(doc["breaks"][0]["resolved_receipt_seq"])
    timeline = [(int(q["as_of_receipt_seq"]), q["book_integrity"]["state"]) for q in records(doc, "QUALITY_REPORT")]
    assert (brk, "INVALID") in timeline
    between = [s for seq, s in timeline if brk < seq < resolved]
    assert between and set(between) <= {"INVALID", "RESYNCING"} and "RESYNCING" in between
    assert (resolved, "VERIFIED") in timeline
    states = {int(s["as_of_receipt_seq"]): s for s in records(doc, "BOOK_STATE")}
    assert states[brk]["bids"] is None and states[brk]["native_state"] == "CONTINUITY_LOST"
    assert states[resolved]["native_state"] == "VALID" and states[resolved]["bids"]


def test_verified_integrity_points_to_the_checksum_matched_message(full):
    doc = full[1]
    states = {s["as_of_receipt_seq"]: s for s in records(doc, "BOOK_STATE")}
    for q in records(doc, "QUALITY_REPORT"):
        if q["book_integrity"]["state"] == "VERIFIED":
            state = states[q["as_of_receipt_seq"]]
            assert q["book_integrity"]["evidence_receipt_seq"] == state["last_book_receipt_seq"] is not None


def test_differential_against_bbo_book_engine(journal):
    """Same journal, same Kraken book and continuity as the pilot's own engine."""
    _manifest, events = kr.load_journal(*journal)
    engine = bbo_book.Engine("BTCUSDT", "unused", "BTC/USDT", 10)
    doc = json.loads(kr.replay(*journal, corpus_id=CORPUS, evidence_kind="SYNTHETIC")[0])
    states = {int(s["as_of_receipt_seq"]): s for s in records(doc, "BOOK_STATE")}
    checked = 0
    for ev in events:
        if ev["venue"] != "kraken":
            continue
        engine.apply({"venue": "kraken", "kind": ev["kind"], "t_ms": ev["t_ms"],
                      "opcode": None if ev["opcode"] is None else int(ev["opcode"]), "payload": ev["payload"],
                      "status": None})
        state = states.get(ev["seq"])
        if state is None:
            continue
        snap = engine.snapshot()["kraken"]
        expected = {"SYNCED": "VALID", "NOT_INITIALIZED": "NOT_INITIALIZED",
                    "CONTINUITY_LOST": "CONTINUITY_LOST"}[snap["continuity"]]
        if expected == "NOT_INITIALIZED" and not snap["connected"]:
            expected = "SOURCE_UNAVAILABLE"
        assert state["native_state"] == expected, ev["seq"]
        if expected == "VALID":
            bid, bid_qty, ask, ask_qty = snap["top"]
            assert (Decimal(state["bids"][0][0]), Decimal(state["bids"][0][1])) == (bid, bid_qty)
            assert (Decimal(state["asks"][0][0]), Decimal(state["asks"][0][1])) == (ask, ask_qty)
            checked += 1
    assert checked > 1000
    assert [b["reason"] for b in engine.sources["kraken"].breaks] == [b["reason"] for b in doc["breaks"]]


def test_checksum_function_matches_the_pilot(journal):
    asks = [("62018.6", "0.5"), ("62018.7", "0.00100000")]
    bids = [("62018.5", "0.00064908"), ("62018.4", "1")]
    assert kr.kraken_checksum(asks, bids) == bbo_book.kraken_checksum(asks, bids)


# ------------------------------------------------------------------ liveness


def test_silences_follow_the_declared_policy(full):
    doc = full[1]
    assert doc["liveness_policy"]["max_gap_ms"] == "2000"
    reasons = [s["reason"] for s in doc["silences"]]
    assert reasons[0] == "SILENCE_UNATTESTED_BEFORE_PROOF" and reasons[-1] == "SILENCE_UNATTESTED_AFTER_LAST_PROOF"
    gaps = [s for s in doc["silences"] if s["reason"] == "SILENCE_GAP_EXCEEDS_MAX"]
    assert len(gaps) == 1  # the scheduled Kraken silence of the synthetic profile
    assert int(gaps[0]["to_t_ms"]) - int(gaps[0]["from_t_ms"]) > kr.LIVENESS_MAX_GAP_MS


# ------------------------------------------------------------------ bound and prefix


def test_prefix_replay_reproduces_every_record_up_to_the_bound(journal, full):
    doc = full[1]
    for bound in (9, 18, 2000, 5023, 5029):
        part = json.loads(kr.replay(*journal, corpus_id=CORPUS, evidence_kind="SYNTHETIC", receipt_bound=bound)[0])
        expected = [r for r in doc["records"]
                    if int(r["record"].get("receipt_seq") or r["record"]["as_of_receipt_seq"]) <= bound]
        assert part["records"] == expected, bound
        assert part["journal_prefix"]["receipt_bound"] == str(bound)


def test_appending_events_after_the_bound_never_changes_the_result(journal):
    bound = len(entries_of(journal[1]))
    longer = append_kraken_text(journal, b'{"channel":"heartbeat"}')
    a, seal_a = kr.replay(*journal, corpus_id=CORPUS, evidence_kind="SYNTHETIC", receipt_bound=bound)
    b, seal_b = kr.replay(*longer, corpus_id=CORPUS, evidence_kind="SYNTHETIC", receipt_bound=bound)
    assert a == b and seal_a != seal_b


# ------------------------------------------------------------------ refusals


def test_journal_integrity_failures_refuse_the_whole_replay(journal):
    manifest, events, frames = journal
    tampered = bytearray(frames)
    tampered[-1] ^= 1
    with pytest.raises(kr.ReplayRefusal, match="FRAMES_HASH_MISMATCH"):
        kr.load_journal(manifest, events, bytes(tampered))
    with pytest.raises(kr.ReplayRefusal, match="EVENTS_HASH_MISMATCH"):
        kr.load_journal(manifest, events + b"\n", frames)
    with pytest.raises(kr.ReplayRefusal, match="FRAME_HASH_MISMATCH"):
        kr.load_journal(*reseal(manifest, entries_of(events), bytes(tampered)))
    entries = entries_of(events)
    entries[5]["seq"] = 99
    with pytest.raises(kr.ReplayRefusal, match="EVENT_SEQ_NOT_CONTIGUOUS"):
        kr.load_journal(*reseal(manifest, entries, frames))
    entries = entries_of(events)
    entries[5]["t_ms"] += 1
    with pytest.raises(kr.ReplayRefusal, match="EVENT_TIME_INCONSISTENT_WITH_ANCHOR"):
        kr.load_journal(*reseal(manifest, entries, frames))
    unsealed = json.loads(manifest)
    del unsealed["sealed"]
    with pytest.raises(kr.ReplayRefusal, match="JOURNAL_NOT_SEALED"):
        kr.load_journal(json.dumps(unsealed).encode(), events, frames)


def test_a_synthetic_journal_cannot_be_declared_historical(journal):
    with pytest.raises(kr.ReplayRefusal, match="SYNTHETIC_JOURNAL_DECLARED_HISTORICAL"):
        kr.replay(*journal, corpus_id=CORPUS, evidence_kind="HISTORICAL")
    with pytest.raises(kr.ReplayRefusal, match="EVIDENCE_KIND_REFUSED"):
        kr.replay(*journal, corpus_id=CORPUS, evidence_kind="LIVE")


def test_a_trade_frame_is_refused_not_silently_ignored(journal):
    longer = append_kraken_text(journal, b'{"channel":"trade","type":"update","data":[]}')
    with pytest.raises(kr.ReplayRefusal, match="TRADE_CHANNEL_OUT_OF_SCOPE"):
        kr.replay(*longer, corpus_id=CORPUS, evidence_kind="SYNTHETIC")


def test_a_malformed_provider_frame_is_traced_not_dropped(journal):
    longer = append_kraken_text(journal, b'{"channel":"book","type":"update","data":[{"symbol":"BTC/USDT","bids":[{"price":1e3,"qty":1}],"asks":[],"checksum":1}]}')
    doc = json.loads(kr.replay(*longer, corpus_id=CORPUS, evidence_kind="SYNTHETIC")[0])
    last_raw = records(doc, "RAW_EVENT")[-1]
    assert last_raw["receipt_seq"] == str(len(entries_of(longer[1])))
    assert doc["breaks"][-1]["reason"] == "MESSAGE_INVALID"
    assert records(doc, "QUALITY_REPORT")[-1]["book_integrity"]["state"] == "INVALID"


def test_invalid_arguments_are_refused(journal):
    for kwargs, code in (({"corpus_id": "bad id"}, "CORPUS_ID_INVALID"),
                         ({"receipt_bound": 0}, "RECEIPT_BOUND_INVALID"),
                         ({"receipt_bound": 10**9}, "RECEIPT_BOUND_INVALID")):
        args = {"corpus_id": CORPUS, "evidence_kind": "SYNTHETIC", **kwargs}
        with pytest.raises(kr.ReplayRefusal, match=code):
            kr.replay(*journal, **args)
