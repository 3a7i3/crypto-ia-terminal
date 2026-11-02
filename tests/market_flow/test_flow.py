"""CryptoRadar Flux core: synthetic counter-examples. No network, no clock, no runtime."""

import ast
import copy
import importlib.util
import json
from pathlib import Path
import socket

import pytest

from observability.market_flow import artifact, fixtures, heatmap, interval, l2, trades as tr

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "observability/market_flow"
S, A, BAR = fixtures.S, fixtures.ANCHOR, fixtures.BAR
GOLDEN = PKG / "fixtures/market_flow_artifact_synthetic.json"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def session():
    return fixtures.synthetic_session()


def rec(tid, side, price, size, *, ev=1, quote="USD", instrument="BTC-USD"):
    return {"trade_id": tid, "instrument": instrument, "quote": quote, "price": price,
            "size": size, "side": side, "event_ns": ev}


def make_flow(**kw):
    base = dict(venue="v", instrument="BTC-USD", base="BTC", quote="USD", market_kind="SPOT",
                id_domain="SESSION", side=fixtures.NO_ATTESTATION)
    base.update(kw)
    return tr.TradeFlow(**base)


def ledger(flow, items):
    led = tr.TradeLedger(flow)
    for i, (r, session_id, received) in enumerate(items):
        led.ingest(r, session_id=session_id, received_ns=received, arrival_seq=i)
    return led


def bars_of(led, anchor=0, bar=10, as_of=30, cov=((0, 30),)):
    return tr.build_bars(led, anchor_ns=anchor, bar_ns=bar, as_of_ns=as_of, coverage=list(cov))


# ---- delta / CVD ---------------------------------------------------------
def test_fixture_bar_deltas_distinguish_exact_zero_partial_uncovered_and_session_break():
    ev, cfg = session()
    d = artifact.replay(ev, cfg)
    b = d["bars"]
    assert (b[0]["delta_status"], b[0]["delta_base"]) == ("EXACT", "0.7")
    assert b[1]["status"] == "OBSERVED_ZERO" and b[1]["delta_base"] == "0" and b[1]["trade_count"] == 0
    assert b[2]["delta_status"] == "PARTIAL_UNKNOWN_SIDE" and b[2]["delta_base"] is None
    assert b[2]["delta_base_bounds"] == ["-0.75", "0.25"]  # -0.25 sell, +-0.5 unknown
    assert b[3]["status"] == "NOT_COVERED" and b[3]["trade_count"] is None  # unknown is not zero
    assert b[4]["status"] == "SESSION_BREAK_UNRESOLVED" and b[4]["delta_base"] is None


def test_cvd_is_a_running_sum_inside_a_segment_with_bounds_when_a_side_is_unknown():
    ev, cfg = session()
    b = artifact.replay(ev, cfg)["bars"]
    assert [x["cvd_base"] for x in b[:2]] == ["0.7", "0.7"]
    assert b[2]["cvd_base"] is None and b[2]["cvd_base_bounds"] == ["-0.05", "0.95"]
    assert {x["segment"] for x in b[:3]} == {0}


def test_cvd_restarts_after_a_gap_instead_of_bridging_it():
    f = make_flow()
    led = ledger(f, [(rec("a", "B", "10", "1", ev=1), "s", 2), (rec("b", "B", "10", "2", ev=21), "s", 22)])
    b = bars_of(led, cov=((0, 10), (20, 30)))["bars"]
    assert [x["status"] for x in b] == ["OBSERVED", "NOT_COVERED", "OBSERVED"]
    assert (b[0]["segment"], b[2]["segment"]) == (0, 1)
    assert b[2]["cvd_base"] == "2"  # not 3: the missing bar is not invented


def test_duplicate_is_dropped_conflict_is_kept_as_evidence():
    f = make_flow()
    led = ledger(f, [(rec("a", "B", "10", "1"), "s", 2), (rec("a", "B", "10", "1"), "s", 3),
                     (rec("a", "B", "11", "1"), "s", 4)])
    assert len(led.trades) == 1 and led.duplicates == 1
    assert led.conflicts == [{"trade_id": "a", "session_id": "s"}]


