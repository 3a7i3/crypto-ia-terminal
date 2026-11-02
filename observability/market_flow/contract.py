"""Closed, nested MarketFlowArtifact 1.0.0 contract (form and internal consistency).

Shared by the builder (``artifact.replay``) and the reader (through
``artifact.validate_artifact``). Every structure is closed: unknown keys,
missing keys, wrong types, non-ASCII digits, NaN/Infinity texts and
inconsistent null/status/coverage combinations are refused.

Checking form and consistency is NOT certifying the data: a document that
passes says nothing about whether the trades or the book are true.
"""

from decimal import Decimal
import re

from .exact import exact
from . import l2

_ASCII = re.ASCII
_NS = re.compile(r"(0|[1-9][0-9]{0,29})", _ASCII)  # unsigned integer nanoseconds
_SNS = re.compile(r"-?(0|[1-9][0-9]{0,29})", _ASCII)  # signed (an age or a persistence bound)
_DEC = re.compile(r"[0-9]{1,125}(\.[0-9]{1,125})?", _ASCII)  # unsigned decimal text
_SDEC = re.compile(r"-?[0-9]{1,125}(\.[0-9]{1,125})?", _ASCII)  # signed: sums, products
_CODE = re.compile(r"[A-Z][A-Z0-9_\-]{0,63}", _ASCII)
_HEX = re.compile(r"[0-9a-f]{64}", _ASCII)

MAX_BARS = 100_000
MAX_COLUMNS = 10_000
MAX_ROWS = 100_000
MAX_ITEMS = 1_000
MAX_LIST = 256
MAX_TEXT = 512

BAR_STATUSES = ("OBSERVED", "OBSERVED_ZERO", "NOT_COVERED", "SESSION_BREAK_UNRESOLVED")


def bad(path, why="CONTRACT_VIOLATION"):
    raise ValueError("%s:%s" % (why, path))


def obj(x, keys, path):
    if not isinstance(x, dict) or set(x) != set(keys):
        bad(path, "CLOSED_KEYS_REQUIRED")
    return x


def is_int(x, path, lo=0, hi=2**53 - 1):
    if type(x) is not int or not lo <= x <= hi:
        bad(path, "INTEGER_REQUIRED")
    return x


def boolean(x, path):
    if type(x) is not bool:
        bad(path, "BOOLEAN_REQUIRED")
    return x


def text(x, path, *, max_len=MAX_TEXT):
    if not isinstance(x, str) or not x or len(x) > max_len or not x.isprintable():
        bad(path, "TEXT_REQUIRED")
    return x


def code(x, path):
    if not isinstance(x, str) or not _CODE.fullmatch(x):
        bad(path, "CODE_REQUIRED")
    return x


def one_of(x, allowed, path):
    if not isinstance(x, str) or x not in allowed:
        bad(path, "ENUM_REFUSED")
    return x


def ns(x, path, *, signed=False):
    if not isinstance(x, str) or not (_SNS if signed else _NS).fullmatch(x):
        bad(path, "NS_MUST_BE_DECIMAL_STRING")
    return int(x)


def dec(x, path, *, signed=False, positive=False):
    if not isinstance(x, str) or not (_SDEC if signed else _DEC).fullmatch(x):
        bad(path, "DECIMAL_TEXT_REQUIRED")
    d = Decimal(x)
    if positive and d <= 0:
        bad(path, "POSITIVE_DECIMAL_REQUIRED")
    return d


def opt(x, check, path):
    return None if x is None else check(x, path)


def must_be_none(x, path):
    if x is not None:
        bad(path, "NULL_REQUIRED")


def str_list(x, path):
    if not isinstance(x, list) or len(x) > MAX_LIST:
        bad(path, "LIST_REQUIRED")
    for i, v in enumerate(x):
        text(v, "%s[%d]" % (path, i))
    return x


def span(x, path, *, signed=False):
    if not isinstance(x, list) or len(x) != 2:
        bad(path, "PAIR_REQUIRED")
    lo, hi = ns(x[0], path + "[0]", signed=signed), ns(x[1], path + "[1]", signed=signed)
    if lo > hi:
        bad(path, "INTERVAL_ORDER")
    return lo, hi


