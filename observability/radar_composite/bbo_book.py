"""Order books, per-instant states and the BBO composite (pure, no network).

Event-sourced: every input is a recorded event ``{seq, t_ms, venue, kind, ...}``
applied in receipt order. The state at an instant t uses only events with
``t_ms <= t``; a later event never improves an earlier instant.

Three facts are kept apart for each source:
- ``last_liveness_ms``: last message proving the connection is alive
  (any frame, PONG, heartbeat). It never validates a book;
- ``last_update_ms``: last applied book change (snapshot, delta). It is the
  quote time. PONG/heartbeat never refresh it;
- ``continuity``: NOT_INITIALIZED, SYNCED or CONTINUITY_LOST (with a reason).

After a version break, a checksum mismatch or a disconnection the book is
dropped at once (CONTINUITY_LOST) and comes back only through a full rebuild
(MEXC: official snapshot join; Kraken: a new snapshot whose checksum matches).

Conventions from the Venues contract are reused without change of meaning:
``mid = (bid + ask) / 2``, ``spread_bps = (ask - bid) / mid * 1e4``,
crossed or locked book excluded (ask must be strictly above bid), and the
signed gap ``(mid_kraken - mid_mexc) / mid_mexc * 1e4`` on the MEXC reference.
"""
from __future__ import annotations

import json
import re
import zlib
from decimal import Context, Decimal, localcontext

from . import bbo_wire as wire

CTX = Context(prec=50)
_DEC = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_INT = re.compile(r"^[0-9]{1,30}$")
BPS = Decimal(10_000)
TWO = Decimal(2)
KRAKEN_CHECKSUM_LEVELS = 10

# Per-source states at an instant.
VALID = "VALID"
UNCHANGED_VERIFIED = "UNCHANGED_VERIFIED"
FRESHNESS_UNKNOWN = "FRESHNESS_UNKNOWN"
CONTINUITY_LOST = "CONTINUITY_LOST"
BOOK_INVALID = "BOOK_INVALID"
NOT_INITIALIZED = "NOT_INITIALIZED"
SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
ELIGIBLE = (VALID, UNCHANGED_VERIFIED)
SOURCE_STATES = (VALID, UNCHANGED_VERIFIED, FRESHNESS_UNKNOWN, CONTINUITY_LOST,
                 BOOK_INVALID, NOT_INITIALIZED, SOURCE_UNAVAILABLE)
# Pair categories.
COMPOSITE = "COMPOSITE"
SINGLE_SOURCE = "SINGLE_SOURCE"
SOURCE_EXCLUDED = "SOURCE_EXCLUDED"
EXCESSIVE_GAP = "EXCESSIVE_GAP"
NOT_EVALUATED = "NOT_EVALUATED"
CATEGORIES = (COMPOSITE, SINGLE_SOURCE, SOURCE_EXCLUDED, EXCESSIVE_GAP, NOT_EVALUATED)
VENUES = ("mexc", "kraken")
REFERENCE = "mexc"


class Num(str):
    """A JSON number kept as its exact literal text (Kraken checksum needs it)."""


def kraken_json(raw):
    """Strict JSON with numeric literals preserved as ``Num`` text."""
    def bad_constant(name):
        raise ValueError(f"non-finite constant {name}")
    return json.loads(raw, parse_float=Num, parse_int=Num, parse_constant=bad_constant)


def dec(text):
    """Strict positive decimal literal: digits with an optional fraction."""
    if not isinstance(text, str) or not _DEC.match(text):
        raise ValueError(f"not a plain decimal literal: {text!r}")
    return Decimal(text)


def version(text):
    if not isinstance(text, str) or not _INT.match(text):
        raise ValueError(f"not a version: {text!r}")
    return int(text)


def fmt(d, places=None):
    if d is None:
        return None
    if places is not None:
        d = d.quantize(Decimal(1).scaleb(-places), context=CTX)
    return format(d, "f")


# ---------------------------------------------------------------- Kraken checksum

def _ck(text):
    return text.replace(".", "").lstrip("0")


def kraken_checksum(asks, bids):
    """CRC32 per the official v2 guide over the top 10 levels.

    ``asks``/``bids`` are lists of ``(price_text, qty_text)`` already sorted
    (asks low to high, bids high to low). The texts must be the literals as
    received: the algorithm is defined on their characters, not on values.
    """
    a = "".join(_ck(p) + _ck(q) for p, q in asks[:KRAKEN_CHECKSUM_LEVELS])
    b = "".join(_ck(p) + _ck(q) for p, q in bids[:KRAKEN_CHECKSUM_LEVELS])
    return zlib.crc32((a + b).encode("ascii")) & 0xFFFFFFFF