def test_same_id_on_two_venues_or_instruments_is_not_a_duplicate():
    a = ledger(make_flow(venue="v1"), [(rec("x", "B", "10", "1"), "s", 2)])
    b = ledger(make_flow(venue="v2"), [(rec("x", "B", "10", "1"), "s", 2)])
    assert len(a.trades) == len(b.trades) == 1  # separate ledgers: keys include venue and instrument
    assert a._key(a.trades[0]) != b._key(b.trades[0])


def test_instrument_scoped_ids_deduplicate_across_a_reconnect_but_session_scoped_do_not():
    items = [(rec("x", "B", "10", "1"), "s1", 2), (rec("x", "B", "10", "1"), "s2", 3)]
    inst = ledger(make_flow(id_domain="INSTRUMENT"), items)
    assert len(inst.trades) == 1 and inst.duplicates == 1
    sess = ledger(make_flow(id_domain="SESSION"), items)
    assert len(sess.trades) == 2  # cannot tell replay from new trade: bar will be flagged
    assert bars_of(sess)["bars"][0]["status"] == "SESSION_BREAK_UNRESOLVED"


def test_inverted_maker_taker_convention_flips_the_sign_and_is_declared():
    inv = tr.SideConvention((("B", tr.SELL), ("S", tr.BUY)), attested=False, evidence_ref="SYNTH")
    led = ledger(make_flow(side=inv), [(rec("a", "B", "10", "3"), "s", 2)])
    assert bars_of(led)["bars"][0]["delta_base"] == "-3"
    ev, cfg = session()
    assert artifact.replay(ev, cfg)["flow"]["side_convention"]["attested"] is False


@pytest.mark.parametrize("raw", [None, "", "buy", "BUY", "?", 1, ["B"]])
def test_absent_or_unmapped_side_is_never_a_default_buy_or_sell(raw):
    led = ledger(make_flow(), [(rec("a", raw, "10", "3"), "s", 2)])
    b = bars_of(led)["bars"][0]
    assert b["buy_volume"] == b["sell_volume"] == "0" and b["unknown_volume"] == "3"
    assert b["delta_base"] is None and b["delta_base_bounds"] == ["-3", "3"]


def test_quote_currency_is_never_relabelled_and_missing_id_is_not_counted():
    led = ledger(make_flow(), [(rec("a", "B", "10", "1", quote="USDT"), "s", 2),
                               (rec("b", "B", "10", "1", instrument="ETH-USD"), "s", 2),
                               ({**rec("c", "B", "10", "1"), "trade_id": None}, "s", 2)])
    assert led.refused == {"QUOTE_MISMATCH": 1, "INSTRUMENT_MISMATCH": 1, "TRADE_ID_REQUIRED": 1}
    assert led.trades == []


@pytest.mark.parametrize("bad", [10, 10.5, "1e3", "-1", "0", "", None, True])
def test_prices_and_sizes_are_exact_positive_decimal_text(bad):
    led = ledger(make_flow(), [(rec("a", "B", bad, "1"), "s", 2), (rec("b", "B", "1", bad), "s", 2)])
    assert led.trades == []


def test_future_missing_and_out_of_range_event_times_are_excluded_and_counted():
    f = make_flow()
    led = ledger(f, [(rec("a", "B", "10", "1", ev=99), "s", 5), (rec("b", "B", "10", "1", ev=None), "s", 5),
                     (rec("c", "B", "10", "1", ev=2), "s", 5)])
    out = bars_of(led)
    assert out["excluded"] == {"no_event_time": 1, "future_event_time": 1, "outside_range": 0}
    assert out["bars"][0]["trade_count"] == 1


