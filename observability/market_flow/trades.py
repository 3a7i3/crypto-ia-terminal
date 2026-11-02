"""Trades, deduplication, delta and CVD with exact arithmetic.

Definitions (stated, not inferred):
- delta = aggressive buy volume - aggressive sell volume inside an interval.
- bar delta = delta of one bar; rolling delta = delta over the last W complete
  bars; session CVD = running sum of bar deltas from an explicit anchor,
  restarted at every coverage gap (a gap is kept, never bridged).
- An unknown aggressor side is never buy nor sell: its volume is carried
  separately and makes delta a *bounded* interval instead of a number.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from .exact import exact

_DEC = re.compile(r"[0-9]{1,30}(\.[0-9]{1,30})?")  # ASCII digits only
BUY, SELL, UNKNOWN = "BUY", "SELL", "UNKNOWN"


class TradeRefusal(ValueError):
    """Stable refusal reason code."""


def _dec(text, *, positive=True):
    if not isinstance(text, str) or not _DEC.fullmatch(text):
        raise TradeRefusal("DECIMAL_TEXT_REFUSED")
    try:
        d = Decimal(text)
    except InvalidOperation:
        raise TradeRefusal("DECIMAL_TEXT_REFUSED") from None
    if positive and d <= 0:
        raise TradeRefusal("NON_POSITIVE_REFUSED")
    return d


def _text(value):
    return format(value, "f")


@dataclass(frozen=True)
class SideConvention:
    """Maps a provider's raw side text to the AGGRESSOR (taker) side.

    ``attested`` is False until a dated, hashed excerpt states what the raw
    field means (maker side vs taker side); outputs carry this flag.
    """

    mapping: tuple  # ((raw_text, "BUY"|"SELL"), ...)
    attested: bool
    evidence_ref: str

    def __post_init__(self):
        # An ambiguous or malformed table is refused here: no entry order may
        # silently pick a sign, and delta must never depend on it.
        if not isinstance(self.mapping, tuple):
            raise ValueError("SIDE_MAPPING_MALFORMED")
        seen = set()
        for entry in self.mapping:
            if (not isinstance(entry, tuple) or len(entry) != 2 or not isinstance(entry[0], str)
                    or not entry[0] or entry[1] not in (BUY, SELL)):
                raise ValueError("SIDE_MAPPING_MALFORMED")
            if entry[0] in seen:
                raise ValueError("SIDE_MAPPING_AMBIGUOUS")  # duplicate raw value, even if identical
            seen.add(entry[0])
        if type(self.attested) is not bool or not isinstance(self.evidence_ref, str) or not self.evidence_ref:
            raise ValueError("SIDE_CONVENTION_EVIDENCE_REQUIRED")

    def aggressor(self, raw):
        if not isinstance(raw, str):
            return UNKNOWN
        for r, a in self.mapping:
            if r == raw and a in (BUY, SELL):
                return a
        return UNKNOWN  # absent, unmapped or ambiguous: never a default side


@dataclass(frozen=True)
class TradeFlow:
    venue: str
    instrument: str  # native symbol
    base: str
    quote: str  # the currency of price*size; USD is not USDT is not USDC
    market_kind: str  # SPOT only here
    id_domain: str  # "SESSION": ids unique per session; "INSTRUMENT": across sessions
    side: SideConvention

    def __post_init__(self):
        if self.market_kind != "SPOT":
            raise ValueError("SPOT_ONLY")
        if self.id_domain not in ("SESSION", "INSTRUMENT"):
            raise ValueError("ID_DOMAIN_REQUIRED")
        if not (self.venue and self.instrument and self.base and self.quote):
            raise ValueError("FLOW_IDENTITY_REQUIRED")


@dataclass(frozen=True)
class Trade:
    flow: TradeFlow
    session_id: str
    trade_id: str
    price: Decimal
    size: Decimal
    price_text: str
    size_text: str
    raw_side: object
    aggressor: str
    event_ns: object  # int or None (native time, unqualified)
    received_ns: int
    arrival_seq: int

    @property
    @exact
    def notional(self):
        return self.price * self.size

    def payload(self):
        return (self.price_text, self.size_text, self.raw_side, self.event_ns)


def make_trade(flow, record, *, session_id, received_ns, arrival_seq):
    """Normalise one project-layout record (provider decoders are a later, attested step)."""
    if not isinstance(record, dict):
        raise TradeRefusal("RECORD_NOT_OBJECT")
    if not isinstance(session_id, str) or not session_id:
        raise TradeRefusal("SESSION_REQUIRED")
    for v in (received_ns, arrival_seq):
        if type(v) is not int or v < 0:
            raise TradeRefusal("INTEGER_REQUIRED")
    tid = record.get("trade_id")
    if not isinstance(tid, str) or not tid:
        raise TradeRefusal("TRADE_ID_REQUIRED")  # cannot deduplicate: not counted
    if record.get("quote") != flow.quote:
        raise TradeRefusal("QUOTE_MISMATCH")
    if record.get("instrument") != flow.instrument:
        raise TradeRefusal("INSTRUMENT_MISMATCH")
    price, size = _dec(record.get("price")), _dec(record.get("size"))
    ev = record.get("event_ns")
    if ev is not None and (type(ev) is not int or ev < 0):
        raise TradeRefusal("EVENT_TIME_INVALID")
    raw = record.get("side")
    return Trade(
        flow, session_id, tid, price, size, record["price"], record["size"], raw,
        flow.side.aggressor(raw), ev, received_ns, arrival_seq,
    )


class TradeLedger:
    """Accepted trades for one flow with an explicit deduplication domain."""

    def __init__(self, flow):
        self.flow = flow
        self.trades = []
        self._seen = {}
        self.duplicates = 0
        self.conflicts = []
        self.refused = {}
        self.sessions = []  # session ids in order of first trade

    def _key(self, t):
        if self.flow.id_domain == "INSTRUMENT":
            return (t.flow.venue, t.flow.instrument, t.trade_id)
        return (t.flow.venue, t.flow.instrument, t.session_id, t.trade_id)

    def ingest(self, record, *, session_id, received_ns, arrival_seq):
        try:
            t = make_trade(self.flow, record, session_id=session_id,
                           received_ns=received_ns, arrival_seq=arrival_seq)
        except TradeRefusal as e:
            self.refused[str(e)] = self.refused.get(str(e), 0) + 1
            return str(e)
        k = self._key(t)
        if k in self._seen:
            if self._seen[k].payload() == t.payload():
                self.duplicates += 1
                return "DUPLICATE"
            # Same identity, different content: keep the first, keep the evidence.
            self.conflicts.append({"trade_id": t.trade_id, "session_id": t.session_id})
            return "CONFLICT"
        self._seen[k] = t
        self.trades.append(t)
        if not self.sessions or self.sessions[-1] != t.session_id:
            self.sessions.append(t.session_id)
        return "ACCEPTED"


def merge_coverage(spans):
    """Union of half-open [start, end) spans, sorted; rejects malformed spans."""
    out = []
    for a, b in sorted(spans):
        if type(a) is not int or type(b) is not int or a >= b:
            raise ValueError("COVERAGE_SPAN_INVALID")
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _covered(spans, lo, hi):
    return any(a <= lo and hi <= b for a, b in spans)


@exact
def build_bars(ledger, *, anchor_ns, bar_ns, as_of_ns, coverage):
    """Complete bars in [anchor, as_of) by native event time; trades visible only
    if received at or before ``as_of_ns`` (no future data in a replay)."""
    for v in (anchor_ns, bar_ns, as_of_ns):
        if type(v) is not int or v < 0:
            raise ValueError("INTEGER_NS_REQUIRED")
    if bar_ns <= 0 or as_of_ns < anchor_ns:
        raise ValueError("BAR_GEOMETRY_INVALID")
    spans = merge_coverage(coverage)
    n = (as_of_ns - anchor_ns) // bar_ns
    per_bar = [[] for _ in range(n)]
    excluded = {"no_event_time": 0, "future_event_time": 0, "outside_range": 0}
    for t in ledger.trades:
        if t.received_ns > as_of_ns:
            continue
        if t.event_ns is None:
            excluded["no_event_time"] += 1
        elif t.event_ns > t.received_ns:
            excluded["future_event_time"] += 1
        else:
            i = (t.event_ns - anchor_ns) // bar_ns
            if t.event_ns < anchor_ns or i >= n:
                excluded["outside_range"] += 1
            else:
                per_bar[i].append(t)
    bars = []
    seg, cum = -1, None
    prev_ok = False
    for i, ts in enumerate(per_bar):
        lo, hi = anchor_ns + i * bar_ns, anchor_ns + (i + 1) * bar_ns
        bar = {"index": i, "start_ns": str(lo), "end_ns": str(hi)}
        if not _covered(spans, lo, hi):
            bar.update(status="NOT_COVERED", trade_count=None, delta_status="NOT_COVERED",
                       delta_base=None, delta_base_bounds=None,
                       segment=None, cvd_base=None, cvd_base_bounds=None)
            bars.append(bar)
            prev_ok = False
            continue
        sessions = {t.session_id for t in ts}
        broken = ledger.flow.id_domain == "SESSION" and len(sessions) > 1
        ts = sorted(ts, key=lambda t: (t.event_ns, t.arrival_seq))
        vol = {BUY: Decimal(0), SELL: Decimal(0), UNKNOWN: Decimal(0)}
        notional = {BUY: Decimal(0), SELL: Decimal(0), UNKNOWN: Decimal(0)}
        for t in ts:
            vol[t.aggressor] += t.size
            notional[t.aggressor] += t.notional
        bar.update(
            status="OBSERVED" if ts else "OBSERVED_ZERO",
            trade_count=len(ts),
            quote=ledger.flow.quote,
            buy_volume=_text(vol[BUY]), sell_volume=_text(vol[SELL]), unknown_volume=_text(vol[UNKNOWN]),
            buy_notional=_text(notional[BUY]), sell_notional=_text(notional[SELL]),
            unknown_notional=_text(notional[UNKNOWN]),
            open=ts[0].price_text if ts else None, close=ts[-1].price_text if ts else None,
            high=_text(max(t.price for t in ts)) if ts else None,
            low=_text(min(t.price for t in ts)) if ts else None,
        )
        if broken:
            # Session ids are only unique per session: overlapping replays after a
            # reconnect cannot be told from new trades. Keep the break, drop the number.
            bar.update(status="SESSION_BREAK_UNRESOLVED", delta_status="SESSION_BREAK_UNRESOLVED",
                       delta_base=None, delta_base_bounds=None, segment=None, cvd_base=None,
                       cvd_base_bounds=None)
            bars.append(bar)
            prev_ok = False
            continue
        d = vol[BUY] - vol[SELL]
        u = vol[UNKNOWN]
        is_exact = u == 0
        bar["delta_status"] = "EXACT" if is_exact else "PARTIAL_UNKNOWN_SIDE"
        bar["delta_base"] = _text(d) if is_exact else None
        bar["delta_base_bounds"] = [_text(d - u), _text(d + u)]
        if not prev_ok:
            seg += 1
            cum = [Decimal(0), Decimal(0)]
        cum = [cum[0] + d - u, cum[1] + d + u]
        prev_ok = True
        bar["segment"] = seg
        bar["cvd_base_bounds"] = [_text(cum[0]), _text(cum[1])]
        bar["cvd_base"] = _text(cum[0]) if cum[0] == cum[1] else None
        bars.append(bar)
    return {"bars": bars, "excluded": excluded}


@exact
def rolling_delta(bars, bar_ns, windows_ns):
    """Delta over the last W complete bars; NOT_AVAILABLE unless every bar is usable."""
    out = {}
    for w in windows_ns:
        if type(w) is not int or w <= 0 or w % bar_ns:
            raise ValueError("WINDOW_MUST_BE_BAR_MULTIPLE")
        k = w // bar_ns
        key = str(w)
        if k > len(bars):
            out[key] = {"status": "NOT_AVAILABLE", "reason": "WINDOW_BEFORE_ANCHOR"}
            continue
        win = bars[len(bars) - k:]
        bad = [b for b in win if b["status"] not in ("OBSERVED", "OBSERVED_ZERO")]
        if bad:
            out[key] = {"status": "NOT_AVAILABLE", "reason": "COVERAGE_INCOMPLETE_OR_UNRESOLVED"}
            continue
        lo = sum((Decimal(b["delta_base_bounds"][0]) for b in win), Decimal(0))
        hi = sum((Decimal(b["delta_base_bounds"][1]) for b in win), Decimal(0))
        out[key] = {"status": "EXACT" if lo == hi else "PARTIAL_UNKNOWN_SIDE",
                    "delta_base": _text(lo) if lo == hi else None,
                    "delta_base_bounds": [_text(lo), _text(hi)]}
    return out