def dec_bounds(x, path):
    if not isinstance(x, list) or len(x) != 2:
        bad(path, "PAIR_REQUIRED")
    lo, hi = dec(x[0], path + "[0]", signed=True), dec(x[1], path + "[1]", signed=True)
    if lo > hi:
        bad(path, "INTERVAL_ORDER")
    return lo, hi


# --------------------------------------------------------------------------- flow

FLOW_KEYS = ("venue", "instrument", "base", "quote", "market_kind", "id_domain", "side_convention")


def check_flow(f):
    obj(f, FLOW_KEYS, "flow")
    for k in ("venue", "instrument", "base", "quote"):
        text(f[k], "flow." + k, max_len=64)
    one_of(f["market_kind"], ("SPOT",), "flow.market_kind")
    one_of(f["id_domain"], ("SESSION", "INSTRUMENT"), "flow.id_domain")
    sc = obj(f["side_convention"], ("attested", "evidence_ref"), "flow.side_convention")
    boolean(sc["attested"], "flow.side_convention.attested")
    text(sc["evidence_ref"], "flow.side_convention.evidence_ref")
    # The book layer is the Coinbase Advanced L2 candidate: another venue/product
    # label cannot be attached to it.
    if f["venue"] != l2.COINBASE_L2_FLOW.venue:
        bad("flow.venue", "FLOW_BOOK_IDENTITY_MISMATCH")
    if f["instrument"] not in l2.INSTRUMENTS or (f["base"], f["quote"]) != l2.INSTRUMENTS[f["instrument"]]:
        bad("flow.instrument", "FLOW_BOOK_IDENTITY_MISMATCH")


# --------------------------------------------------------------------------- inputs / trades

def check_inputs(x):
    obj(x, ("events_sha256", "event_count", "events_after_as_of_not_read",
            "events_straddling_as_of_not_read", "l2_events_not_read_after_straddle"), "inputs")
    if not isinstance(x["events_sha256"], str) or not _HEX.fullmatch(x["events_sha256"]):
        bad("inputs.events_sha256", "SHA256_REQUIRED")
    for k in ("event_count", "events_after_as_of_not_read", "events_straddling_as_of_not_read",
              "l2_events_not_read_after_straddle"):
        is_int(x[k], "inputs." + k)


def check_trades(x):
    obj(x, ("accepted", "duplicates", "conflicts", "refused", "sessions", "excluded"), "trades")
    is_int(x["accepted"], "trades.accepted")
    is_int(x["duplicates"], "trades.duplicates")
    if not isinstance(x["conflicts"], list) or len(x["conflicts"]) > MAX_ITEMS * 10:
        bad("trades.conflicts", "LIST_REQUIRED")
    for i, c in enumerate(x["conflicts"]):
        p = "trades.conflicts[%d]" % i
        obj(c, ("trade_id", "session_id"), p)
        text(c["trade_id"], p + ".trade_id")
        text(c["session_id"], p + ".session_id")
    if not isinstance(x["refused"], dict) or len(x["refused"]) > MAX_LIST:
        bad("trades.refused", "OBJECT_REQUIRED")
    for k, v in x["refused"].items():
        code(k, "trades.refused.key")
        is_int(v, "trades.refused." + str(k), lo=1)
    str_list(x["sessions"], "trades.sessions")
    ex = obj(x["excluded"], ("no_event_time", "future_event_time", "outside_range"), "trades.excluded")
    for k, v in ex.items():
        is_int(v, "trades.excluded." + k)


# --------------------------------------------------------------------------- bars / rolling

_BAR_OBSERVED_KEYS = (
    "index", "start_ns", "end_ns", "status", "trade_count", "quote",
    "buy_volume", "sell_volume", "unknown_volume", "buy_notional", "sell_notional", "unknown_notional",
    "open", "close", "high", "low",
    "delta_status", "delta_base", "delta_base_bounds", "segment", "cvd_base", "cvd_base_bounds",
)
_BAR_NOT_COVERED_KEYS = (
    "index", "start_ns", "end_ns", "status", "trade_count",
    "delta_status", "delta_base", "delta_base_bounds", "segment", "cvd_base", "cvd_base_bounds",
)


