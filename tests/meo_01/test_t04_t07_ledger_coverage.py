"""T4 deduplication, T5 id contiguity, T6 transport vs trade coverage, T7 as_of and determinism."""

from observability.market_flow import kraken_trades as kt

from ._support import ACK, HEARTBEAT, MS, T0, frame, item, journal, report, steady


# ---------------------------------------------------------------- T4 deduplication

def test_t04_snapshot_update_overlap_counts_once():
    rows = steady(400)
    snap = frame([item(1000 + i, T0 - 60_000 + i * 1000, side="buy" if i % 3 else "sell") for i in range(5)],
                 "snapshot")
    rows.insert(1, (T0 - 60_000 - 1, "ws_message", snap))  # replays trades 1000..1004 before their updates
    r = report(rows)
    assert r["ledger"]["duplicates"] == 5
    assert r["ledger"]["conflicts_count"] == 0
    assert r["frames"]["trade_snapshot"] == 1
    assert r["trade_coverage"]["id_gaps_count"] == 0


def test_t04_same_id_with_other_content_is_a_kept_conflict_and_cuts_coverage():
    rows = steady(700)
    rows.append((T0 + 1_000_000, "ws_message", frame([item(1100, T0 + 40_000, price="1.0")])))
    r = report(rows, as_of_ns=(T0 + 700_000) * MS)
    assert r["ledger"]["conflicts_count"] == 0  # the contradicting copy arrives after as_of
    r = report(rows)
    assert r["ledger"]["conflicts"] == [{"trade_id": "1100", "session_id": "ws-1"}]
    spans = [[int(a), int(b)] for a, b in r["trade_coverage"]["spans_ns"]]
    t1100 = (T0 + 40_000) * MS
    assert all(not (a <= t1100 < b) for a, b in spans)  # the conflicted trade time is not covered
    assert r["windows"][1]["status"] == "PARTIALLY_COVERED"


# ---------------------------------------------------------------- T5 contiguity

def test_t05_id_gaps_are_listed_and_never_filled():
    r = report(steady(700, skip={1100, 1101, 1300}))
    cov = r["trade_coverage"]
    assert cov["id_gaps"] == [{"after_id": "1099", "before_id": "1102", "missing": 2},
                              {"after_id": "1299", "before_id": "1301", "missing": 1}]
    assert cov["missing_ids_total"] == 3 and cov["runs"] == 3
    assert r["ledger"]["accepted"] == 697
    assert r["hypotheses"]["H2_trade_id_plus_one"]["status"] == "UNKNOWN"  # no REST to decide
    # Windows touching a gap are not COVERED; their totals stay null (never a partial sum).
    for w in r["windows"]:
        if w["status"] != "COVERED":
            assert w["totals"] is None and w["side_coverage"] is None and w["delta_300s"] is None


def test_t05_time_inversion_inside_contiguous_ids_cuts_the_run():
    r = report(steady(50, mutate=lambda tid, at, it: item(tid, at - 5_000) if tid == 1010 else it))
    assert r["trade_coverage"]["time_inversions"] == 1
    assert r["hypotheses"]["H5_order_and_time_follow_ids"]["status"] == "REFUTED"


def test_t05_in_frame_id_order_is_checked():
    rows = steady(3)
    rows.append((T0, "ws_message", frame([item(2001, T0 - 10), item(2000, T0 - 10)])))
    r = report(rows)
    assert r["hypotheses"]["H5_order_and_time_follow_ids"]["evidence"]["in_frame_id_inversions"] == 1


# ---------------------------------------------------------------- T6 transport vs coverage

def test_t06_transport_continuity_and_trade_coverage_are_separate():
    # Heartbeats keep the transport alive, but ids jump: coverage is cut, transport is not.
    rows = steady(700, skip=set(range(1100, 1110)))
    rows += [(T0 - 60_000 + k * 1000 + 500, "ws_message", HEARTBEAT) for k in range(700)]
    rows.sort(key=lambda e: e[0])
    r = report(rows)
    assert len(r["transport_continuity"]["spans_ns"]) == 1
    assert r["trade_coverage"]["id_gaps_count"] == 1
    w = r["windows"][1]
    assert w["status"] == "PARTIALLY_COVERED" and w["transport_continuous_receipt_axis"] is True
    assert {b["status"] for b in w["bars"]} >= {"NOT_COVERED", "OBSERVED"}
    for b in w["bars"]:
        if b["status"] == "NOT_COVERED":
            assert b["trade_count"] is None and b["delta_base"] is None and b["cvd_base_bounds"] is None


