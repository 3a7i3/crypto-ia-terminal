"""Liquidity heatmap grid and level-lifecycle events from book samples.

A grid cell is the *displayed* quantity at a price tick in a time bucket (the
last LIVE sample of the bucket). It is not executed volume, not an order, and
a vanished level has no proven cause. Bids and asks stay separate and every
(venue, instrument) is its own layer: nothing is summed across venues.
"""

from decimal import Decimal

from .trades import _text


def book_sample(conn, product, receipt_ns, *, depth_levels_limit=None):
    """Immutable sample of one product: state, full exact levels, declared depth limit."""
    if type(receipt_ns) is not int or receipt_ns < 0:
        raise ValueError("INTEGER_NS_REQUIRED")
    lv = conn.levels(product)
    state = conn.state(product)[0]
    return {
        "receipt_ns": receipt_ns, "state": state, "limit": depth_levels_limit,
        "bids": None if lv is None else [(Decimal(p), Decimal(q), p, q) for p, q in lv[0]],
        "asks": None if lv is None else [(Decimal(p), Decimal(q), p, q) for p, q in lv[1]],
    }


def _floor(sample):
    """Lowest bid / highest ask the sample can vouch for when its depth is truncated."""
    lim = sample["limit"]
    bf = af = None
    if lim is not None:
        if len(sample["bids"]) >= lim:
            bf = sample["bids"][-1][0]
        if len(sample["asks"]) >= lim:
            af = sample["asks"][-1][0]
    return bf, af


def build_heatmap(samples, *, tick, t0_ns, bucket_ns, buckets, price_lo, price_hi, as_of_ns):
    tick, price_lo, price_hi = Decimal(tick), Decimal(price_lo), Decimal(price_hi)
    if tick <= 0 or price_hi <= price_lo or type(buckets) is not int or buckets < 1:
        raise ValueError("GRID_GEOMETRY_INVALID")
    if type(bucket_ns) is not int or bucket_ns <= 0 or type(t0_ns) is not int:
        raise ValueError("GRID_GEOMETRY_INVALID")
    rows = int(((price_hi - price_lo) / tick).to_integral_value(rounding="ROUND_CEILING"))
    visible = [s for s in samples if s["receipt_ns"] <= as_of_ns]  # no future samples
    cols = []
    for i in range(buckets):
        lo, hi = t0_ns + i * bucket_ns, t0_ns + (i + 1) * bucket_ns
        if hi > as_of_ns:
            cols.append({"bucket": i, "status": "NOT_YET_COMPLETE", "sample_receipt_ns": None})
            continue
        inb = [s for s in visible if lo <= s["receipt_ns"] < hi]
        if not inb:
            cols.append({"bucket": i, "status": "NO_SAMPLE", "sample_receipt_ns": None})
            continue
        s = max(inb, key=lambda x: x["receipt_ns"])
        if s["state"] != "LIVE":
            cols.append({"bucket": i, "status": "BOOK_" + s["state"], "sample_receipt_ns": str(s["receipt_ns"])})
            continue
        bf, af = _floor(s)
        cells = {"bids": {}, "asks": {}}
        for side, key in (("bids", "bids"), ("asks", "asks")):
            for price, qty, _, _ in s[key]:
                if not price_lo <= price < price_hi:
                    continue
                j = int((price - price_lo) // tick)
                cells[side][j] = cells[side].get(j, Decimal(0)) + qty
        cols.append({
            "bucket": i, "status": "LIVE", "sample_receipt_ns": str(s["receipt_ns"]),
            "bid_cover_floor": None if bf is None else _text(bf),
            "ask_cover_ceiling": None if af is None else _text(af),
            "bids": [[j, _text(q)] for j, q in sorted(cells["bids"].items())],
            "asks": [[j, _text(q)] for j, q in sorted(cells["asks"].items())],
        })
    return {
        "unit": "DISPLAYED_BASE_QUANTITY", "aggregation": "LAST_LIVE_SAMPLE_IN_BUCKET",
        "tick": _text(tick), "price_lo": _text(price_lo), "price_hi": _text(price_hi), "rows": rows,
        "t0_ns": str(t0_ns), "bucket_ns": str(bucket_ns), "columns": cols,
        "zero_semantics": "ABSENT_CELL_IN_LIVE_COLUMN_WITHIN_COVER_IS_OBSERVED_ZERO",
    }


def level_events(samples, *, as_of_ns, trades=(), max_events=1000):
    """Appear/disappear events between consecutive LIVE samples; cause is never claimed."""
    seq = [s for s in samples if s["receipt_ns"] <= as_of_ns]
    events, tracked = [], {}
    prev = None
    for s in seq:
        if s["state"] != "LIVE":
            prev = None  # a gap: lifecycle continuity is not assumed across it
            tracked = {}
            continue
        now = {("bid", p): (p, q, pt) for p, q, pt, _ in s["bids"]}
        now.update({("ask", p): (p, q, pt) for p, q, pt, _ in s["asks"]})
        bf, af = _floor(s)
        if prev is not None:
            ps, pnow = prev
            for key, (p, q, pt) in pnow.items():
                if key in now:
                    continue
                side = key[0]
                if (side == "bid" and bf is not None and p < bf) or (side == "ask" and af is not None and p > af):
                    status, kind = "LEFT_COVERED_DEPTH", "NOT_A_DISAPPEARANCE"
                else:
                    status, kind = "DISAPPEARED", "CAUSE_UNDETERMINED"
                first = tracked.pop(key, None)
                if first is None:
                    first = {"first_seen_ns": ps["receipt_ns"], "before_ns": None}
                n_tr = sum(1 for t in trades if t.price_text == pt and ps["receipt_ns"] < t.received_ns <= s["receipt_ns"])
                events.append({
                    "kind": status, "cause": kind, "side": key[0], "price": pt, "last_qty": _text(q),
                    "interval_ns": [str(ps["receipt_ns"]), str(s["receipt_ns"])],
                    "persistence_ns": {
                        "min": str(ps["receipt_ns"] - first["first_seen_ns"]),
                        "max": None if first["before_ns"] is None else str(s["receipt_ns"] - first["before_ns"]),
                    },
                    "left_censored": first["before_ns"] is None,
                    "trades_at_price_in_interval": n_tr,
                })
            for key, (p, q, pt) in now.items():
                if key not in pnow:
                    tracked[key] = {"first_seen_ns": s["receipt_ns"], "before_ns": ps["receipt_ns"]}
                    events.append({"kind": "APPEARED", "cause": "CAUSE_UNDETERMINED", "side": key[0],
                                   "price": pt, "qty": _text(q),
                                   "interval_ns": [str(ps["receipt_ns"]), str(s["receipt_ns"])]})
        else:
            for key in now:
                tracked[key] = {"first_seen_ns": s["receipt_ns"], "before_ns": None}
        prev = (s, now)
        if len(events) > max_events:
            return events[:max_events], True
    return events, False