@exact
def _check_bar(b, i, anchor, bar_ns, quote):
    p = "bars[%d]" % i
    if not isinstance(b, dict):
        bad(p, "OBJECT_REQUIRED")
    status = one_of(b.get("status"), BAR_STATUSES, p + ".status")
    obj(b, _BAR_NOT_COVERED_KEYS if status == "NOT_COVERED" else _BAR_OBSERVED_KEYS, p)
    if is_int(b["index"], p + ".index") != i:
        bad(p + ".index", "BAR_INDEX_ORDER")
    lo, hi = ns(b["start_ns"], p + ".start_ns"), ns(b["end_ns"], p + ".end_ns")
    if lo != anchor + i * bar_ns or hi != lo + bar_ns:
        bad(p, "BAR_GEOMETRY")
    if status == "NOT_COVERED":
        for k in ("trade_count", "delta_base", "delta_base_bounds", "segment", "cvd_base", "cvd_base_bounds"):
            must_be_none(b[k], "%s.%s" % (p, k))  # UNKNOWN is never 0
        if b["delta_status"] != "NOT_COVERED":
            bad(p + ".delta_status", "STATUS_INCONSISTENT")
        return None
    count = is_int(b["trade_count"], p + ".trade_count")
    if b["quote"] != quote:
        bad(p + ".quote", "QUOTE_MISMATCH")  # USD is not USDT is not USDC
    vols = {k: dec(b[k], "%s.%s" % (p, k)) for k in ("buy_volume", "sell_volume", "unknown_volume")}
    for k in ("buy_notional", "sell_notional", "unknown_notional"):
        dec(b[k], "%s.%s" % (p, k))
    if (count == 0) != (status == "OBSERVED_ZERO") and status != "SESSION_BREAK_UNRESOLVED":
        bad(p + ".trade_count", "STATUS_INCONSISTENT")
    prices = [opt(b[k], dec, "%s.%s" % (p, k)) for k in ("open", "close", "high", "low")]
    if (count == 0) != all(v is None for v in prices) or (count > 0 and any(v is None for v in prices)):
        bad(p, "PRICES_INCONSISTENT")
    if count == 0 and any(v != 0 for v in vols.values()):
        bad(p, "ZERO_BAR_WITH_VOLUME")
    if status == "SESSION_BREAK_UNRESOLVED":
        if b["delta_status"] != status:
            bad(p + ".delta_status", "STATUS_INCONSISTENT")
        for k in ("delta_base", "delta_base_bounds", "segment", "cvd_base", "cvd_base_bounds"):
            must_be_none(b[k], "%s.%s" % (p, k))
        return None
    ds = one_of(b["delta_status"], ("EXACT", "PARTIAL_UNKNOWN_SIDE"), p + ".delta_status")
    blo, bhi = dec_bounds(b["delta_base_bounds"], p + ".delta_base_bounds")
    d = vols["buy_volume"] - vols["sell_volume"]
    u = vols["unknown_volume"]
    if (blo, bhi) != (d - u, d + u):
        bad(p + ".delta_base_bounds", "BOUNDS_INCONSISTENT")
    if ds == "EXACT":
        if u != 0 or b["delta_base"] is None or dec(b["delta_base"], p + ".delta_base", signed=True) != d:
            bad(p + ".delta_base", "STATUS_INCONSISTENT")
    else:
        if u == 0 or b["delta_base"] is not None:
            bad(p + ".delta_base", "STATUS_INCONSISTENT")
    is_int(b["segment"], p + ".segment")
    clo, chi = dec_bounds(b["cvd_base_bounds"], p + ".cvd_base_bounds")
    if b["cvd_base"] is None:
        if clo == chi:
            bad(p + ".cvd_base", "STATUS_INCONSISTENT")
    elif not (dec(b["cvd_base"], p + ".cvd_base", signed=True) == clo == chi):
        bad(p + ".cvd_base", "STATUS_INCONSISTENT")
    return b["segment"]


def check_bars(bars, anchor, bar_ns, as_of, quote):
    if not isinstance(bars, list) or len(bars) > MAX_BARS:
        bad("bars", "LIST_REQUIRED")
    if bars and anchor + len(bars) * bar_ns > as_of:
        bad("bars", "BAR_AFTER_AS_OF")
    last_seg = -1
    for i, b in enumerate(bars):
        seg = _check_bar(b, i, anchor, bar_ns, quote)
        if seg is not None:
            if seg < last_seg:
                bad("bars[%d].segment" % i, "SEGMENT_ORDER")
            last_seg = seg