# ---------------------------------------------------------------- books

class _Book:
    """Price levels keyed by Decimal; the native texts are kept for checksums."""

    def __init__(self):
        self.bids, self.asks = {}, {}

    def clear(self):
        self.bids.clear()
        self.asks.clear()

    def set_level(self, side, price_text, qty_text):
        price, qty = dec(price_text), dec(qty_text)
        book = self.bids if side == "bid" else self.asks
        if qty == 0:
            book.pop(price, None)
        else:
            book[price] = (qty, str(price_text), str(qty_text))

    def sorted_asks(self):
        return sorted(self.asks.items())

    def sorted_bids(self):
        return sorted(self.bids.items(), reverse=True)

    def truncate(self, depth):
        for price, _ in self.sorted_asks()[depth:]:
            del self.asks[price]
        for price, _ in self.sorted_bids()[depth:]:
            del self.bids[price]

    def top(self):
        bid = max(self.bids) if self.bids else None
        ask = min(self.asks) if self.asks else None
        return (bid, None if bid is None else self.bids[bid][0],
                ask, None if ask is None else self.asks[ask][0])


class Source:
    """Common bookkeeping of one venue's book state."""

    venue = ""

    def __init__(self, expected_symbol):
        self.symbol = expected_symbol
        self.book = _Book()
        self.connected = False
        self.unavailable = False          # gave up: budget of reconnects exhausted
        self.continuity = "NOT_INITIALIZED"
        self.lost_reason = None
        self.last_liveness_ms = None
        self.last_update_ms = None
        self.last_top_change_ms = None
        self.synced_at_ms = None
        self.source_ts = None
        self.top = (None, None, None, None)
        self.breaks = []                  # [{t_ms, reason, resolved_at_ms}]
        self.counters = {}
        self.join_log = []

    # -- bookkeeping
    def count(self, key, n=1):
        self.counters[key] = self.counters.get(key, 0) + n

    def alive(self, t):
        self.last_liveness_ms = t

    def lose(self, t, reason):
        """Remove the source from the composite immediately."""
        if self.continuity == "CONTINUITY_LOST" and self.breaks and self.breaks[-1]["resolved_at_ms"] is None:
            self.count("break_while_lost")
        else:
            self.breaks.append({"t_ms": t, "reason": reason, "resolved_at_ms": None})
        self.continuity, self.lost_reason = "CONTINUITY_LOST", reason
        self.book.clear()
        self.top = (None, None, None, None)
        self.synced_at_ms = None

    def synced(self, t):
        self.continuity, self.lost_reason = "SYNCED", None
        self.synced_at_ms = t
        for b in self.breaks:
            if b["resolved_at_ms"] is None:
                b["resolved_at_ms"] = t
        self.book_changed(t, force=True)

    def book_changed(self, t, force=False):
        self.last_update_ms = t
        top = self.book.top()
        if force or top != self.top:
            self.top = top
            self.last_top_change_ms = t

    def on_connect(self, t):
        self.connected = True
        self.alive(t)

    def on_disconnect(self, t, reason="DISCONNECTED"):
        self.connected = False
        if self.continuity != "NOT_INITIALIZED" or self.book.bids or self.book.asks:
            self.lose(t, reason)
        self.reset_join()

    def reset_join(self):
        pass

    def snap(self):
        return {
            "connected": self.connected, "unavailable": self.unavailable,
            "continuity": self.continuity, "lost_reason": self.lost_reason,
            "top": self.top, "last_liveness_ms": self.last_liveness_ms,
            "last_update_ms": self.last_update_ms, "last_top_change_ms": self.last_top_change_ms,
            "synced_at_ms": self.synced_at_ms, "source_ts": self.source_ts,
        }


