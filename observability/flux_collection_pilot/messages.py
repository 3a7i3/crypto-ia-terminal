"""Tolerant-on-time, strict-on-shape decoding of one Coinbase application message.

Layout read from the official AsyncAPI document (dated limits in the report):
envelope ``channel`` / ``timestamp`` (server send time) / ``sequence_num``;
``l2_data`` events with ``updates``; ``market_trades`` events with ``trades``
(``side`` = the MAKER's side per the AsyncAPI text); ``heartbeats`` events.

Unlike the Flux L2 prototype (not imported here): a bad or missing time is
RECORDED (state) instead of refusing the message, because the pilot must count
them; no sequence judgement is made here. Strict JSON and RFC 3339 parsing are
local copies (``exactjson``) pinned to the originals by a test.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from . import exactjson as xj
from . import protocol

_DEC = re.compile(r"[0-9]{1,30}(\.[0-9]{1,30})?")
OK, MISSING, INVALID, SENTINEL = "OK", "MISSING", "INVALID", "SENTINEL_EPOCH"


class MessageRefusal(ValueError):
    """Stable reason code in the message text."""


@dataclass(frozen=True)
class TimeObs:
    state: str  # OK | MISSING | INVALID | SENTINEL_EPOCH
    ns: object  # int or None (never a guessed value)


def time_obs(container, key):
    if not isinstance(container, dict) or key not in container:
        return TimeObs(MISSING, None)
    try:
        ns = xj.parse_rfc3339_ns(container[key])
    except xj.Refusal:
        return TimeObs(INVALID, None)
    if ns <= 0:
        return TimeObs(SENTINEL, ns)  # A-PLACEHOLDER: at or before the Unix epoch
    return TimeObs(OK, ns)


def after_cut(obs, cut_ns):
    return obs.state == OK and cut_ns is not None and obs.ns > cut_ns


def _dec(text, *, zero_ok):
    if not isinstance(text, str) or not _DEC.fullmatch(text):
        raise MessageRefusal("DECIMAL_TEXT_REFUSED")
    try:
        d = Decimal(text)
    except InvalidOperation:
        raise MessageRefusal("DECIMAL_TEXT_REFUSED") from None
    if d == 0 and not zero_ok:
        raise MessageRefusal("ZERO_NOT_ALLOWED")
    return d


@dataclass(frozen=True)
class Parsed:
    kind: str  # "data" | "error"
    channel: object
    seq: object
    send: TimeObs
    products: tuple
    l2_events: tuple  # ((event_type, product, ((side, price, ptxt, qty, qtxt, TimeObs), ...)), ...)
    trades: tuple  # ({trade_id, product, price, size, side, time: TimeObs}, ...)
    heartbeat_counters: tuple
    heartbeat_times: tuple  # TimeObs of current_time
    error_text: object = None

    @property
    def snapshot_events(self):
        """Events LABELLED snapshot, whatever they contain (presence proves nothing)."""
        return sum(1 for e in self.l2_events if e[0] == "snapshot")

    @property
    def snapshots(self):
        """USABLE snapshots: a book can be built from them (at least one bid AND one offer level)."""
        return sum(1 for e in self.l2_events if e[0] == "snapshot"
                   and {u[0] for u in e[2]} >= set(xj.SIDES))


def parse_message(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise MessageRefusal("BYTES_REQUIRED")
    try:
        d = xj.strict_json(bytes(raw))
    except xj.Refusal as e:
        raise MessageRefusal(str(e)) from None
    if not isinstance(d, dict):
        raise MessageRefusal("ENVELOPE_NOT_OBJECT")
    if d.get("type") == "error":
        msg = d.get("message")
        return Parsed("error", None, None, TimeObs(MISSING, None), (), (), (), (), (),
                      msg if isinstance(msg, str) else None)
    channel, seq = d.get("channel"), d.get("sequence_num")
    if not isinstance(channel, str) or not channel:
        raise MessageRefusal("CHANNEL_MISSING")
    if type(seq) is not int or seq < 0:
        raise MessageRefusal("SEQUENCE_NOT_NONNEGATIVE_INTEGER")
    send = time_obs(d, "timestamp")
    events = d.get("events", [])
    if not isinstance(events, list):
        raise MessageRefusal("EVENTS_NOT_LIST")
    products, l2_events, trades, hb_n, hb_t = [], [], [], [], []
    for ev in events:
        if not isinstance(ev, dict):
            raise MessageRefusal("EVENT_NOT_OBJECT")
        if channel == protocol.L2_CHANNEL:
            kind, product = ev.get("type"), ev.get("product_id")
            if kind not in ("snapshot", "update"):
                raise MessageRefusal("EVENT_TYPE_UNKNOWN")
            if not isinstance(product, str):
                raise MessageRefusal("PRODUCT_MISSING")
            if product != protocol.PRODUCT:
                raise MessageRefusal("UNEXPECTED_PRODUCT")
            ups = ev.get("updates")
            if not isinstance(ups, list):
                raise MessageRefusal("UPDATES_NOT_LIST")
            parsed, seen = [], set()
            for u in ups:
                if not isinstance(u, dict) or u.get("side") not in xj.SIDES:
                    raise MessageRefusal("SIDE_UNKNOWN")
                price = _dec(u.get("price_level"), zero_ok=False)
                qty = _dec(u.get("new_quantity"), zero_ok=(kind == "update"))
                if kind == "snapshot":
                    if (u["side"], price) in seen:
                        raise MessageRefusal("SNAPSHOT_DUPLICATE_LEVEL")
                    seen.add((u["side"], price))
                parsed.append((u["side"], price, u["price_level"], qty, u["new_quantity"],
                               time_obs(u, "event_time")))
            products.append(product)
            l2_events.append((kind, product, tuple(parsed)))
        elif channel == protocol.TRADES_CHANNEL:
            ts = ev.get("trades")
            if ev.get("type") not in ("snapshot", "update") or not isinstance(ts, list):
                raise MessageRefusal("TRADES_EVENT_REFUSED")
            for t in ts:
                if not isinstance(t, dict):
                    raise MessageRefusal("TRADE_NOT_OBJECT")
                product = t.get("product_id")
                if product != protocol.PRODUCT:
                    raise MessageRefusal("UNEXPECTED_PRODUCT")
                tid = t.get("trade_id")
                if not isinstance(tid, str) or not tid:
                    raise MessageRefusal("TRADE_ID_REQUIRED")
                _dec(t.get("price"), zero_ok=False)
                _dec(t.get("size"), zero_ok=False)
                products.append(product)
                trades.append({
                    "trade_id": tid, "product": product, "price": t["price"], "size": t["size"],
                    "side": t.get("side"), "time": time_obs(t, "time"), "time_text": t.get("time"),
                })
        elif channel == protocol.HEARTBEAT_CHANNEL:
            c = ev.get("heartbeat_counter")
            hb_n.append(c if type(c) is int else None)
            hb_t.append(time_obs(ev, "current_time"))
    return Parsed("data", channel, seq, send, tuple(sorted(set(products))), tuple(l2_events),
                  tuple(trades), tuple(hb_n), tuple(hb_t))