@exact
def check_rolling(r, bar_ns):
    if not isinstance(r, dict) or len(r) > MAX_LIST:
        bad("rolling_delta", "OBJECT_REQUIRED")
    for key, v in r.items():
        p = "rolling_delta." + str(key)
        w = ns(key, p + ".key")
        if w <= 0 or w % bar_ns:
            bad(p, "WINDOW_MUST_BE_BAR_MULTIPLE")
        if not isinstance(v, dict):
            bad(p, "OBJECT_REQUIRED")
        if v.get("status") == "NOT_AVAILABLE":
            obj(v, ("status", "reason"), p)
            one_of(v["reason"], ("WINDOW_BEFORE_ANCHOR", "COVERAGE_INCOMPLETE_OR_UNRESOLVED"), p + ".reason")
        else:
            obj(v, ("status", "delta_base", "delta_base_bounds"), p)
            st = one_of(v["status"], ("EXACT", "PARTIAL_UNKNOWN_SIDE"), p + ".status")
            lo, hi = dec_bounds(v["delta_base_bounds"], p + ".delta_base_bounds")
            if st == "EXACT":
                if lo != hi or v["delta_base"] is None or dec(v["delta_base"], p + ".delta_base", signed=True) != lo:
                    bad(p, "STATUS_INCONSISTENT")
            elif lo == hi or v["delta_base"] is not None:
                bad(p, "STATUS_INCONSISTENT")


# --------------------------------------------------------------------------- book

_BBO_KEYS = ("connection_id", "product", "base", "quote", "market_kind", "status", "reason", "bid", "ask",
             "mid", "spread", "economic_metrics", "qualification", "unattested_assumptions")
_LEVEL_KEYS = ("price", "size", "level_event_time_ns", "level_event_time_state", "level_last_change_seq")
_FRESH_KEYS = ("product", "book_state", "reason", "connection_silence_ns", "connection_silence_status",
               "connection_last_channel", "frontier", "state_age_ns", "state_age_status", "unresolved",
               "freshness", "unattested_assumptions")


# Every refusal code the L2 decoder/applier can emit (a test keeps this list equal to l2.py's).
L2_REFUSALS = (
    "BOUNDED_BYTES_REQUIRED", "CHANNEL_MISSING", "DECIMAL_TEXT_REFUSED", "DUPLICATE_NATIVE_FIELD",
    "ENVELOPE_NOT_OBJECT", "EVENTS_NOT_LIST", "EVENT_NOT_OBJECT", "EVENT_TYPE_UNKNOWN", "INVALID_JSON",
    "JSON_NUMBER_FRACTION_REFUSED", "LEVEL_LIMIT_EXCEEDED", "NONFINITE_JSON", "REMOVE_UNKNOWN_LEVEL",
    "SEQUENCE_NOT_NONNEGATIVE_INTEGER", "SIDE_UNKNOWN", "SNAPSHOT_DUPLICATE_LEVEL", "TIME_FORMAT_REFUSED",
    "TIME_NOT_TEXT", "TIME_VALUE_REFUSED", "UNEXPECTED_PRODUCT", "UPDATES_NOT_LIST", "ZERO_NOT_ALLOWED",
)
BOOK_STATES = ("NO_SNAPSHOT", "LIVE", "INVALID", "CONNECTION_CLOSED", "UNRESOLVED")
INVALID_REASONS = (
    ("SEQUENCE_DUPLICATE_OR_REORDERED", "SEQUENCE_GAP", "CROSSED_OR_LOCKED_BOOK")
    + tuple("MALFORMED_MESSAGE:" + r for r in L2_REFUSALS)
    + tuple("APPLY_REFUSED:" + r for r in L2_REFUSALS)
)
SILENCE_STATUSES = ("UNRESOLVED", "STALE_BY_SILENCE", "SILENCE_BUDGET_NOT_EXCLUDED", "WITHIN_BUDGET")
AGE_STATUSES = ("UNRESOLVED", "FUTURE", "FUTURE_NOT_EXCLUDED", "STALE", "STALE_NOT_EXCLUDED", "WITHIN_ASSUMPTIONS")
FRESHNESS = ("NOT_USABLE", "FUTURE_TIMESTAMP", "STALE", "FUTURE_NOT_EXCLUDED", "STALE_NOT_EXCLUDED",
             "UNRESOLVED", "QUALIFIED_WITHIN_ASSUMPTIONS", "LIVE_UNQUALIFIED")
