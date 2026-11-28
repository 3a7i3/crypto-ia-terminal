"""T1 decoder, T2 native time, T3 side convention (SYNTHETIC frames)."""

from observability.market_flow import kraken_trades as kt
from observability.market_flow import trades as tr
from observability.radar_composite import bbo_book

from ._support import ACK, HEARTBEAT, T0, frame, item, report, steady


def _items(payload):
    c = kt.classify_frame(payload)
    assert c["kind"] == "trade"
    return [kt.decode_item(i) for i in c["items"]]


# ---------------------------------------------------------------- T1 decoder

def test_t01_snapshot_and_update_frames_become_project_records_with_literal_texts():
    for typ in ("snapshot", "update"):
        c = kt.classify_frame(frame([item(7, T0, price="62000.10", qty="0.00120000")], typ))
        assert (c["kind"], c["type"]) == ("trade", typ)
        rec, why = kt.decode_item(c["items"][0])
        assert why is None
        # The literal text is kept exactly (trailing zeros included), never re-rendered.
        assert rec == {"trade_id": "7", "instrument": "BTC/USDT", "quote": "USDT", "price": "62000.10",
                       "size": "0.00120000", "side": "buy", "event_ns": T0 * 1_000_000}


def test_t01_control_frames_are_classified_not_decoded():
    assert kt.classify_frame(HEARTBEAT) == {"kind": "heartbeat"}
    ack = kt.classify_frame(ACK)
    assert ack == {"kind": "subscribe_ack", "success": True, "channel": "trade", "symbol": "BTC/USDT",
                   "snapshot": True}
    assert kt.classify_frame(b'{"method":"pong","req_id":1}') == {"kind": "pong"}
    assert kt.classify_frame(b'{"channel":"status","type":"update","data":[]}') == {"kind": "status"}
    assert kt.classify_frame(b"not json")["kind"] == "malformed"
    assert kt.classify_frame(b'{"a":1,"a":2}')["kind"] == "malformed"  # duplicate key
    assert kt.classify_frame(b'{"channel":"trade","type":"update","data":[],"x":1}')["reason"] == \
        "TRADE_ENVELOPE_REFUSED"
    assert kt.classify_frame(b'{"channel":"trade","type":"delta","data":[]}')["kind"] == "malformed"
    assert kt.classify_frame(b'{"x":NaN}')["kind"] == "malformed"


def test_t01_items_that_cannot_be_trusted_are_refused_with_a_code():
    bad = {
        "TRADE_ID_INVALID": item('"7"', T0),        # id as text
        "NUMBER_REQUIRED": item(8, T0, price='"62000"'),
        "ITEM_KEYS_REFUSED": item(9, T0)[:-1] + ',"extra":1}',
        "SYMBOL_INVALID": item(10, T0, symbol="BTCUSDT"),
    }
    for code, it in bad.items():
        assert _items(frame([it])) == [(None, code)], code
    assert _items(frame([item("-1", T0)])) == [(None, "TRADE_ID_INVALID")]
    assert _items(frame([item("1.5", T0)])) == [(None, "TRADE_ID_INVALID")]
    assert kt.decode_item([1, 2]) == (None, "ITEM_NOT_OBJECT")


def test_t01_exponent_and_foreign_symbol_are_counted_refusals_not_conversions():
    r = report(steady(5, mutate=lambda tid, at, it: (
        item(tid, at, qty="1e-05") if tid == 1001 else
        item(tid, at, symbol="ETH/USDT") if tid == 1002 else it)))
    assert r["ledger"]["refused"] == {"DECIMAL_TEXT_REFUSED": 1, "INSTRUMENT_MISMATCH": 1}
    assert r["ledger"]["accepted"] == 3
    assert r["hypotheses"]["H4_plain_decimal_numbers"]["status"] == "REFUTED"
    assert r["hypotheses"]["H6_symbol_echo"]["status"] == "REFUTED"
    # The refused ids leave holes: they are coverage gaps, never filled.
    assert r["trade_coverage"]["missing_ids_total"] == 2


def test_t01_literal_reader_matches_the_bbo_book_pattern_on_a_corpus():
    corpus = [ACK, HEARTBEAT, frame([item(1, T0, price="62000.10", qty="0.00000001")]),
              b'{"n":0,"m":-0.0,"big":123456789012345678901234567890}', b'[1.10, 2, "x", true, null]']
    for raw in corpus:
        mine, ref = kt.literal_json(raw), bbo_book.kraken_json(raw)
        assert mine == ref
    assert type(kt.literal_json(b"[0.10]")[0]) is kt.Literal


# ---------------------------------------------------------------- T2 native time

def test_t02_rfc3339_microseconds_become_exact_nanoseconds():
    (rec, _), = _items(frame([item(1, T0, us=123)]))
    assert rec["event_ns"] == T0 * 1_000_000 + 123_000
    (rec, _), = _items(frame([item(2, T0, ts="2026-11-28T01:02:03.123456789Z")]))
    assert rec["event_ns"] % 1_000_000_000 == 123_456_789


def test_t02_invalid_native_time_is_null_and_counted_never_replaced_by_receipt():
    for ts in ("2026-11-28 01:02:03Z", "2026-02-30T00:00:00Z", "x"):
        (rec, why), = _items(frame([item(3, T0, ts=ts)]))
        assert why is None and rec["event_ns"] is None
    r = report(steady(4, mutate=lambda tid, at, it: item(tid, at, ts="bad") if tid == 1001 else it))
    assert r["ledger"]["excluded"]["no_event_time"] == 1
    assert r["ledger"]["counted_in_bars"] == 3


# ---------------------------------------------------------------- T3 side convention

def test_t03_taker_convention_maps_buy_sell_and_nothing_else():
    conv = kt.KRAKEN_TAKER_CONVENTION
    assert conv.aggressor("buy") == tr.BUY and conv.aggressor("sell") == tr.SELL
    for raw in ("b", "s", "BUY", "", None, 1):
        assert conv.aggressor(raw) == tr.UNKNOWN
    assert conv.attested is True and kt.EVIDENCE_EXCERPT_SHA256 in conv.evidence_ref
    assert kt.KRAKEN_BTC_USDT_FLOW.id_domain == "INSTRUMENT"


def test_t03_unknown_side_is_unknown_with_unknown_basis_and_bounded_delta():
    r = report(steady(700, mutate=lambda tid, at, it: item(tid, at, side="maker") if tid == 1100 else it))
    w = r["windows"][1]
    assert w["status"] == "COVERED"
    assert w["side_coverage"]["known_count"] == w["side_coverage"]["total_count"] - 1
    assert w["delta_300s"]["status"] == "PARTIAL_UNKNOWN_SIDE" and w["delta_300s"]["delta_base"] is None
    unknown = [n for n in r["normalized_trades_exit_window"] if n["trade_id"] == "1100"]
    assert [(u["aggressor_side"], u["side_basis"]) for u in unknown] == [("UNKNOWN", "UNKNOWN")]
    for n in r["normalized_trades_exit_window"]:
        assert (n["aggressor_side"] == "UNKNOWN") == (n["side_basis"] == "UNKNOWN")
    assert r["flow"]["side_convention"]["attested"] is True
