"""Regressions for the independent review of #554 (F1-F5). Synthetic, offline."""

import copy
from dataclasses import replace
from decimal import Decimal, localcontext

import pytest

from observability.market_flow import artifact, fixtures, heatmap, trades as tr

S, A, BAR = fixtures.S, fixtures.ANCHOR, fixtures.BAR
BIG = "123456789012345678901234567890"  # 30 digits: accepted input


def rec(tid, side, price, size, ev=1):
    return {"trade_id": tid, "instrument": "BTC-USD", "quote": "USD", "price": price, "size": size,
            "side": side, "event_ns": ev}


def bars_for(records):
    led = tr.TradeLedger(fixtures.FLOW)
    for i, r in enumerate(records):
        assert led.ingest(r, session_id="s", received_ns=2 + i, arrival_seq=i) == "ACCEPTED"
    return tr.build_bars(led, anchor_ns=0, bar_ns=10, as_of_ns=10, coverage=[(0, 10)])["bars"][0]


# ----------------------------------------------------------------------------- F1

@pytest.mark.parametrize("prec", [1, 5, 28, 50])
def test_f1_result_does_not_depend_on_the_ambient_decimal_context(prec):
    with localcontext() as ctx:
        ctx.prec = prec
        bar = bars_for([rec("a", "B", "1", BIG)])
        assert Decimal(bar["buy_volume"]) == Decimal(BIG)
        assert bar["delta_base"] == BIG and bar["delta_status"] == "EXACT"
        assert ctx.prec == prec  # the caller's context is restored


def test_f1_cancellation_and_notional_are_exact():
    p = "999999999999999999999999999999.999999999999999999999999999999"
    bar = bars_for([rec("a", "B", p, BIG, ev=1), rec("b", "S", p, BIG, ev=2), rec("c", "B", "1", "0.000000000000000000000000000001", ev=3)])
    assert bar["delta_base"] == "0.000000000000000000000000000001"
    with localcontext() as ctx:
        ctx.prec = 200
        want = Decimal(p) * Decimal(BIG) + Decimal("0.000000000000000000000000000001")
    assert Decimal(bar["buy_notional"]) == want


def test_f1_rolling_delta_and_cvd_stay_exact():
    bar = bars_for([rec("a", "B", "1", BIG)])
    assert bar["cvd_base"] == BIG
    roll = tr.rolling_delta([bar], 10, [10])
    assert roll["10"]["delta_base"] == BIG


def test_f1_heatmap_cell_sums_stay_exact():
    q = BIG + ".5"
    smp = {"receipt_ns": 5, "state": "LIVE", "limit": None,
           "bids": [(Decimal("100.1"), Decimal(q), "100.1", q), (Decimal("100.2"), Decimal(q), "100.2", q)],
           "asks": []}
    with localcontext() as ctx:
        ctx.prec = 5
        h = heatmap.build_heatmap([smp], tick="1", t0_ns=0, bucket_ns=10, buckets=1, price_lo="100",
                                  price_hi="102", as_of_ns=10)
    assert h["columns"][0]["bids"][0][1] == "246913578024691357802469135781.0"  # 2 x (BIG + .5), by hand


def test_f1_non_ascii_digits_are_refused():
    led = tr.TradeLedger(fixtures.FLOW)
    assert led.ingest(rec("a", "B", "1", "٣"), session_id="s", received_ns=2, arrival_seq=0) == "DECIMAL_TEXT_REFUSED"


# ----------------------------------------------------------------------------- F2

def straddle_session(lo, hi, as_of):
    ev, cfg = fixtures.synthetic_session()
    first = copy.deepcopy(ev[0])
    first["receipt"] = {"mono": [lo, hi], "utc": [lo, hi]}
    cfg.update(as_of_receipt_ns=as_of, anchor_ns=0, bar_ns=1, coverage=[(0, as_of)], windows_ns=[1],
               silence_budget_ns=10)
    cfg["heatmap"] = {**cfg["heatmap"], "t0_ns": 0, "bucket_ns": 1, "buckets": as_of}
    return [first], cfg


def test_f2_message_straddling_as_of_is_not_served():
    ev, cfg = straddle_session(4, 6, 5)
    doc = artifact.replay(ev, cfg)
    assert doc["book"]["state"] == ["UNRESOLVED", "MESSAGE_STRADDLES_AS_OF"]
    assert doc["book"]["bbo"]["status"] == "NOT_AVAILABLE" and doc["book"]["bbo"]["bid"] is None
    assert doc["book"]["freshness"] is None
    assert doc["inputs"]["events_straddling_as_of_not_read"] == 1 and doc["inputs"]["event_count"] == 0
    assert all(c["status"] != "LIVE" for c in doc["heatmap"]["columns"])


