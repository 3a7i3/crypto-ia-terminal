"""Level-2 book reconstruction for CryptoRadar Flux (source only, #551/#553).

Graduated from docs/research/market_v0_551 (kept as the reviewed reference; a
differential test pins both to the same behaviour). NON_ADMIS / NOT WIRED.
Stdlib only. No network, no clock read, no file write. Every time is an integer
supplied by the caller; this module never asks the machine for one.

Scope: the *candidate* Coinbase Advanced level2 message layout documented in
#548 (``l2_data`` envelope, per-connection ``sequence_num``, ``event_time`` of an
update, ``timestamp`` = message send time). It is NOT the REST roster, it is NOT
admitted, and nothing here proves that the provider really behaves this way:
the unattested hypotheses are listed in ``ASSUMPTIONS`` and echoed in outputs.

Principles kept from #543/#546/#548:
- UNKNOWN is never 0; a missing bound yields None plus a reason.
- A freshness claim needs a covering, unexpired attestation; "just received" is
  never "fresh".
- A level's last-change time is reported, never promoted to the age of the BBO.
- Prices and quantities keep their native text; arithmetic is Decimal/int only.
- No mid, spread, score or economic metric is produced.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import calendar
import json
import re

from . import interval as _ref

Span, Window = _ref.Span, _ref.Window

MAX_MESSAGE_BYTES = 512_000
INSTRUMENTS = {"BTC-USD": ("BTC", "USD"), "ETH-USD": ("ETH", "USD")}
SIDES = {"bid": "bids", "offer": "asks"}

ASSUMPTIONS = {
    "A-LAYOUT": "Message layout (event types, side labels) read from #548 excerpts only; "
    "snapshot/update labels and side labels are NOT attested by a dated, hashed excerpt.",
    "A-SEQ-CONN": "sequence_num is one counter per connection across all messages "
    "(documented per connection in #548; 'across all channels' is NOT attested).",
    "A-QTY-ABS": "new_quantity is the absolute quantity at the level, 0 removes it (NOT attested).",
    "A-SNAP-FULL": "A snapshot event is the complete book of its product (NOT attested).",
    "A-STREAM-ORDER": "Messages of one connection arrive in send order (transport property, NOT attested).",
    "A-PLACEHOLDER": "An event_time at or before the Unix epoch is a placeholder, not a date (hypothesis).",
    "A-SEND-AS-OF": "Envelope timestamp labels a state the stream already reflects "
    "(link between send time and book state is NOT attested).",
}

_RFC3339 = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z"
)


class L2Refusal(ValueError):
    """A message that must not be trusted; the message is the stable reason code."""


def parse_rfc3339_ns(text):
    """Exact UTC nanoseconds from 'Z' RFC 3339 text; no float, no truncation."""
    if not isinstance(text, str):
        raise L2Refusal("TIME_NOT_TEXT")
    m = _RFC3339.fullmatch(text)
    if not m:
        raise L2Refusal("TIME_FORMAT_REFUSED")
    y, mo, d, h, mi, s = (int(x) for x in m.groups()[:6])
    try:
        moment = datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
    except ValueError:
        raise L2Refusal("TIME_VALUE_REFUSED") from None
    fraction = (m.group(7) or "").ljust(9, "0")
    return calendar.timegm(moment.timetuple()) * 1_000_000_000 + int(fraction or "0")


def _strict_json(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_MESSAGE_BYTES:
        raise L2Refusal("BOUNDED_BYTES_REQUIRED")

    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise L2Refusal("DUPLICATE_NATIVE_FIELD")
            out[k] = v
        return out

    def constant(_):
        raise L2Refusal("NONFINITE_JSON")

    def no_float(_):
        # A JSON number for a price/size/time is inexact by construction.
        raise L2Refusal("JSON_NUMBER_FRACTION_REFUSED")

    try:
        return json.loads(
            raw.decode("utf-8"),
            parse_float=no_float,
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except L2Refusal:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise L2Refusal("INVALID_JSON") from None


def _decimal(text, *, zero_ok):
    if not isinstance(text, str) or not re.fullmatch(r"\d{1,30}(\.\d{1,30})?", text):
        raise L2Refusal("DECIMAL_TEXT_REFUSED")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise L2Refusal("DECIMAL_TEXT_REFUSED") from None
    if value == 0 and not zero_ok:
        raise L2Refusal("ZERO_NOT_ALLOWED")
    return value


def _integer(value):
    if type(value) is not int or value < 0:
        raise L2Refusal("SEQUENCE_NOT_NONNEGATIVE_INTEGER")
    return value


@dataclass(frozen=True)
class Receipt:
    """Observer clocks around full receipt: monotonic span and local-UTC span."""

    mono: Span
    utc: Span

    def __post_init__(self):
        if type(self.mono) is not Span or type(self.utc) is not Span:
            raise TypeError("SPAN_REQUIRED")


@dataclass(frozen=True)
class ObserverAttestation:
    """Bound on the local clock error, valid only inside ``valid_utc``."""

    scale: str
    bound_ns: int
    valid_utc: Span
    evidence_ref: str

    def window(self, utc):
        """Common-scale window of a local-UTC span, or (None, reason)."""
        if type(self.bound_ns) is not int or self.bound_ns < 0:
            return None, "OBSERVER_BOUND_INVALID"
        if not self.evidence_ref:
            return None, "OBSERVER_EVIDENCE_MISSING"
        if utc.lo < self.valid_utc.lo or utc.hi > self.valid_utc.hi:
            return None, "OBSERVER_ATTESTATION_EXPIRED_OR_NOT_COVERING"
        b = self.bound_ns
        return Window(self.scale, Span(utc.lo - b, utc.hi + b)), None


@dataclass(frozen=True)
class FlowIdentity:
    """Declared identity of a flow: provider, host, channel and layout version.

    The prototype cannot authenticate a transport; the caller (a future plan)
    declares which flow the bytes belong to, and every proof must name the same
    one. No neighbour transfer: another provider, host or channel never matches.
    """

    venue: str
    host: str
    channel: str
    layout_version: str


COINBASE_L2_FLOW = FlowIdentity(
    "coinbase_advanced",
    "advanced-trade-ws.coinbase.com",
    "l2_data",
    "ASYNCAPI_3.0.0_INFO_1.0.0",  # declared version in #548; not an immutable revision
)


@dataclass(frozen=True)
class ClockAttestation:
    """Provider-clock proof for ONE exact field on ONE flow (no neighbour transfer)."""

    flow: FlowIdentity
    products: frozenset
    field: str
    scale: str
    offset: Span
    quantization: Span
    lag: Span
    validity: Window
    evidence_ref: str
    attested_by: str

    def window(self, native_ns, flow, product, field):
        if not self.evidence_ref or not self.attested_by:
            return None, "ATTESTATION_PROVENANCE_MISSING"
        if type(self.flow) is not FlowIdentity or self.flow != flow:
            return None, "ATTESTATION_FLOW_MISMATCH"
        if field != self.field or product not in self.products:
            return None, "ATTESTATION_DOMAIN_MISMATCH"
        event = _ref.event_window(
            native_ns,
            offset=self.offset,
            quantization=self.quantization,
            event_to_stamp_lag=self.lag,
            scale=self.scale,
        )
        if event is None:
            return None, "ATTESTATION_INCOMPLETE"
        if (
            event.scale != self.validity.scale
            or event.span.lo < self.validity.span.lo
            or event.span.hi > self.validity.span.hi
        ):
            return None, "ATTESTATION_NOT_COVERING_EVENT_WINDOW"
        return event, None


def _level_time(update):
    """(ns|None, state) for an optional update event_time."""
    if "event_time" not in update:
        return None, "NOT_SUPPLIED"
    ns = parse_rfc3339_ns(update["event_time"])
    if ns <= 0:
        return None, "PLACEHOLDER_EPOCH_NOT_A_DATE"
    return ns, "NATIVE_UNQUALIFIED"


def _decode(raw):
    """Pure decode: (envelope, ops). Raises L2Refusal; touches no book."""
    d = _strict_json(raw)
    if not isinstance(d, dict):
        raise L2Refusal("ENVELOPE_NOT_OBJECT")
    seq = _integer(d.get("sequence_num"))
    channel = d.get("channel")
    if not isinstance(channel, str) or not channel:
        raise L2Refusal("CHANNEL_MISSING")
    send_ns, send_state = None, "NOT_SUPPLIED"
    if "timestamp" in d:
        send_ns, send_state = parse_rfc3339_ns(d["timestamp"]), "NATIVE_UNQUALIFIED"
    env = {"sequence_num": seq, "channel": channel, "send_ns": send_ns, "send_state": send_state}
    ops = []
    if channel != "l2_data":
        return env, ops
    events = d.get("events")
    if not isinstance(events, list):
        raise L2Refusal("EVENTS_NOT_LIST")
    for ev in events:
        if not isinstance(ev, dict):
            raise L2Refusal("EVENT_NOT_OBJECT")
        kind, product = ev.get("type"), ev.get("product_id")
        if not isinstance(kind, str) or kind not in ("snapshot", "update"):
            raise L2Refusal("EVENT_TYPE_UNKNOWN")
        if not isinstance(product, str) or product not in INSTRUMENTS:
            raise L2Refusal("UNEXPECTED_PRODUCT")
        updates = ev.get("updates")
        if not isinstance(updates, list):
            raise L2Refusal("UPDATES_NOT_LIST")
        parsed, seen = [], set()
        for u in updates:
            if (
                not isinstance(u, dict)
                or not isinstance(u.get("side"), str)
                or u["side"] not in SIDES
            ):
                raise L2Refusal("SIDE_UNKNOWN")
            price_text, qty_text = u.get("price_level"), u.get("new_quantity")
            price = _decimal(price_text, zero_ok=False)
            qty = _decimal(qty_text, zero_ok=(kind == "update"))
            when, when_state = _level_time(u)
            key = (u["side"], price)
            if kind == "snapshot" and key in seen:
                raise L2Refusal("SNAPSHOT_DUPLICATE_LEVEL")
            seen.add(key)
            parsed.append((u["side"], price, price_text, qty, qty_text, when, when_state))
        ops.append((kind, product, parsed))
    return env, ops


class _Book:
    def __init__(self):
        self.state, self.reason = "NO_SNAPSHOT", None
        self.bids, self.asks = {}, {}
        self.resyncs = 0
        # (send_ns, send_state, sequence_num, receipt) of the last accepted
        # l2_data message that carried an event for THIS product; never a
        # heartbeat or another channel, never another product's message.
        self.frontier = None

    def clone(self):
        c = _Book()
        c.state, c.reason, c.resyncs = self.state, self.reason, self.resyncs
        c.frontier = self.frontier
        c.bids, c.asks = dict(self.bids), dict(self.asks)
        return c

    def side(self, name):
        return self.bids if SIDES[name] == "bids" else self.asks

    def crossed(self):
        return bool(self.bids and self.asks and max(self.bids) >= min(self.asks))


class L2Connection:
    """One connection's books. A new connection never inherits any state."""

    def __init__(self, connection_id, flow, *, max_levels_per_side=5000):
        if not isinstance(connection_id, str) or not connection_id:
            raise ValueError("CONNECTION_ID_REQUIRED")
        if flow != COINBASE_L2_FLOW:
            # The decoder implements one documented layout; no other flow.
            raise ValueError("UNSUPPORTED_FLOW")
        self.flow = flow
        if type(max_levels_per_side) is not int or max_levels_per_side < 1:
            raise ValueError("LEVEL_LIMIT_REQUIRED")
        self.connection_id = connection_id
        self.limit = max_levels_per_side
        self.books = {p: _Book() for p in INSTRUMENTS}
        self.expected_seq = None
        self.baseline_seq = None
        self.closed = False
        self.last_receipt = None  # any channel: connection liveness only
        self.last_channel = None
        self.messages_applied = 0

    # -- invalidation -----------------------------------------------------
    def _invalidate(self, reason, products=None):
        for p in products or self.books:
            b = self.books[p]
            if b.state == "LIVE":  # a book never built stays NO_SNAPSHOT
                b.state, b.reason = "INVALID", reason

    def close(self):
        self.closed = True

    # -- ingestion --------------------------------------------------------
    def feed(self, raw, receipt):
        """Apply one message. Returns a result dict; never raises on bad bytes."""
        if type(receipt) is not Receipt:
            raise TypeError("RECEIPT_REQUIRED")
        if self.closed:
            return {"accepted": False, "reason": "CONNECTION_CLOSED"}
        try:
            env, ops = _decode(raw)
        except L2Refusal as e:
            # Content is lost: deltas cannot be trusted; a snapshot supersedes.
            self._invalidate("MALFORMED_MESSAGE:" + str(e))
            self.expected_seq = None
            return {"accepted": False, "reason": str(e)}
        seq = env["sequence_num"]
        note = None
        if self.expected_seq is None:
            if self.baseline_seq is None:
                self.baseline_seq = seq
            self.expected_seq = seq + 1
        elif seq == self.expected_seq:
            self.expected_seq = seq + 1
        elif seq < self.expected_seq:
            self._invalidate("SEQUENCE_DUPLICATE_OR_REORDERED")
            return {"accepted": False, "reason": "SEQUENCE_DUPLICATE_OR_REORDERED"}
        else:
            self._invalidate("SEQUENCE_GAP")
            self.expected_seq = seq + 1
            note = "SEQUENCE_GAP"
        # Candidate copies so a refused message leaves the books untouched.
        staged = {}
        try:
            for kind, product, updates in ops:
                book = staged.get(product) or self.books[product].clone()
                staged[product] = book
                self._apply(book, kind, updates)
        except L2Refusal as e:
            # Events after the faulty one were never applied either: no product
            # can be trusted, whatever its position in the message.
            self._invalidate("APPLY_REFUSED:" + str(e))
            return {"accepted": False, "reason": str(e)}
        for product, book in staged.items():
            if book.state == "LIVE" and book.crossed():
                book.state, book.reason = "INVALID", "CROSSED_OR_LOCKED_BOOK"
            book.frontier = (env["send_ns"], env["send_state"], seq, receipt)
            self.books[product] = book
        self.last_receipt = receipt
        self.last_channel = env["channel"]
        self.messages_applied += 1
        return {"accepted": True, "reason": note, "sequence_num": seq}

    def _apply(self, book, kind, updates):
        if kind == "snapshot":
            if book.state == "INVALID":
                book.resyncs += 1
            book.bids, book.asks = {}, {}
            book.state, book.reason = "LIVE", None
            for side, price, ptxt, qty, qtxt, when, wstate in updates:
                book.side(side)[price] = (ptxt, qty, qtxt, when, wstate, self.expected_seq - 1)
        else:
            if book.state != "LIVE":
                # Deltas on an unknown/invalid base are discarded, not guessed.
                return
            for side, price, ptxt, qty, qtxt, when, wstate in updates:
                levels = book.side(side)
                if qty == 0:
                    if price not in levels:
                        raise L2Refusal("REMOVE_UNKNOWN_LEVEL")
                    del levels[price]
                else:
                    levels[price] = (ptxt, qty, qtxt, when, wstate, self.expected_seq - 1)
        if len(book.bids) > self.limit or len(book.asks) > self.limit:
            raise L2Refusal("LEVEL_LIMIT_EXCEEDED")

    # -- reading ----------------------------------------------------------
    def state(self, product):
        if self.closed:
            return "CONNECTION_CLOSED", None
        b = self.books[product]
        return b.state, b.reason

    def bbo(self, product):
        """Best bid/ask with native text and per-level provenance; no metrics."""
        state, reason = self.state(product)
        out = {
            "connection_id": self.connection_id,
            "product": product,
            "base": INSTRUMENTS[product][0],
            "quote": INSTRUMENTS[product][1],
            "market_kind": "SPOT",
            "status": "NOT_AVAILABLE",
            "reason": reason or state,
            "bid": None,
            "ask": None,
            "mid": None,
            "spread": None,
            "economic_metrics": None,
            "qualification": "UNQUALIFIED",
            "unattested_assumptions": sorted(ASSUMPTIONS),
        }
        if state != "LIVE":
            return out
        b = self.books[product]
        if not b.bids or not b.asks:
            out["reason"] = "EMPTY_SIDE"
            return out

        def view(level):
            ptxt, _, qtxt, when, wstate, seq = level
            return {
                "price": ptxt,
                "size": qtxt,
                "level_event_time_ns": when,
                "level_event_time_state": wstate,
                "level_last_change_seq": seq,
            }

        out.update(
            status="OBSERVED_UNQUALIFIED",
            reason=None,
            bid=view(b.bids[max(b.bids)]),
            ask=view(b.asks[min(b.asks)]),
        )
        return out

    def levels(self, product):
        """Full exact book of a LIVE product as (bids desc, asks asc) text pairs.

        Returns None unless LIVE. Depth is whatever the snapshot/updates gave;
        A-SNAP-FULL (unattested) says the snapshot is complete.
        """
        if self.state(product)[0] != "LIVE":
            return None
        b = self.books[product]
        bids = [(b.bids[k][0], b.bids[k][2]) for k in sorted(b.bids, reverse=True)]
        asks = [(b.asks[k][0], b.asks[k][2]) for k in sorted(b.asks)]
        return bids, asks

    def freshness(
        self,
        product,
        now,
        *,
        silence_budget_ns,
        age_budget_ns=None,
        observer=None,
        envelope_clock=None,
    ):
        """Two separate questions, never merged.

        1. Connection silence: observer-only, monotonic, any channel. It can
           refuse a silent connection; it says nothing about the book's age.
        2. Book frontier: the send time of the last accepted ``l2_data``
           message that carried an event for THIS product, qualified only by a
           proof naming this exact flow, product and field. A heartbeat or any
           other channel never dates the book, and sequence continuity is
           checked independently of this qualification.

        ``silence_budget_ns`` has no default: its value is a governance decision.
        The level event_time is deliberately NOT used (a level can stay valid
        while old). A quiet product keeps an old frontier: that is fail-safe.
        """
        if type(now) is not Receipt:
            raise TypeError("RECEIPT_REQUIRED")
        state, reason = self.state(product)
        out = {
            "product": product,
            "book_state": state,
            "reason": reason,
            "connection_silence_ns": None,
            "connection_silence_status": "UNRESOLVED",
            "connection_last_channel": self.last_channel,
            "frontier": None,
            "state_age_ns": None,
            "state_age_status": "UNRESOLVED",
            "unresolved": [],
            "freshness": "NOT_USABLE",
            "unattested_assumptions": sorted(ASSUMPTIONS),
        }
        if state != "LIVE":
            return out
        if type(silence_budget_ns) is not int or silence_budget_ns < 0:
            raise ValueError("EXPLICIT_SILENCE_BUDGET_REQUIRED")
        last = self.last_receipt.mono
        silence = (
            None
            if now.mono.hi < last.lo
            else Span(max(0, now.mono.lo - last.hi), now.mono.hi - last.lo)
        )
        if silence is None:
            out["unresolved"].append("MONOTONIC_ORDER_NOT_ESTABLISHED")
        else:
            out["connection_silence_ns"] = [silence.lo, silence.hi]
            out["connection_silence_status"] = (
                "STALE_BY_SILENCE"
                if silence.lo > silence_budget_ns
                else "SILENCE_BUDGET_NOT_EXCLUDED"
                if silence.hi > silence_budget_ns
                else "WITHIN_BUDGET"
            )
        send_ns, send_state, frontier_seq, _ = self.books[product].frontier
        out["frontier"] = {
            "channel": self.flow.channel,
            "sequence_num": frontier_seq,
            "send_state": send_state,
        }
        window = None
        if send_ns is None:
            out["unresolved"].append("SEND_TIME_" + send_state)
        elif observer is None:
            out["unresolved"].append("OBSERVER_ATTESTATION_MISSING")
        elif envelope_clock is None:
            out["unresolved"].append("PROVIDER_CLOCK_ATTESTATION_MISSING")
        elif age_budget_ns is None:
            out["unresolved"].append("AGE_BUDGET_NOT_SUPPLIED")
        else:
            now_w, why = observer.window(now.utc)
            event_w, why2 = envelope_clock.window(
                send_ns, self.flow, product, "l2_data.timestamp"
            )
            if why or why2:
                out["unresolved"].append(why or why2)
            else:
                try:
                    age = _ref.age_window(now_w, event_w)
                except ValueError:
                    out["unresolved"].append("DIFFERENT_COMMON_SCALES")
                else:
                    window = age
                    out["state_age_ns"] = [age.lo, age.hi]
                    out["state_age_status"] = _ref.classify_age(
                        age, max_age_ns=age_budget_ns
                    )
        out["freshness"] = _overall(
            out["connection_silence_status"], out["state_age_status"], window
        )
        return out