def test_exact_arithmetic_with_nine_decimals_and_ns_beyond_js_safe_integers():
    big = 2**60
    led = ledger(make_flow(), [(rec("a", "B", "0.000000001", "0.000000003", ev=big + 1), "s", big + 2)])
    out = tr.build_bars(led, anchor_ns=big, bar_ns=10, as_of_ns=big + 10, coverage=[(big, big + 10)])
    b = out["bars"][0]
    assert b["buy_volume"] == "0.000000003" and b["buy_notional"] == "0.000000000000000003"
    assert b["start_ns"] == str(big) and isinstance(b["start_ns"], str)


def test_rolling_delta_expires_without_any_new_trade():
    led = ledger(make_flow(), [(rec("a", "B", "10", "5", ev=1), "s", 2)])
    early = tr.rolling_delta(bars_of(led, as_of=10, cov=((0, 40),))["bars"], 10, [10])
    later = tr.rolling_delta(bars_of(led, as_of=40, cov=((0, 40),))["bars"], 10, [10, 20, 40])
    assert early["10"]["delta_base"] == "5"
    assert later["10"]["delta_base"] == "0" and later["20"]["delta_base"] == "0"  # trade aged out
    assert later["40"]["delta_base"] == "5"
    assert tr.rolling_delta([], 10, [10])["10"]["reason"] == "WINDOW_BEFORE_ANCHOR"


def test_rolling_delta_refuses_incomplete_coverage_or_unresolved_bars():
    ev, cfg = session()
    d = artifact.replay(ev, cfg)
    assert all(v["status"] == "NOT_AVAILABLE" for v in d["rolling_delta"].values())


def test_bar_boundaries_are_half_open_on_event_time():
    led = ledger(make_flow(), [(rec("a", "B", "10", "1", ev=10), "s", 11), (rec("b", "B", "10", "1", ev=9), "s", 11)])
    b = bars_of(led)["bars"]
    assert (b[0]["trade_count"], b[1]["trade_count"]) == (1, 1)


def test_invalid_geometry_and_coverage_are_refused():
    led = ledger(make_flow(), [])
    for kw in ({"bar_ns": 0}, {"as_of": -1}):
        with pytest.raises(ValueError):
            bars_of(led, **{("bar" if k == "bar_ns" else "as_of"): v for k, v in kw.items()})
    with pytest.raises(ValueError):
        bars_of(led, cov=((5, 5),))


def test_mixed_quotes_cannot_be_summed_there_is_no_cross_ledger_api():
    assert not hasattr(tr, "merge_series")  # absence is the contract until a conversion contract exists


# ---- replay ---------------------------------------------------------------
def test_replay_is_deterministic_and_matches_the_golden_file():
    ev, cfg = session()
    one = artifact.canonical(artifact.replay(ev, cfg))
    two = artifact.canonical(artifact.replay(copy.deepcopy(ev), cfg))
    assert one == two
    assert json.loads(one) == json.loads(GOLDEN.read_text())


def test_replay_never_reads_events_received_after_as_of():
    ev, cfg = session()
    full = artifact.replay(ev, cfg)
    assert full["inputs"]["events_after_as_of_not_read"] == 1
    cut = [e for e in ev if not (e["kind"] == "trade" and e["record"].get("trade_id") == "t8")]
    assert artifact.canonical({**full, "inputs": {}}) == artifact.canonical({**artifact.replay(cut, cfg), "inputs": {}})
    early = {**cfg, "as_of_receipt_ns": A + 100 * S}
    d = artifact.replay(ev, early)
    assert all(b["end_ns"] <= str(A + 100 * S) for b in d["bars"])
    assert d["trades"]["accepted"] == 3 and d["bars"][-1]["index"] == 0


