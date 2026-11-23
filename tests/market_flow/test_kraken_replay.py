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


WALL0, MONO0 = 1_795_000_000_000, 40_000
HEARTBEAT = b'{"channel":"heartbeat"}'
SUBSCRIBE = b'{"method":"subscribe","params":{"channel":"book","symbol":["BTC/USDT"],"depth":10}}'


def snapshot_frame():
    """A one-level Kraken snapshot whose CRC32 matches its literals."""
    checksum = kr.kraken_checksum([("100.6", "2")], [("100.5", "1.25")])
    return ('{"channel":"book","type":"snapshot","data":[{"symbol":"BTC/USDT",'
            '"bids":[{"price":100.5,"qty":1.25}],"asks":[{"price":100.6,"qty":2}],'
            '"checksum":%d,"timestamp":"2026-11-20T07:06:32.000000Z"}]}' % checksum).encode()


def build(spec):
    """From-scratch SYNTHETIC sealed journal; spec = [(t offset in ms, venue, kind, payload)]."""
    frames, entries = b"", []
    for seq, (t, venue, kind, payload) in enumerate(spec, 1):
        entry = {"seq": seq, "venue": venue, "kind": kind, "recv_wall_ms": WALL0 + t, "recv_mono_ms": MONO0 + t,
                 "t_ms": WALL0 + t, "offset": len(frames), "bytes": len(payload),
                 "sha256": hashlib.sha256(payload).hexdigest()}
        if kind == "ws_message":
            entry["opcode"] = 2 if venue == "mexc" else 1
        frames += payload
        entries.append(entry)
    manifest = {"clock_anchor": {"wall_ms": WALL0, "mono_ms": MONO0}, "evidence_kind": "SYNTHETIC",
                "instrument": {"base_asset_id": "BTC", "quote_asset_id": "USDT"}, "market_type": "SPOT",
                "ws": {"kraken": {"symbol": "BTC/USDT", "depth": 10}}, "sealed": {}}
    return reseal(json.dumps(manifest).encode(), entries, frames)


def truncated(journal, bound):
    """The same journal physically cut after ``bound`` events and sealed again."""
    manifest, events, frames = journal
    entries = entries_of(events)[:bound]
    return reseal(manifest, entries, frames[:max((e["offset"] + e["bytes"] for e in entries), default=0)])


def silence(reason, starts, ends, last_proof, opened_by=None, closed_by=None):
    def ms(offset):
        return None if offset is None else str(WALL0 + offset)

    def seq(value):
        return None if value is None else str(value)

    return {"reason": reason, "starts_at_t_ms": ms(starts), "ends_before_t_ms": ms(ends),
            "last_proof_receipt_seq": seq(last_proof and last_proof[0]), "last_proof_t_ms": ms(last_proof and last_proof[1]),
            "opened_by_receipt_seq": seq(opened_by), "closed_by_receipt_seq": seq(closed_by)}


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
    silences = doc["silences"]
    assert all(set(s) == kr.SILENCE_KEYS for s in silences)
    assert [s["reason"] for s in silences] == ["SILENCE_UNATTESTED_BEFORE_FIRST_PROOF", "SILENCE_GAP_EXCEEDS_MAX",
                                               "SILENCE_UNATTESTED_AFTER_LAST_PROOF"]
    gap = silences[1]  # the scheduled Kraken silence of the synthetic profile
    assert int(gap["starts_at_t_ms"]) == int(gap["last_proof_t_ms"]) + kr.LIVENESS_MAX_GAP_MS
    assert int(gap["ends_before_t_ms"]) > int(gap["starts_at_t_ms"])
    raw = {r["receipt_seq"] for r in records(doc, "RAW_EVENT")}
    assert {gap["last_proof_receipt_seq"], gap["closed_by_receipt_seq"]} <= raw
    last = silences[-1]
    assert int(last["starts_at_t_ms"]) == int(last["last_proof_t_ms"]) + kr.LIVENESS_MAX_GAP_MS
    assert last["ends_before_t_ms"] is None and last["closed_by_receipt_seq"] is None


def two_proofs(apart_ms):
    """Proof p at +100 ms, then only frames that attest nothing about Kraken, then proof q."""
    return build([
        (0, "kraken", "ws_open", b""),                        # 1  proof
        (10, "kraken", "sent", SUBSCRIBE),                    # 2  our own frame
        (100, "kraken", "ws_message", snapshot_frame()),      # 3  proof p
        (1100, "mexc", "ws_message", b"\x0a\x00"),            # 4  another venue
        (1600, "kraken", "sent", b'{"method":"ping"}'),       # 5  our own frame
        (2100, "mexc", "ws_message", b"\x0a\x01"),            # 6  another venue, at the expiry of p
        (100 + apart_ms, "kraken", "ws_message", HEARTBEAT),  # 7  proof q
        (600 + apart_ms, "kraken", "ws_message", HEARTBEAT),  # 8  proof
    ])


def test_proofs_2001_ms_apart_open_a_silence_at_the_expiry_of_the_first():
    doc = json.loads(kr.replay(*two_proofs(2001), corpus_id=CORPUS, evidence_kind="SYNTHETIC")[0])
    assert doc["silences"] == [
        silence("SILENCE_UNATTESTED_BEFORE_FIRST_PROOF", None, 0, None, closed_by=1),
        silence("SILENCE_GAP_EXCEEDS_MAX", 2100, 2101, (3, 100), closed_by=7),
        silence("SILENCE_UNATTESTED_AFTER_LAST_PROOF", 4601, None, (8, 2601)),
    ]
    assert records(doc, "QUALITY_REPORT")[-1]["book_integrity"]["state"] == "VERIFIED"
    assert records(doc, "QUALITY_REPORT")[-1]["book_freshness"]["state"] == "UNKNOWN"  # liveness is not freshness