SEND_STATES = ("NOT_SUPPLIED", "NATIVE_UNQUALIFIED")
LEVEL_TIME_STATES = ("NOT_SUPPLIED", "NATIVE_UNQUALIFIED")


def _state_reason(st, path):
    """(state, reason) pair: enumerated, and the reason must fit the state."""
    if not isinstance(st, list) or len(st) != 2:
        bad(path, "PAIR_REQUIRED")
    state = one_of(st[0], BOOK_STATES, path + "[0]")
    reason = st[1]
    if state == "INVALID":
        one_of(reason, INVALID_REASONS, path + "[1]")
    elif state == "UNRESOLVED":
        one_of(reason, ("MESSAGE_STRADDLES_AS_OF",), path + "[1]")
    else:
        must_be_none(reason, path + "[1]")
    return state, reason


def check_book(book, flow):
    obj(book, ("state", "bbo", "freshness"), "book")
    state, reason = _state_reason(book["state"], "book.state")
    b = obj(book["bbo"], _BBO_KEYS, "book.bbo")
    text(b["connection_id"], "book.bbo.connection_id", max_len=128)
    if (b["product"], b["base"], b["quote"], b["market_kind"]) != (
            flow["instrument"], flow["base"], flow["quote"], flow["market_kind"]):
        bad("book.bbo", "FLOW_BOOK_IDENTITY_MISMATCH")  # F4: one instrument, one identity
    one_of(b["status"], ("NOT_AVAILABLE", "OBSERVED_UNQUALIFIED"), "book.bbo.status")
    for k in ("mid", "spread", "economic_metrics"):
        must_be_none(b[k], "book.bbo." + k)
    one_of(b["qualification"], ("UNQUALIFIED",), "book.bbo.qualification")
    str_list(b["unattested_assumptions"], "book.bbo.unattested_assumptions")
    if b["status"] == "OBSERVED_UNQUALIFIED":
        if state != "LIVE":
            bad("book.bbo.status", "STATUS_INCONSISTENT")
        must_be_none(b["reason"], "book.bbo.reason")
        for side in ("bid", "ask"):
            lv = obj(b[side], _LEVEL_KEYS, "book.bbo." + side)
            dec(lv["price"], "book.bbo.%s.price" % side, positive=True)
            dec(lv["size"], "book.bbo.%s.size" % side, positive=True)
            opt(lv["level_event_time_ns"], ns, "book.bbo.%s.level_event_time_ns" % side)
            one_of(lv["level_event_time_state"], LEVEL_TIME_STATES, "book.bbo.%s.level_event_time_state" % side)
            is_int(lv["level_last_change_seq"], "book.bbo.%s.level_last_change_seq" % side)
    else:
        must_be_none(b["bid"], "book.bbo.bid")
        must_be_none(b["ask"], "book.bbo.ask")
        want = "EMPTY_SIDE" if state == "LIVE" else (reason or state)
        if b["reason"] != want:
            bad("book.bbo.reason", "STATUS_INCONSISTENT")
    f = book["freshness"]
    if f is None:
        return
    obj(f, _FRESH_KEYS, "book.freshness")
    if f["product"] != flow["instrument"]:
        bad("book.freshness.product", "FLOW_BOOK_IDENTITY_MISMATCH")
    if f["book_state"] != state or f["reason"] != reason:
        bad("book.freshness.book_state", "STATUS_INCONSISTENT")
    silence_status = one_of(f["connection_silence_status"], SILENCE_STATUSES, "book.freshness.connection_silence_status")
    age_status = one_of(f["state_age_status"], AGE_STATUSES, "book.freshness.state_age_status")
    silence = opt(f["connection_silence_ns"], lambda v, p: span(v, p), "book.freshness.connection_silence_ns")
    age = opt(f["state_age_ns"], lambda v, p: span(v, p, signed=True), "book.freshness.state_age_ns")
    if (silence is None) != (silence_status == "UNRESOLVED") or (age is None) != (age_status == "UNRESOLVED"):
        bad("book.freshness", "STATUS_INCONSISTENT")  # a status never claims a value that is absent
    opt(f["connection_last_channel"], text, "book.freshness.connection_last_channel")
    if not isinstance(f["unresolved"], list) or len(f["unresolved"]) > MAX_LIST:
        bad("book.freshness.unresolved", "LIST_REQUIRED")
    for i, v in enumerate(f["unresolved"]):
        code(v, "book.freshness.unresolved[%d]" % i)
    str_list(f["unattested_assumptions"], "book.freshness.unattested_assumptions")
    one_of(f["freshness"], FRESHNESS, "book.freshness.freshness")
    if state != "LIVE":
        if (f["freshness"], silence_status, age_status, f["frontier"]) != ("NOT_USABLE", "UNRESOLVED", "UNRESOLVED", None):
            bad("book.freshness", "STATUS_INCONSISTENT")
        return
    fr = obj(f["frontier"], ("channel", "sequence_num", "send_state"), "book.freshness.frontier")
    if fr["channel"] != l2.COINBASE_L2_FLOW.channel:
        bad("book.freshness.frontier.channel", "FLOW_BOOK_IDENTITY_MISMATCH")
    is_int(fr["sequence_num"], "book.freshness.frontier.sequence_num")
    one_of(fr["send_state"], SEND_STATES, "book.freshness.frontier.send_state")
    # The overall classification is derived, never free: no qualification may exist
    # while the age or the provenance behind it is unresolved.
    if f["freshness"] != l2._overall(silence_status, age_status, None):
        bad("book.freshness.freshness", "STATUS_INCONSISTENT")
    if age_status == "UNRESOLVED" and not f["unresolved"]:
        bad("book.freshness.unresolved", "STATUS_INCONSISTENT")
    if f["freshness"] == "QUALIFIED_WITHIN_ASSUMPTIONS" and (f["unresolved"] or age is None):
        bad("book.freshness.freshness", "STATUS_INCONSISTENT")


