"""T10 REST cross-check: decoder and comparison (SYNTHETIC bodies)."""

import pytest

from observability.market_flow import kraken_trades as kt
from observability.market_flow import trades as tr

from ._support import MS, T0, report, steady

W0, W1 = T0 * MS, (T0 + 300_000) * MS


def rest_body(rows, last="1"):
    """rows: (id, ms, price, qty, side 'b'/'s')."""
    return ('{"error":[],"result":{"XBTUSDT":[%s],"last":"%s"}}' % (",".join(
        '["%s","%s",%d.%04d,"%s","l","",%d]' % (p, q, ms // 1000, (ms % 1000) * 10, s, tid)
        for tid, ms, p, q, s in rows), last)).encode()


def ws_trades(rows):
    led = tr.TradeLedger(kt.KRAKEN_BTC_USDT_FLOW)
    for i, (tid, ms, p, q, s) in enumerate(rows):
        rec = {"trade_id": str(tid), "instrument": "BTC/USDT", "quote": "USDT", "price": p, "size": q,
               "side": "buy" if s == "b" else "sell", "event_ns": ms * MS}
        assert led.ingest(rec, session_id="ws-1", received_ns=ms * MS + 1, arrival_seq=i) == "ACCEPTED"
    return led.trades


BASE = [(10 + i, T0 - 1_000 + i * 1_000, "62000.1", "0.5", "b" if i % 2 else "s") for i in range(305)]


def test_t10_decoder_is_strict():
    rows, last = kt.decode_rest_trades(rest_body(BASE[:2], last="1795128000000000000"))
    assert set(rows) == {"10", "11"} and last == "1795128000000000000"
    assert rows["11"] == {"price": "62000.1", "qty": "0.5", "side": "buy", "time_ns": T0 * MS,
                          "time_text": "%d.0000" % (T0 // 1000)}
    for body in (b'{"error":["EGeneral:Too many requests"],"result":{}}',
                 b'{"error":[],"result":{"XBTUSD":[],"last":"1"}}',
                 b'{"error":[],"result":{"XBTUSDT":[["1","1",1.0,"b","l",""]],"last":"1"}}',
                 b'{"error":[],"result":{"XBTUSDT":[["1","1",1.0,"x","l","",1]],"last":"1"}}',
                 b'{"error":[],"result":{"XBTUSDT":[],"last":"abc"}}'):
        with pytest.raises(ValueError):
            kt.decode_rest_trades(body)


def test_t10_identical_sets_match():
    rows, _ = kt.decode_rest_trades(rest_body(BASE))
    out = kt.compare_with_rest(ws_trades(BASE), rows, W0, W1)
    assert out["status"] == "MATCH" and out["matched"] == out["compared_ids"] == 300
    assert out["side_agreement"] == 300


def test_t10_missing_extra_and_divergent_rows_are_listed():
    ws = [r for r in BASE if r[0] != 50]                      # WS lost id 50
    rest = [r for r in BASE if r[0] != 60]                    # REST lacks id 60
    rest = [(t, ms, "1.0" if t == 70 else p, q, s) for t, ms, p, q, s in rest]  # REST differs on 70
    rows, _ = kt.decode_rest_trades(rest_body(rest))
    out = kt.compare_with_rest(ws_trades(ws), rows, W0, W1)
    assert out["status"] == "MISMATCH"
    assert (out["missing_in_ws"], out["missing_in_rest"], out["content_mismatch"]) == (["50"], ["60"], ["70"])


def test_t10_padded_decimals_are_equal_values():
    rest = [(t, ms, p + "000", q + "0", s) for t, ms, p, q, s in BASE]
    rows, _ = kt.decode_rest_trades(rest_body(rest))
    assert kt.compare_with_rest(ws_trades(BASE), rows, W0, W1)["status"] == "MATCH"


def test_t10_a_rest_range_that_does_not_enclose_the_window_concludes_nothing():
    rows, _ = kt.decode_rest_trades(rest_body(BASE[:150]))
    out = kt.compare_with_rest(ws_trades(BASE), rows, W0, W1)
    assert out["status"] == "UNKNOWN" and out["reason"] == "REST_RANGE_DOES_NOT_ENCLOSE_WINDOW"
    assert kt.compare_with_rest(ws_trades(BASE), {}, W0, W1)["status"] == "NOT_AVAILABLE"


def _with_rest(rows, body):
    return rows + [(T0 + 700_000, "rest", body, {"endpoint": "trades", "status": 200})]


def test_t10_h2_and_h7_are_decided_by_rest_inside_the_replay():
    ws_rows = steady(700, skip={1100})
    full = [(1000 + i, T0 - 60_000 + i * 1000, "62000.5", "0.0012", "b" if i % 3 else "s") for i in range(700)]
    # REST holds id 1100: the WS lost it (H2 confirmed), the exit window still matches.
    r = report(_with_rest(ws_rows, rest_body(full)))
    assert r["hypotheses"]["H2_trade_id_plus_one"]["status"] == "CONFIRMED_ON_CAPTURE"
    assert r["rest_cross_check"]["rows_fetched"] == 700
    # REST lacks 1100 too: ids are not dense, H2 refuted.
    r = report(_with_rest(ws_rows, rest_body([x for x in full if x[0] != 1100])))
    assert r["hypotheses"]["H2_trade_id_plus_one"]["status"] == "REFUTED"
    # Exit window compared: a quantity differs -> H7 refuted.
    bad = [(t, ms, p, "9" if t == 1200 else q, s) for t, ms, p, q, s in full]
    r = report(_with_rest(steady(700), rest_body(bad)))
    assert r["exit_window"] is not None
    assert r["hypotheses"]["H7_ws_row_equals_rest_row"]["status"] == "REFUTED"
    r = report(_with_rest(steady(700), rest_body(full)))
    assert r["hypotheses"]["H7_ws_row_equals_rest_row"]["status"] == "CONFIRMED_ON_CAPTURE"
    assert r["hypotheses"]["H1_side_is_taker"]["status"] == "DOCUMENTARY"


def test_t10_unreadable_rest_body_is_an_error_not_an_empty_set():
    r = report(_with_rest(steady(10), b"<html>"))
    assert r["rest_cross_check"]["errors"] and r["rest_cross_check"]["rows_fetched"] == 0
    r = report(steady(10) + [(T0 + 1, "rest", b"", {"endpoint": "trades", "status": 503})])
    assert r["rest_cross_check"]["errors"] == {"HTTP_OR_TRANSPORT": 1}