def _overall(silence, age_status, window):
    if age_status == "FUTURE":
        return "FUTURE_TIMESTAMP"
    if silence == "STALE_BY_SILENCE" or age_status == "STALE":
        return "STALE"
    if age_status == "FUTURE_NOT_EXCLUDED":
        return "FUTURE_NOT_EXCLUDED"
    if age_status == "STALE_NOT_EXCLUDED" or silence == "SILENCE_BUDGET_NOT_EXCLUDED":
        return "STALE_NOT_EXCLUDED"
    if silence == "UNRESOLVED":
        return "UNRESOLVED"
    if age_status == "WITHIN_ASSUMPTIONS":
        return "QUALIFIED_WITHIN_ASSUMPTIONS"
    return "LIVE_UNQUALIFIED"


def pair_state(a, b, *, max_gap_ns=None):
    """Cross-venue relation. Without two qualified windows: UNRESOLVED, no metric.

    ``a`` and ``b`` are dicts with an optional ``event_window`` (Window); a venue
    that supplies nothing (e.g. a flow whose documentation is unreadable) keeps
    the pair UNRESOLVED instead of being filled from another transport.
    """
    out = {"comparability": "NOT_PROVEN", "separation_ns": None, "mid": None, "spread": None}
    wa, wb = (a or {}).get("event_window"), (b or {}).get("event_window")
    if wa is None or wb is None:
        out["reason"] = "SOURCE_NOT_SUPPLIED_OR_UNQUALIFIED"
        return out
    if max_gap_ns is None:
        out["reason"] = "EXPLICIT_GAP_BUDGET_REQUIRED"
        return out
    try:
        gap = _ref.separation_window(wa, wb)
    except ValueError:
        out["reason"] = "DIFFERENT_COMMON_SCALES"
        return out
    out["separation_ns"] = [gap.lo, gap.hi]
    out["reason"] = _ref.classify_separation(gap, max_gap_ns=max_gap_ns)
    return out