@pytest.mark.parametrize("lo,hi,live", [(3, 5, True), (4, 5, True), (5, 5, True), (4, 6, False), (5, 6, False)])
def test_f2_frontier(lo, hi, live):
    ev, cfg = straddle_session(lo, hi, 5)
    doc = artifact.replay(ev, cfg)
    assert (doc["book"]["state"][0] == "LIVE") is live


def test_f2_later_book_events_after_a_straddler_are_not_read_but_trades_are():
    ev, cfg = fixtures.synthetic_session()
    l2s = [e for e in ev if e["kind"] == "l2"]
    cfg["as_of_receipt_ns"] = l2s[1]["receipt"]["utc"][0] + 5  # inside the second l2 message
    doc = artifact.replay(ev, cfg)
    assert doc["inputs"]["events_straddling_as_of_not_read"] == 1
    assert doc["book"]["state"][0] == "UNRESOLVED"
    assert doc["trades"]["accepted"] > 0


def test_f2_heatmap_sample_is_dated_at_the_end_of_receipt():
    ev, cfg = straddle_session(3, 5, 6)
    doc = artifact.replay(ev, cfg)
    live = [c for c in doc["heatmap"]["columns"] if c["status"] == "LIVE"]
    assert live and live[0]["bucket"] == 5 and live[0]["sample_receipt_ns"] == "5"


# ----------------------------------------------------------------------------- F3

def fresh():
    ev, cfg = fixtures.synthetic_session()
    return artifact.replay(ev, cfg)


def mutate(path, value):
    doc = fresh()
    cur = doc
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = value
    return doc