def test_validator_is_closed_and_refuses_floats_scores_and_unmarked_evidence():
    ev, cfg = session()
    good = artifact.replay(ev, cfg)
    assert artifact.validate_artifact(copy.deepcopy(good))
    for mutate in (
        lambda d: d.update(extra=1),
        lambda d: d.update(score="9"),
        lambda d: d.update(recommendation="buy"),
        lambda d: d.update(synthetic=False),
        lambda d: d.update(evidence_kind="LIVE"),
        lambda d: d.update(anchor_ns=1000),
        lambda d: d["bars"][0].update(start_ns=5),
        lambda d: d["bars"][3].update(trade_count=0),
        lambda d: d["bars"][0].update(open=1.5),
        lambda d: d.update(schema_version="2.0.0"),
    ):
        bad = copy.deepcopy(good)
        mutate(bad)
        with pytest.raises(ValueError):
            artifact.validate_artifact(bad)


# ---- heatmap and level lifecycle --------------------------------------------
def test_heatmap_separates_sides_uses_half_open_ticks_and_keeps_zero_distinct_from_unknown():
    ev, cfg = session()
    d = artifact.replay(ev, cfg)
    col0 = d["heatmap"]["columns"][0]
    assert col0["status"] == "LIVE"
    # last live sample of bucket 0 (after the 1001 ask was removed), tick 0.5 from 998:
    # bids 999.5 -> row 3, 1000 -> row 4, 1000.5 -> row 5 ; asks 1002 -> row 8 (1001 is gone)
    assert col0["bids"] == [[3, "1"], [4, "2"], [5, "5"]] and col0["asks"] == [[8, "4"]]
    assert d["heatmap"]["unit"] == "DISPLAYED_BASE_QUANTITY"
    assert "OBSERVED_ZERO" in d["heatmap"]["zero_semantics"]


def test_heatmap_marks_buckets_without_a_live_book_instead_of_drawing_zeros():
    ev, cfg = session()
    ev = [e for e in ev if e["kind"] != "sample"]
    cols = artifact.replay(ev, cfg)["heatmap"]["columns"]
    assert [c["status"] for c in cols] == ["LIVE", "NO_SAMPLE", "LIVE", "NO_SAMPLE", "LIVE"]
    assert all("bids" not in c for c in cols if c["status"] != "LIVE")


def test_silent_connection_sample_is_not_live():
    ev, cfg = session()
    cfg = {**cfg, "silence_budget_ns": 10 * S}
    cols = artifact.replay(ev, cfg)["heatmap"]["columns"]
    assert cols[1]["status"] == "BOOK_STALE_BY_SILENCE"


def test_truncated_depth_does_not_claim_coverage_beyond_the_last_known_level():
    ev, cfg = session()
    cfg = {**cfg, "depth_levels_limit": 2}
    col0 = artifact.replay(ev, cfg)["heatmap"]["columns"][0]
    assert col0["bid_cover_floor"] == "999.5"  # 3 bids >= declared limit 2: nothing below is vouched for
    assert col0["ask_cover_ceiling"] is None  # one ask < limit: the ask side is complete


def test_disappearance_has_no_cause_and_trades_are_evidence_counts_not_explanations():
    ev, cfg = session()
    items = artifact.replay(ev, cfg)["level_events"]["items"]
    gone = [e for e in items if e["kind"] == "DISAPPEARED"]
    assert len(gone) == 1 and gone[0]["cause"] == "CAUSE_UNDETERMINED"
    assert gone[0]["left_censored"] is True and gone[0]["persistence_ns"]["max"] is None
    assert "spoof" not in json.dumps(items).lower()


def test_level_leaving_a_truncated_depth_is_not_reported_as_a_disappearance():
    mk = lambda t, bids, asks: {"receipt_ns": t, "state": "LIVE", "limit": 2,  # noqa: E731
                                "bids": [(l2.Decimal(p), l2.Decimal(q), p, q) for p, q in bids],
                                "asks": [(l2.Decimal(p), l2.Decimal(q), p, q) for p, q in asks]}
    s1 = mk(1, [("10", "1"), ("9", "1")], [("11", "1"), ("12", "1")])
    s2 = mk(2, [("10", "1"), ("9.5", "1")], [("11", "1"), ("12", "1")])  # 9 fell out of the 2-level window
    ev, _ = heatmap.level_events([s1, s2], as_of_ns=5)
    assert [e["kind"] for e in ev if e["side"] == "bid" and e["price"] == "9"] == ["LEFT_COVERED_DEPTH"]