# --------------------------------------------------------------------------- heatmap / events

_HEAT_KEYS = ("unit", "aggregation", "tick", "price_lo", "price_hi", "rows", "t0_ns", "bucket_ns", "columns",
              "zero_semantics")
_HEAT_CONST = {
    "unit": "DISPLAYED_BASE_QUANTITY",
    "aggregation": "LAST_LIVE_SAMPLE_IN_BUCKET",
    "zero_semantics": "ABSENT_CELL_IN_LIVE_COLUMN_WITHIN_COVER_IS_OBSERVED_ZERO",
}


def _cells(cells, rows, path):
    if not isinstance(cells, list) or len(cells) > rows:
        bad(path, "LIST_REQUIRED")
    last = -1
    for i, c in enumerate(cells):
        if not isinstance(c, list) or len(c) != 2:
            bad("%s[%d]" % (path, i), "PAIR_REQUIRED")
        j = is_int(c[0], "%s[%d][0]" % (path, i), hi=rows - 1)
        if j <= last:
            bad(path, "CELL_ORDER")
        last = j
        dec(c[1], "%s[%d][1]" % (path, i), positive=True)


@exact
def check_heatmap(h, as_of):
    obj(h, _HEAT_KEYS, "heatmap")
    for k, v in _HEAT_CONST.items():
        if h[k] != v:
            bad("heatmap." + k, "CONSTANT_REFUSED")
    tick = dec(h["tick"], "heatmap.tick", positive=True)
    lo, hi = dec(h["price_lo"], "heatmap.price_lo"), dec(h["price_hi"], "heatmap.price_hi")
    if hi <= lo:
        bad("heatmap", "GRID_GEOMETRY_INVALID")
    whole, rest = divmod(hi - lo, tick)
    rows = is_int(h["rows"], "heatmap.rows", lo=1, hi=MAX_ROWS)
    if rows != int(whole) + (1 if rest else 0):
        bad("heatmap.rows", "GRID_GEOMETRY_INVALID")
    t0, width = ns(h["t0_ns"], "heatmap.t0_ns"), ns(h["bucket_ns"], "heatmap.bucket_ns")
    if width <= 0:
        bad("heatmap.bucket_ns", "GRID_GEOMETRY_INVALID")
    cols = h["columns"]
    if not isinstance(cols, list) or not 1 <= len(cols) <= MAX_COLUMNS:
        bad("heatmap.columns", "LIST_REQUIRED")
    for i, c in enumerate(cols):
        p = "heatmap.columns[%d]" % i
        if not isinstance(c, dict):
            bad(p, "OBJECT_REQUIRED")
        status = c.get("status")
        if status == "LIVE":
            obj(c, ("bucket", "status", "sample_receipt_ns", "bid_cover_floor", "ask_cover_ceiling", "bids", "asks"), p)
        else:
            obj(c, ("bucket", "status", "sample_receipt_ns"), p)
        if is_int(c["bucket"], p + ".bucket") != i:
            bad(p + ".bucket", "BUCKET_ORDER")
        end = t0 + (i + 1) * width
        if status in ("NOT_YET_COMPLETE", "NO_SAMPLE"):
            must_be_none(c["sample_receipt_ns"], p + ".sample_receipt_ns")
            if status == "NOT_YET_COMPLETE" and end <= as_of:
                bad(p + ".status", "STATUS_INCONSISTENT")
            continue
        if end > as_of:
            bad(p + ".status", "BUCKET_AFTER_AS_OF")
        if status != "LIVE":
            if not isinstance(status, str) or not re.fullmatch(r"BOOK_[A-Z0-9_]{1,59}", status, _ASCII):
                bad(p + ".status", "ENUM_REFUSED")
        t = ns(c["sample_receipt_ns"], p + ".sample_receipt_ns")
        if not t0 + i * width <= t < end:
            bad(p + ".sample_receipt_ns", "SAMPLE_OUTSIDE_BUCKET")
        if status == "LIVE":
            opt(c["bid_cover_floor"], dec, p + ".bid_cover_floor")
            opt(c["ask_cover_ceiling"], dec, p + ".ask_cover_ceiling")
            _cells(c["bids"], rows, p + ".bids")
            _cells(c["asks"], rows, p + ".asks")