class MexcSource(Source):
    """MEXC aggregated diff depth with the official snapshot join.

    Official procedure (Spot v3 WebSocket, "How to Properly Maintain a Local
    Copy of the Order Book"): cache diffs from the subscription, fetch the REST
    depth, refetch if ``lastUpdateId`` is below the first cached
    ``fromVersion``, drop diffs with ``toVersion <= lastUpdateId``, reinitialise
    if the first remaining diff has ``fromVersion > lastUpdateId + 1``, then
    require ``fromVersion == previous toVersion + 1`` for every diff.
    """

    venue = "mexc"

    def __init__(self, expected_symbol, channel):
        super().__init__(expected_symbol)
        self.channel = channel
        self.buffer = []          # cached diffs before the join
        self.pending = None       # snapshot waiting for its first usable diff
        self.last_to = None

    def reset_join(self):
        self.buffer, self.pending, self.last_to = [], None, None

    # -- frames
    def on_binary(self, t, payload, actions):
        try:
            push = wire.decode_mexc_push(payload)
        except wire.WireError as exc:
            self.count("decode_error:" + exc.code)
            return
        self.alive(t)
        if push["channel"] != self.channel or (push["symbol"] not in (None, self.symbol)):
            self.count("foreign_frame")
            return
        if push["body_field"] != 313:
            self.count("unexpected_body")
            return
        body = push["body"]
        try:
            diff = {
                "from": version(body["fromVersion"]), "to": version(body["toVersion"]),
                "asks": [(p, q, dec(p), dec(q)) for p, q in body["asks"]],
                "bids": [(p, q, dec(p), dec(q)) for p, q in body["bids"]],
            }
        except ValueError:
            self.count("diff_invalid")
            if self.continuity == "SYNCED":
                self.lose(t, "DIFF_INVALID")
                actions.append(("mexc", "NEED_SNAPSHOT"))
            self.reset_join()
            return
        if diff["from"] > diff["to"]:
            self.count("diff_invalid")
            return
        self.source_ts = {"sendTime": push["sendTime"], "createTime": push["createTime"]}
        self.count("diffs")
        if self.continuity == "SYNCED":
            if diff["from"] != self.last_to + 1:
                self.lose(t, "VERSION_GAP")
                self.reset_join()
                self.buffer = [diff]
                actions.append(("mexc", "NEED_SNAPSHOT"))
                return
            self._apply(diff)
            self.book_changed(t)
            return
        # not synced: cache, keeping the cache internally contiguous
        if self.buffer and diff["from"] != self.buffer[-1]["to"] + 1:
            self.count("buffer_gap")
            self.buffer, self.pending = [], None
        self.buffer.append(diff)
        if self.pending is not None:
            self._try_join(t, actions)
        elif len(self.buffer) == 1:
            actions.append(("mexc", "NEED_SNAPSHOT"))

    def on_text(self, t, payload):
        self.alive(t)
        try:
            doc = json.loads(payload)
        except ValueError:
            self.count("text_invalid")
            return
        if isinstance(doc, dict) and doc.get("msg") == "PONG":
            self.count("pong")
        elif isinstance(doc, dict) and doc.get("msg") == self.channel and doc.get("code") == 0:
            self.count("subscribed")
        else:
            self.count("text_other")

    def on_snapshot(self, t, status, body, actions):
        """REST depth snapshot received (official join, step 2)."""
        self.count("snapshots")
        if status != 200:
            self.join_log.append({"t_ms": t, "outcome": "SNAPSHOT_FETCH_FAILED"})
            actions.append(("mexc", "NEED_SNAPSHOT"))
            return
        try:
            doc = json.loads(body)
            snap = {"last": int(doc["lastUpdateId"]),
                    "bids": [(p, q) for p, q in doc["bids"]],
                    "asks": [(p, q) for p, q in doc["asks"]]}
            for p, q in snap["bids"] + snap["asks"]:
                dec(p), dec(q)
        except (ValueError, KeyError, TypeError):
            self.join_log.append({"t_ms": t, "outcome": "SNAPSHOT_INVALID"})
            actions.append(("mexc", "NEED_SNAPSHOT"))
            return
        if self.continuity == "SYNCED":
            self.join_log.append({"t_ms": t, "outcome": "SNAPSHOT_IGNORED_ALREADY_SYNCED"})
            return
        if not self.buffer:
            self.join_log.append({"t_ms": t, "outcome": "NO_CACHED_DIFF"})
            actions.append(("mexc", "NEED_SNAPSHOT"))
            return
        if snap["last"] < self.buffer[0]["from"]:
            self.join_log.append({"t_ms": t, "outcome": "SNAPSHOT_OLDER_THAN_FIRST_DIFF",
                                  "last_update_id": snap["last"], "first_from": self.buffer[0]["from"]})
            actions.append(("mexc", "NEED_SNAPSHOT"))
            return
        self.pending = snap
        self._try_join(t, actions)

    def _try_join(self, t, actions):
        snap = self.pending
        remaining = [d for d in self.buffer if d["to"] > snap["last"]]
        if not remaining:
            self.buffer = []
            return  # wait for the first diff after the snapshot
        first = remaining[0]
        if first["from"] > snap["last"] + 1:
            self.join_log.append({"t_ms": t, "outcome": "FIRST_DIFF_AFTER_SNAPSHOT_GAP",
                                  "last_update_id": snap["last"], "first_from": first["from"]})
            self.pending = None
            self.buffer = remaining
            actions.append(("mexc", "NEED_SNAPSHOT"))
            return
        self.book.clear()
        for p, q in snap["bids"]:
            self.book.set_level("bid", p, q)
        for p, q in snap["asks"]:
            self.book.set_level("ask", p, q)
        self.last_to = None
        for d in remaining:
            if self.last_to is not None and d["from"] != self.last_to + 1:  # pragma: no cover
                raise AssertionError("cache kept contiguous")
            self._apply(d)
        self.join_log.append({"t_ms": t, "outcome": "JOINED", "last_update_id": snap["last"],
                              "first_from": first["from"], "applied_diffs": len(remaining)})
        self.buffer, self.pending = [], None
        self.synced(t)

    def _apply(self, diff):
        for p, q, _, _ in diff["bids"]:
            self.book.set_level("bid", p, q)
        for p, q, _, _ in diff["asks"]:
            self.book.set_level("ask", p, q)
        self.last_to = diff["to"]