def test_lifecycle_is_not_bridged_across_a_non_live_sample():
    mk = lambda t, state, bids: {"receipt_ns": t, "state": state, "limit": None,  # noqa: E731
                                 "bids": bids, "asks": []}
    q = [(l2.Decimal("10"), l2.Decimal("1"), "10", "1")]
    ev, _ = heatmap.level_events([mk(1, "LIVE", q), mk(2, "INVALID", None), mk(3, "LIVE", [])], as_of_ns=9)
    assert ev == []  # nothing is claimed about the gap


def test_per_venue_layers_exist_only_as_separate_artifacts_no_cross_venue_sum():
    assert not hasattr(heatmap, "merge_layers")


# ---- L2 equivalence and package hygiene -----------------------------------------
def test_l2_module_matches_the_reviewed_prototype_on_the_prototype_fixtures():
    spec = importlib.util.spec_from_file_location("proto551", ROOT / "docs/research/market_v0_551/l2_reconstruction_prototype.py")
    proto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proto)
    fix = json.loads((ROOT / "docs/research/market_v0_551/SYNTHETIC_L2_FIXTURES.json").read_text())["scenarios"]
    for name, msgs in fix.items():
        a, b = l2.L2Connection("c", l2.COINBASE_L2_FLOW), proto.L2Connection("c", proto.COINBASE_L2_FLOW)
        for i, m in enumerate(msgs):
            ra = a.feed(json.dumps(m).encode(), l2.Receipt(interval.Span(i, i + 1), interval.Span(i, i + 1)))
            rb = b.feed(json.dumps(m).encode(), proto.Receipt(proto.Span(i, i + 1), proto.Span(i, i + 1)))
            assert ra == rb, name
        for p in ("BTC-USD", "ETH-USD"):
            assert a.state(p) == b.state(p) and a.bbo(p) == b.bbo(p), name


def test_interval_copy_is_byte_identical_apart_from_its_pinned_header():
    orig = (ROOT / "docs/research/market_time_attestation_546/interval_reference.py").read_text()
    copy_ = (PKG / "interval.py").read_text()
    header = "Copy of docs/research/market_time_attestation_546/interval_reference.py (pinned by a test).\n\n"
    assert copy_.replace(header, "", 1) == orig


def test_package_has_no_transport_clock_write_or_float_and_nobody_imports_it():
    banned = {"socket", "ssl", "http", "urllib", "asyncio", "time", "requests", "websockets", "subprocess", "os", "random", "datetime_now"}
    for path in PKG.glob("*.py"):
        tree = ast.parse(path.read_text())
        imported = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imported |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                imported.add(n.module.split(".")[0])
        assert not imported & banned, path.name
        assert path.name == "artifact.py" or not any(isinstance(n, ast.Name) and n.id == "float" for n in ast.walk(tree)), path.name  # artifact.py only uses it to REFUSE floats
        assert not any(isinstance(n, ast.Constant) and isinstance(n.value, float) for n in ast.walk(tree)), path.name
        assert "now()" not in path.read_text() and "open(" not in path.read_text(), path.name
    hits = []
    for base in ("observability", "core", "paper_trading", "market_data", "trade_analysis", "frontend/src"):
        for p in (ROOT / base).rglob("*"):
            if p.suffix in (".py", ".ts", ".tsx") and p.is_file() and "market_flow" not in str(p.relative_to(ROOT)).split("/")[:2]:
                if "market_flow" in p.read_text(errors="ignore"):
                    hits.append(str(p))
    assert hits == []


def test_bars_never_include_a_trade_received_after_as_of_even_if_its_event_time_is_inside():
    led = ledger(make_flow(), [(rec("a", "B", "10", "1", ev=5), "s", 6), (rec("b", "B", "10", "1", ev=6), "s", 31)])
    assert bars_of(led)["bars"][0]["trade_count"] == 1  # the second arrives after as_of=30