def test_proofs_2000_ms_apart_leave_no_silence_between_them():
    doc = json.loads(kr.replay(*two_proofs(2000), corpus_id=CORPUS, evidence_kind="SYNTHETIC")[0])
    assert doc["silences"] == [
        silence("SILENCE_UNATTESTED_BEFORE_FIRST_PROOF", None, 0, None, closed_by=1),
        silence("SILENCE_UNATTESTED_AFTER_LAST_PROOF", 4600, None, (8, 2600)),
    ]


@pytest.mark.parametrize("bound", [3, 5, 6])
def test_a_replay_bounded_before_the_next_frame_only_knows_what_was_received(bound):
    """Two futures, one prefix: the verdict at the bound is the same and never cites q."""
    late, on_time = two_proofs(2001), two_proofs(2000)
    verdicts = [kr.replay(*j, corpus_id=CORPUS, evidence_kind="SYNTHETIC", receipt_bound=bound)[0]
                for j in (late, on_time, truncated(late, bound), truncated(on_time, bound))]
    assert len(set(verdicts)) == 1  # byte-identical, including a journal that stops at the bound
    doc = json.loads(verdicts[0])
    assert doc["silences"] == [
        silence("SILENCE_UNATTESTED_BEFORE_FIRST_PROOF", None, 0, None, closed_by=1),
        silence("SILENCE_UNATTESTED_AFTER_LAST_PROOF", 2100, None, (3, 100)),
    ]
    assert doc["journal_prefix"]["receipt_bound"] == str(bound)


def test_a_disconnection_is_unattested_until_the_reconnection_proves_again():
    snap = snapshot_frame()
    after_expiry = build([(0, "kraken", "ws_open", b""), (100, "kraken", "ws_message", snap),
                          (2500, "kraken", "ws_close", b""), (4000, "kraken", "ws_open", b""),
                          (4010, "kraken", "sent", SUBSCRIBE), (4100, "kraken", "ws_message", snap)])
    doc = json.loads(kr.replay(*after_expiry, corpus_id=CORPUS, evidence_kind="SYNTHETIC")[0])
    assert doc["silences"] == [
        silence("SILENCE_UNATTESTED_BEFORE_FIRST_PROOF", None, 0, None, closed_by=1),
        silence("SILENCE_GAP_EXCEEDS_MAX", 2100, 2500, (2, 100), closed_by=3),
        silence("SILENCE_UNATTESTED_AFTER_DISCONNECT", 2500, 4000, (2, 100), opened_by=3, closed_by=4),
        silence("SILENCE_UNATTESTED_AFTER_LAST_PROOF", 6100, None, (6, 4100)),
    ]
    before_expiry = build([(0, "kraken", "ws_open", b""), (100, "kraken", "ws_message", snap),
                           (1500, "kraken", "ws_error", b""), (1700, "kraken", "ws_close", b""),
                           (4000, "kraken", "ws_open", b"")])
    doc = json.loads(kr.replay(*before_expiry, corpus_id=CORPUS, evidence_kind="SYNTHETIC")[0])
    assert doc["silences"] == [
        silence("SILENCE_UNATTESTED_BEFORE_FIRST_PROOF", None, 0, None, closed_by=1),
        silence("SILENCE_UNATTESTED_AFTER_DISCONNECT", 1500, 4000, (2, 100), opened_by=3, closed_by=5),
        silence("SILENCE_UNATTESTED_AFTER_LAST_PROOF", 6000, None, (5, 4000)),
    ]
    assert [b["reason"] for b in doc["breaks"]] == ["DISCONNECTED"]


# ------------------------------------------------------------------ bound and prefix


def test_prefix_replay_reproduces_every_record_up_to_the_bound(journal, full):
    doc = full[1]
    gap = doc["silences"][1]
    last_proof, closing = int(gap["last_proof_receipt_seq"]), int(gap["closed_by_receipt_seq"])
    for bound in (9, 18, 2000, 5023, 5029, last_proof, closing - 1, closing):
        part = json.loads(kr.replay(*journal, corpus_id=CORPUS, evidence_kind="SYNTHETIC", receipt_bound=bound)[0])
        expected = [r for r in doc["records"]
                    if int(r["record"].get("receipt_seq") or r["record"]["as_of_receipt_seq"]) <= bound]
        assert part["records"] == expected, bound
        assert part["journal_prefix"]["receipt_bound"] == str(bound)
        closed = [s for s in doc["silences"]
                  if s["closed_by_receipt_seq"] is not None and int(s["closed_by_receipt_seq"]) <= bound]
        assert part["silences"][:-1] == closed, bound  # what the bound has seen closing, nothing more
        assert part["silences"][-1]["ends_before_t_ms"] is None, bound
    inside = json.loads(kr.replay(*journal, corpus_id=CORPUS, evidence_kind="SYNTHETIC", receipt_bound=closing - 1)[0])
    assert inside["silences"][-1] == {**gap, "reason": "SILENCE_UNATTESTED_AFTER_LAST_PROOF",
                                      "ends_before_t_ms": None, "closed_by_receipt_seq": None}


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