class KrakenSource(Source):
    """Kraken Spot WS v2 ``book`` channel, checksum verified on every message.

    A matching CRC32 shows that the local top 10 levels equal the exchange's
    top 10 after this message. It cannot show that no message was lost and
    later compensated, nor anything below the top 10, since v2 documents no
    sequence number.
    """

    venue = "kraken"

    def __init__(self, expected_symbol, depth=10):
        super().__init__(expected_symbol)
        self.depth = depth

    def on_text(self, t, payload, actions):
        try:
            doc = kraken_json(payload)
        except ValueError:
            self.count("text_invalid")
            return
        self.alive(t)
        if not isinstance(doc, dict):
            self.count("text_other")
            return
        channel, method = doc.get("channel"), doc.get("method")
        if channel == "heartbeat":
            self.count("heartbeat")
        elif method == "pong":
            self.count("pong")
        elif method in ("subscribe", "unsubscribe"):
            ok = doc.get("success") is True
            self.count(f"{method}_{'ok' if ok else 'refused'}")
            if not ok and method == "subscribe":
                actions.append(("kraken", "SUBSCRIBE_REFUSED"))
        elif channel == "book" and doc.get("type") in ("snapshot", "update"):
            for item in doc.get("data") or []:
                self._book(t, doc["type"], item, actions)
        else:
            self.count("text_other")

    def _book(self, t, kind, item, actions):
        if not isinstance(item, dict) or item.get("symbol") != self.symbol:
            self.count("foreign_frame")
            return
        if kind == "update" and self.continuity != "SYNCED":
            self.count("update_ignored_not_synced")
            return
        try:
            if kind == "snapshot":
                self.book.clear()
            for side, key in (("bid", "bids"), ("ask", "asks")):
                for level in item.get(key) or []:
                    self.book.set_level(side, level["price"], level["qty"])
            self.book.truncate(self.depth)
            expected = int(item["checksum"])
        except (ValueError, KeyError, TypeError):
            self.count("book_invalid_message")
            self.lose(t, "MESSAGE_INVALID")
            actions.append(("kraken", "NEED_RESUBSCRIBE"))
            return
        self.source_ts = {"timestamp": item.get("timestamp")}
        asks = [(v[1], v[2]) for _, v in self.book.sorted_asks()]
        bids = [(v[1], v[2]) for _, v in self.book.sorted_bids()]
        got = kraken_checksum(asks, bids)
        self.count(kind + "s")
        if got != expected:
            self.count("checksum_mismatch")
            self.lose(t, "CHECKSUM_MISMATCH")
            actions.append(("kraken", "NEED_RESUBSCRIBE"))
            return
        self.count("checksum_ok")
        if kind == "snapshot":
            self.synced(t)
        else:
            self.book_changed(t)


# ---------------------------------------------------------------- engine

class Engine:
    def __init__(self, mexc_symbol, mexc_channel, kraken_symbol, kraken_depth=10):
        self.sources = {"mexc": MexcSource(mexc_symbol, mexc_channel),
                        "kraken": KrakenSource(kraken_symbol, kraken_depth)}

    def apply(self, ev):
        """Apply one recorded event; returns control actions for the live loop."""
        actions = []
        venue, kind, t = ev["venue"], ev["kind"], ev["t_ms"]
        src = self.sources.get(venue)
        if src is None:
            return actions
        if kind == "ws_open":
            src.on_connect(t)
        elif kind in ("ws_close", "ws_error"):
            src.on_disconnect(t, "DISCONNECTED")
        elif kind == "gave_up":
            src.unavailable = True
            src.on_disconnect(t, "GAVE_UP")
        elif kind == "ws_message":
            payload = ev["payload"]
            if ev["opcode"] == wire.OP_BINARY and venue == "mexc":
                src.on_binary(t, payload, actions)
            elif ev["opcode"] == wire.OP_TEXT:
                if venue == "mexc":
                    src.on_text(t, payload)
                else:
                    src.on_text(t, payload, actions)
            else:
                src.count("unexpected_opcode")
        elif kind == "ws_control":
            src.alive(t)  # protocol ping/pong: liveness only
        elif kind == "rest_depth" and venue == "mexc":
            src.on_snapshot(t, ev["status"], ev["payload"], actions)
        return actions

    def snapshot(self):
        return {v: s.snap() for v, s in self.sources.items()}


