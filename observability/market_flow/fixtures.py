"""Invented session for tests and the isolated UI mock-up. Not provider output."""

from . import trades as tr

S = 1_000_000_000
ANCHOR = 1_000 * S
BAR = 60 * S
NO_ATTESTATION = tr.SideConvention(
    mapping=(("B", tr.BUY), ("S", tr.SELL)), attested=False, evidence_ref="SYNTHETIC-CONVENTION-NOT-ATTESTED"
)
FLOW = tr.TradeFlow("coinbase_advanced", "BTC-USD", "BTC", "USD", "SPOT", "SESSION", NO_ATTESTATION)


def _rcv(t):
    return {"mono": [t, t + 10], "utc": [t, t + 10]}


def _l2(seq, t, events, ts_ns=None):
    msg = {"channel": "l2_data", "sequence_num": seq, "events": events}
    if ts_ns is not None:
        msg["timestamp"] = ts_ns
    return {"kind": "l2", "message": msg, "receipt": _rcv(t)}


def _snap(levels):
    return [{"type": "snapshot", "product_id": "BTC-USD", "updates": [
        {"side": s, "price_level": p, "new_quantity": q} for s, p, q in levels]}]


def _upd(levels):
    return [{"type": "update", "product_id": "BTC-USD", "updates": [
        {"side": s, "price_level": p, "new_quantity": q} for s, p, q in levels]}]


def _trade(i, t_recv, t_event, tid, side, price, size, session="s1", quote="USD"):
    rec = {"trade_id": tid, "instrument": "BTC-USD", "quote": quote, "price": price, "size": size, "side": side,
           "event_ns": t_event}
    if tid is None:
        del rec["trade_id"]
    return {"kind": "trade", "record": rec, "session_id": session, "received_ns": t_recv, "arrival_seq": i}


def synthetic_session():
    a = ANCHOR
    ev = [
        _l2(0, a + 1 * S, _snap([("bid", "1000", "2"), ("bid", "999.5", "1"), ("offer", "1001", "3"), ("offer", "1002", "4")])),
        _trade(1, a + 5 * S, a + 4 * S, "t1", "B", "1001", "1"),
        _trade(2, a + 6 * S, a + 5 * S, "t2", "S", "1000", "0.4"),
        _trade(3, a + 7 * S, a + 5 * S, "t2", "S", "1000", "0.4"),  # exact duplicate
        _trade(4, a + 8 * S, a + 7 * S, "t3", "B", "1001.5", "0.1"),
        _trade(5, a + 9 * S, a + 8 * S, None, "B", "1001", "9"),  # no id: refused
        _trade(6, a + 10 * S, a + 9 * S, "tq", "B", "1001", "9", quote="USDT"),  # other quote: refused
        _l2(1, a + 20 * S, _upd([("bid", "1000.5", "5")])),
        _l2(2, a + 30 * S, _upd([("offer", "1001", "0")])),  # level disappears, cause unknown
        {"kind": "sample", "receipt": _rcv(a + 90 * S)},
        _trade(7, a + 130 * S, a + 125 * S, "t4", "S", "1000.5", "0.25"),
        _trade(8, a + 131 * S, a + 126 * S, "t5", "?", "1000.5", "0.5"),  # unknown aggressor side
        _trade(9, a + 135 * S, a + 400 * S, "t9", "B", "1001", "7"),  # event time in the future: excluded
        _l2(5, a + 150 * S, _upd([("bid", "999", "1")])),  # sequence gap: every book invalid
        _l2(6, a + 170 * S, _snap([("bid", "1000", "2"), ("offer", "1001.5", "3")])),  # resync by snapshot
        {"kind": "sample", "receipt": _rcv(a + 210 * S)},
        _trade(10, a + 250 * S, a + 245 * S, "t6", "B", "1001", "2"),
        _trade(11, a + 262 * S, a + 250 * S, "t1", "B", "1001", "1", session="s2"),  # new session reuses an id
        _l2(7, a + 290 * S, _upd([("bid", "1000.5", "1")])),
        _trade(12, a + 400 * S, a + 395 * S, "t8", "B", "1001", "100"),  # after as_of: never read
    ]
    cfg = {
        "connection_id": "synthetic-c1", "product": "BTC-USD", "trade_flow": FLOW,
        "as_of_receipt_ns": a + 300 * S, "anchor_ns": a, "bar_ns": BAR,
        "coverage": [(a, a + 3 * BAR), (a + 4 * BAR, a + 5 * BAR)],  # bar 3 has no trade-feed coverage
        "windows_ns": [BAR, 2 * BAR, 5 * BAR], "silence_budget_ns": 120 * S,
        "heatmap": {"tick": "0.5", "t0_ns": a, "bucket_ns": BAR, "buckets": 5,
                    "price_lo": "998", "price_hi": "1004"},
        "depth_levels_limit": None,
    }
    return ev, cfg