def test_t06_silence_cuts_transport_and_cvd_restarts_after_a_gap():
    rows = [r for r in steady(700) if not (T0 + 100_000 <= r[0] < T0 + 120_000)]  # 20 s silent, ids lost
    r = report(rows)
    assert len(r["transport_continuity"]["spans_ns"]) == 2
    segments = [b["segment"] for b in r["windows"][1]["bars"]]
    assert None in segments
    covered = [b["segment"] for w in r["windows"] for b in w["bars"] if b["segment"] is not None]
    assert covered == sorted(covered) and len(set(covered)) == 2  # CVD restarts, never bridges


def test_t06_close_ends_transport_and_unknown_coverage_is_never_complete():
    rows = [(T0 - 1, "ws_message", ACK), (T0 + 5_000, "ws_close", b"")]
    r = report(rows)
    assert r["trade_coverage"]["state"] == "UNKNOWN"
    assert r["trade_coverage"]["reason"] == "NO_CONTIGUOUS_TRADE_ID_RUN"
    assert r["windows"] == [] and r["exit_window"] is None
    assert r["transport_continuity"]["spans_ns"] == [[str((T0 - 1) * MS), str((T0 + 2_000 - 1) * MS)]]
    # A single trade proves nothing about its neighbours.
    r = report([(T0 - 1, "ws_message", ACK), (T0 + 10, "ws_message", frame([item(5, T0)]))])
    assert r["trade_coverage"]["state"] == "UNKNOWN"


def test_t06_tail_after_the_last_trade_is_not_covered():
    r = report(steady(700), as_of_ns=(T0 + 900_000) * MS)  # the journal stops earlier; the clock does not
    end = int(r["trade_coverage"]["spans_ns"][-1][1])
    bars = [b for w in r["windows"] for b in w["bars"]]
    after = [b for b in bars if int(b["end_ns"]) > end]
    assert after and all(b["status"] == "NOT_COVERED" and b["trade_count"] is None for b in after)
    assert r["windows"][-1]["status"] == "NOT_COVERED"


def test_t06_event_after_receipt_is_excluded_and_cuts_coverage():
    r = report(steady(700, mutate=lambda tid, at, it: item(tid, at + 5_000) if tid == 1100 else it))
    assert r["ledger"]["excluded"]["future_event_time"] == 1
    assert r["trade_coverage"]["id_gaps"][0]["after_id"] == "1099"


# ---------------------------------------------------------------- T7 as_of and determinism

def test_t07_frames_after_as_of_are_not_read_and_output_is_byte_identical():
    rows = steady(700)
    as_of = (T0 + 400_000) * MS
    a = report(rows, as_of_ns=as_of)
    b = report(rows, as_of_ns=as_of)
    assert kt.canonical(a) == kt.canonical(b)
    assert a["events_after_as_of_not_read"] > 0
    extra = rows + [(T0 + 500_000, "ws_message", frame([item(9999, T0 + 100_000, qty="99")]))]
    c = report(extra, as_of_ns=as_of)
    for k in ("windows", "trade_coverage", "ledger", "transport_continuity", "exit_window"):
        assert c[k] == a[k], k
    assert all(int(t) <= as_of for s in a["transport_continuity"]["spans_ns"] for t in s)


def test_t07_report_has_no_float_and_states_its_time_bases():
    r = report(steady(700))

    def walk(x):
        assert not isinstance(x, float)
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(r)
    assert r["time_bases"]["bars_axis"] == "NATIVE_TIMESTAMP_UNQUALIFIED"
    assert r["time_bases"]["receipt_axis"] == "HOST_UTC_RECEIPT_NS"
    assert r["time_bases"]["receipt_clock_check"] == {"reference": "KRAKEN_PUBLIC_TIME_1S", "start_offset_ms": 12,
                                                       "end_offset_ms": -8, "tolerance_ms": 2000}
    assert r["synthetic"] is True
    m, e = journal(steady(3), evidence_kind="OBSERVATION")
    assert kt.replay_journal(m, e)["synthetic"] is False