_EV_COMMON = ("cause", "interval_ns", "kind", "price", "side")
_EV_KEYS = {
    "APPEARED": _EV_COMMON + ("qty",),
    "DISAPPEARED": _EV_COMMON + ("last_qty", "left_censored", "persistence_ns", "trades_at_price_in_interval"),
    "LEFT_COVERED_DEPTH": _EV_COMMON + ("last_qty", "left_censored", "persistence_ns", "trades_at_price_in_interval"),
}


def check_level_events(le):
    obj(le, ("items", "truncated"), "level_events")
    boolean(le["truncated"], "level_events.truncated")
    items = le["items"]
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        bad("level_events.items", "LIST_REQUIRED")
    for i, e in enumerate(items):
        p = "level_events.items[%d]" % i
        if not isinstance(e, dict):
            bad(p, "OBJECT_REQUIRED")
        kind = one_of(e.get("kind"), tuple(_EV_KEYS), p + ".kind")
        obj(e, _EV_KEYS[kind], p)
        one_of(e["side"], ("bid", "ask"), p + ".side")
        dec(e["price"], p + ".price", positive=True)
        span(e["interval_ns"], p + ".interval_ns")
        # The cause of a level change is never claimed.
        one_of(e["cause"], ("NOT_A_DISAPPEARANCE",) if kind == "LEFT_COVERED_DEPTH" else ("CAUSE_UNDETERMINED",),
               p + ".cause")
        if kind == "APPEARED":
            dec(e["qty"], p + ".qty", positive=True)
            continue
        dec(e["last_qty"], p + ".last_qty", positive=True)
        boolean(e["left_censored"], p + ".left_censored")
        pr = obj(e["persistence_ns"], ("min", "max"), p + ".persistence_ns")
        mn = ns(pr["min"], p + ".persistence_ns.min")
        mx = opt(pr["max"], ns, p + ".persistence_ns.max")
        if mx is not None and mx < mn:
            bad(p + ".persistence_ns", "INTERVAL_ORDER")
        if e["left_censored"] != (pr["max"] is None):
            bad(p + ".left_censored", "STATUS_INCONSISTENT")
        is_int(e["trades_at_price_in_interval"], p + ".trades_at_price_in_interval")