def source_state(snap, t, liveness_ms):
    """Classify one source at instant t from its frozen snapshot."""
    if snap["unavailable"]:
        return SOURCE_UNAVAILABLE
    if not snap["connected"] and snap["continuity"] != "CONTINUITY_LOST":
        return SOURCE_UNAVAILABLE
    if snap["continuity"] == "CONTINUITY_LOST":
        return CONTINUITY_LOST
    if snap["continuity"] != "SYNCED":
        return NOT_INITIALIZED
    bid, _, ask, _ = snap["top"]
    if bid is None or ask is None or ask <= bid:
        return BOOK_INVALID
    alive = max(snap["last_liveness_ms"], snap["last_update_ms"])
    if t - alive > liveness_ms:
        return FRESHNESS_UNKNOWN
    if t - snap["last_top_change_ms"] > liveness_ms:
        return UNCHANGED_VERIFIED
    return VALID


def quote_values(snap):
    bid, bid_qty, ask, ask_qty = snap["top"]
    with localcontext(CTX):
        mid = (bid + ask) / TWO
        spread = (ask - bid) / mid * BPS
    return {"bid": bid, "ask": ask, "bid_qty": bid_qty, "ask_qty": ask_qty,
            "mid": mid, "spread_bps": spread}


def gap_bps(mid_kraken, mid_mexc):
    with localcontext(CTX):
        return (mid_kraken - mid_mexc) / mid_mexc * BPS


def evaluate_pair(snaps, t, liveness_ms, gap_max_bps):
    """One instant: per-source states and the pair category (exact Decimal)."""
    states = {v: source_state(snaps[v], t, liveness_ms) for v in VENUES}
    values = {v: quote_values(snaps[v]) if states[v] in ELIGIBLE else None for v in VENUES}
    eligible = [v for v in VENUES if states[v] in ELIGIBLE]
    gap = composite = None
    if len(eligible) == 2:
        gap = gap_bps(values["kraken"]["mid"], values["mexc"]["mid"])
        # Boundary: |gap| == G is admitted (closed interval).
        if abs(gap) <= gap_max_bps:
            category = COMPOSITE
            with localcontext(CTX):
                composite = (values["mexc"]["mid"] + values["kraken"]["mid"]) / TWO
        else:
            category = EXCESSIVE_GAP
    elif len(eligible) == 1:
        category = SINGLE_SOURCE
    else:
        category = SOURCE_EXCLUDED
    return {"states": states, "values": values, "gap_bps": gap, "composite_mid": composite,
            "category": category}


def candle(values):
    """OHLC only for a complete 30/30 series; else no OHLC."""
    if len(values) == 30 and all(v is not None for v in values):
        return {"status": "COMPLETE", "points": 30, "open": values[0], "high": max(values),
                "low": min(values), "close": values[-1]}
    return {"status": "INCOMPLETE", "points": sum(v is not None for v in values),
            "open": None, "high": None, "low": None, "close": None}


def sample(engine, events, instants):
    """Freeze the engine state at each instant using only events with t_ms <= instant.

    ``events`` are applied in receipt (seq) order and their ``t_ms`` must be
    non-decreasing. Returns one snapshot per instant (instants ascending).
    """
    out, it, pending = [], iter(events), None
    last_t = None
    for instant in instants:
        while True:
            if pending is None:
                pending = next(it, None)
                if pending is None:
                    break
                if last_t is not None and pending["t_ms"] < last_t:
                    raise ValueError("events out of receipt order")
                last_t = pending["t_ms"]
            if pending["t_ms"] > instant:
                break
            engine.apply(pending)
            pending = None
        out.append(engine.snapshot())
    for ev in ([pending] if pending is not None else []) + list(it):
        if last_t is not None and ev["t_ms"] < last_t:
            raise ValueError("events out of receipt order")
        last_t = ev["t_ms"]
        engine.apply(ev)
    return out