MUTATIONS = {
    "book_extra_key": (("book", "unexpected_score"), "999"),
    "bbo_extra_key": (("book", "bbo", "score"), "1"),
    "bid_extra_key": (("book", "bbo", "bid", "x"), "1"),
    "freshness_extra_key": (("book", "freshness", "x"), "1"),
    "frontier_extra_key": (("book", "freshness", "frontier", "x"), "1"),
    "flow_extra": (("flow", "x"), "1"),
    "side_convention_extra": (("flow", "side_convention", "x"), "1"),
    "inputs_extra": (("inputs", "x"), 1),
    "trades_extra": (("trades", "x"), 1),
    "excluded_extra": (("trades", "excluded", "x"), 1),
    "bar_extra": (("bars", 0, "x"), "1"),
    "heatmap_extra": (("heatmap", "x"), "1"),
    "column_extra": (("heatmap", "columns", 0, "x"), "1"),
    "event_extra": (("level_events", "items", 0, "x"), "1"),
    "delta_nan": (("bars", 0, "delta_base"), "NaN"),
    "delta_inf": (("bars", 0, "delta_base_bounds"), ["Infinity", "Infinity"]),
    "delta_exponent": (("bars", 0, "buy_volume"), "1e3"),
    "volume_unicode_digit": (("bars", 0, "buy_volume"), "٣"),
    "ns_unicode_digit": (("bars", 0, "start_ns"), "٣"),
    "ns_leading_zero": (("bars", 0, "start_ns"), "01"),
    "ns_int": (("bars", 0, "start_ns"), 1),
    "bar_index": (("bars", 0, "index"), 1),
    "bar_geometry": (("bars", 1, "start_ns"), "1"),
    "count_bool": (("bars", 0, "trade_count"), True),
    "not_covered_delta_zero": (("bars", 3, "delta_base"), "0"),
    "not_covered_cvd_zero": (("bars", 3, "cvd_base"), "0"),
    "not_covered_bounds_zero": (("bars", 3, "cvd_base_bounds"), ["0", "0"]),
    "not_covered_count_zero": (("bars", 3, "trade_count"), 0),
    "exact_with_unknown": (("bars", 2, "delta_base"), "0"),
    "bounds_inconsistent": (("bars", 0, "delta_base_bounds"), ["0", "1"]),
    "session_break_with_delta": (("bars", 4, "delta_base"), "0"),
    "rolling_bad_key": (("rolling_delta", "7"), {"status": "NOT_AVAILABLE", "reason": "WINDOW_BEFORE_ANCHOR"}),
    "rolling_bad_reason": (("rolling_delta", "60000000000"), {"status": "NOT_AVAILABLE", "reason": "x"}),
    "bbo_score": (("book", "bbo", "mid"), "1000"),
    "bbo_price_nan": (("book", "bbo", "bid", "price"), "NaN"),
    "state_type": (("book", "state"), "LIVE"),
    "column_bucket": (("heatmap", "columns", 1, "bucket"), 0),
    "cell_unsorted": (("heatmap", "columns", 0, "bids"), [[4, "2"], [3, "1"]]),
    "cell_out_of_grid": (("heatmap", "columns", 0, "bids"), [[99, "1"]]),
    "cell_zero_quantity": (("heatmap", "columns", 0, "bids"), [[3, "0"]]),
    "rows_wrong": (("heatmap", "rows"), 5),
    "constant_wrong": (("heatmap", "unit"), "EXECUTED_VOLUME"),
    "event_cause_claimed": (("level_events", "items", 1, "cause"), "ICEBERG"),
    "event_side": (("level_events", "items", 0, "side"), "buy"),
    "assumptions_type": (("assumptions",), "A-LAYOUT"),
    "limits_item": (("limits",), [1]),
    "hash": (("inputs", "events_sha256"), "xyz"),
    "calc_version": (("calc_version",), "other"),
    "float_value": (("inputs", "event_count"), 1.5),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_f3_nested_contract_refuses(name):
    path, value = MUTATIONS[name]
    doc = mutate(path, value)
    with pytest.raises(ValueError):
        artifact.validate_artifact(doc)


def test_f3_golden_passes_and_is_unchanged_by_validation():
    doc = fresh()
    before = copy.deepcopy(doc)
    assert artifact.validate_artifact(doc) == before


def test_f3_every_ns_in_the_book_is_a_decimal_string():
    f = fresh()["book"]["freshness"]
    assert f["connection_silence_ns"] and all(isinstance(v, str) for v in f["connection_silence_ns"])


# ----------------------------------------------------------------------------- F4

def test_f4_book_cannot_be_relabelled_as_another_flow():
    ev, cfg = fixtures.synthetic_session()
    for changes in ({"venue": "OTHER_PROVIDER", "instrument": "ETH-USD", "base": "ETH"}, {"venue": "OTHER"},
                    {"instrument": "ETH-USD", "base": "ETH"}, {"base": "XBT"}, {"quote": "USDT"}):
        c = dict(cfg, trade_flow=replace(cfg["trade_flow"], **changes))
        with pytest.raises(ValueError, match="FLOW_BOOK_IDENTITY_MISMATCH"):
            artifact.replay(ev, c)
    with pytest.raises(ValueError, match="FLOW_BOOK_IDENTITY_MISMATCH"):
        artifact.replay(ev, dict(cfg, product="ETH-USD"))


def test_f4_contract_refuses_inconsistent_identity_in_a_document():
    for path, value in ((("flow", "venue"), "OTHER_PROVIDER"), (("book", "bbo", "product"), "ETH-USD"),
                        (("flow", "instrument"), "ETH-USD"), (("book", "freshness", "product"), "ETH-USD"),
                        (("book", "bbo", "quote"), "USDT")):
        with pytest.raises(ValueError):
            artifact.validate_artifact(mutate(path, value))


# ----------------------------------------------------------------------------- F5

def test_f5_ambiguous_or_malformed_conventions_are_refused():
    bad = [
        (("B", tr.BUY), ("B", tr.SELL)),
        (("B", tr.BUY), ("B", tr.BUY)),
        (("B", "MAYBE"),),
        (("B",),),
        ((1, tr.BUY),),
        (("", tr.BUY),),
        [("B", tr.BUY)],
    ]
    for mapping in bad:
        with pytest.raises(ValueError):
            tr.SideConvention(mapping, False, "SYNTHETIC")
    with pytest.raises(ValueError):
        tr.SideConvention((("B", tr.BUY),), "no", "SYNTHETIC")
    with pytest.raises(ValueError):
        tr.SideConvention((("B", tr.BUY),), False, "")


def test_f5_valid_convention_and_unknown_values():
    conv = tr.SideConvention((("B", tr.BUY), ("S", tr.SELL)), False, "SYNTHETIC")
    assert conv.aggressor("B") == tr.BUY and conv.aggressor("S") == tr.SELL
    assert conv.aggressor("?") == tr.UNKNOWN and conv.aggressor(None) == tr.UNKNOWN
