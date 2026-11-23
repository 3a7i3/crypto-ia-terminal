"""CH1-02 step 1: Kraken-only replay of a sealed BBO journal into BOOK_STATE / QUALITY_REPORT.

SOURCE ONLY / NOT WIRED. Pure: the caller hands the three sealed files as bytes
(``manifest.json``, ``events.jsonl``, ``frames.bin``); nothing here reads a file,
a clock or the network. Replaying a real corpus is an operator gesture.

What it does, in receipt order and up to an optional receipt bound:
- verifies the seal (hashes, contiguous receipt numbers, monotonic receipt clock,
  per-frame sha256, anchor consistency), exactly like ``bbo_pilot.load``;
- rebuilds the Kraken Spot WS v2 ``book`` with the CRC32 checked on every message
  (logic ported from ``radar_composite/bbo_book.KrakenSource``; a differential test
  pins both to the same book and the same breaks); every other venue is ignored;
- emits one RAW_EVENT per Kraken event, and a BOOK_STATE + QUALITY_REPORT after
  every Kraken event that can change the book or its integrity;
- lists the silences under the liveness policy declared below: a proof received at
  ``p`` attests ``[p, p + 2000)`` ms, so a silence starts when that delay expires
  and cites the last proof; at the receipt bound, the silence that the prefix can
  already see is listed with no end, so nothing after the bound is ever read.

Declared rules (fixed before any real replay, see the CH1-01 contract):
- integrity: a checksum match attests the top ``depth`` levels at that message only;
- freshness of the book: never attested here -> UNKNOWN (``BOOK_FRESHNESS_NOT_ATTESTED``);
- trades: no trade channel is replayed -> UNKNOWN (``TRADE_CHANNEL_NOT_CAPTURED``); a
  Kraken trade frame in the journal is refused rather than ignored;
- native times are kept in their original form, never attested -> UNKNOWN.
Checking form and replaying are not certifying the market.
"""

import hashlib
import json
import re
import zlib
from decimal import Decimal

from . import perception as pc

REPLAY_VERSION = "ch1-02-kraken-replay-0.2.0"
ARTIFACT = "CH1_02_KRAKEN_BOOK_REPLAY"
VENUE = "kraken"
OP_TEXT = 1
CHECKSUM_LEVELS = 10
MS_TO_NS = 1_000_000

# Liveness policy, declared before any real replay. Liveness concerns the connection,
# never the book: it does not make a book fresh and it does not validate one.
# Intervals are half-open in integer milliseconds. ``bbo_book.source_state`` still
# counts the instant p + 2000 itself as alive (``t - alive > L``); this replay does not.
LIVENESS_MAX_GAP_MS = 2_000  # = parameters_primary.liveness_max_ms pre-registered by the BBO pilot
LIVENESS_POLICY = {
    "attesting_events": ["ws_open", "ws_control", "ws_message:valid_json_text"],
    "not_attesting": ["sent", "rest", "checksum_mismatch", "closed_by_pilot", "other"],
    "max_gap_ms": str(LIVENESS_MAX_GAP_MS),
    "time_axis": "t_ms in integer milliseconds (manifest anchor + monotonic receipt delta)",
    "attestation": "a proof received at p attests [p, p + max_gap_ms); the delay expires at p + max_gap_ms",
    "gap": "next proof q with q - p > max_gap_ms: SILENCE_GAP_EXCEEDS_MAX over [p + max_gap_ms, q), citing p and q",
    "disconnect": ("ws_close, ws_error or gave_up at c: SILENCE_UNATTESTED_AFTER_DISCONNECT over [c, next proof), "
                   "after a SILENCE_GAP_EXCEEDS_MAX over [p + max_gap_ms, c) when c - p > max_gap_ms"),
    "no_proof": "before the first proof: SILENCE_UNATTESTED_BEFORE_FIRST_PROOF, with no start",
    "bound": ("at the receipt bound, the open silence, or SILENCE_UNATTESTED_AFTER_LAST_PROOF from p + max_gap_ms, "
              "is listed with no end; no event after the bound is read"),
    "scope": "connection liveness only; book freshness stays UNKNOWN",
}
SILENCE_KEYS = frozenset({"reason", "starts_at_t_ms", "ends_before_t_ms", "last_proof_receipt_seq",
                          "last_proof_t_ms", "opened_by_receipt_seq", "closed_by_receipt_seq"})

_SYMBOL = re.compile(r"[A-Z0-9]{1,16}/[A-Z0-9]{1,16}", re.ASCII)
_PLAIN_DEC = re.compile(r"[0-9]+(\.[0-9]+)?", re.ASCII)
_CORPUS = re.compile(r"[A-Z0-9][A-Z0-9_\-]{0,127}", re.ASCII)


class ReplayRefusal(ValueError):
    """Stable refusal reason code for the whole replay (nothing is produced)."""


class _Num(str):
    """A JSON number kept as its exact literal text (the Kraken checksum is defined on it)."""


def _json_keep_numbers(raw, *, refusal):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ReplayRefusal(refusal + "_DUPLICATE_KEY")
            out[key] = value
        return out

    def no_constant(_):
        raise ReplayRefusal(refusal + "_NONFINITE")

    try:
        return json.loads(raw.decode("utf-8"), parse_float=_Num, parse_int=_Num,
                          parse_constant=no_constant, object_pairs_hook=pairs)
    except ReplayRefusal:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise ReplayRefusal(refusal + "_INVALID_JSON") from None


def _int(value, code):
    if type(value) is _Num and re.fullmatch(r"0|[1-9][0-9]*", value, re.ASCII):
        return int(value)
    raise ReplayRefusal(code)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


# ------------------------------------------------------------------ seal


def load_journal(manifest_bytes, events_bytes, frames_bytes):
    """Verify the sealed journal; return (manifest, events). Any defect refuses the whole journal."""
    for blob in (manifest_bytes, events_bytes, frames_bytes):
        if type(blob) is not bytes:
            raise ReplayRefusal("BYTES_REQUIRED")
    manifest = _json_keep_numbers(manifest_bytes, refusal="MANIFEST")
    sealed = manifest.get("sealed") if isinstance(manifest, dict) else None
    if not isinstance(sealed, dict):
        raise ReplayRefusal("JOURNAL_NOT_SEALED")
    if _sha(events_bytes) != sealed.get("events_sha256"):
        raise ReplayRefusal("EVENTS_HASH_MISMATCH")
    if _sha(frames_bytes) != sealed.get("frames_sha256"):
        raise ReplayRefusal("FRAMES_HASH_MISMATCH")
    anchor = manifest.get("clock_anchor") or {}
    wall0 = _int(anchor.get("wall_ms"), "ANCHOR_INVALID")
    mono0 = _int(anchor.get("mono_ms"), "ANCHOR_INVALID")
    if not events_bytes.endswith(b"\n"):
        raise ReplayRefusal("EVENTS_TRUNCATED")
    events, prev_seq, prev_mono = [], 0, None
    for line in events_bytes.split(b"\n")[:-1]:
        entry = _json_keep_numbers(line, refusal="EVENT")
        if not isinstance(entry, dict):
            raise ReplayRefusal("EVENT_NOT_OBJECT")
        seq = _int(entry.get("seq"), "EVENT_SEQ_INVALID")
        mono = _int(entry.get("recv_mono_ms"), "EVENT_TIME_INVALID")
        wall = _int(entry.get("recv_wall_ms"), "EVENT_TIME_INVALID")
        t_ms = _int(entry.get("t_ms"), "EVENT_TIME_INVALID")
        offset = _int(entry.get("offset"), "EVENT_OFFSET_INVALID")
        size = _int(entry.get("bytes"), "EVENT_OFFSET_INVALID")
        if seq != prev_seq + 1:
            raise ReplayRefusal("EVENT_SEQ_NOT_CONTIGUOUS")
        if prev_mono is not None and mono < prev_mono:
            raise ReplayRefusal("EVENT_RECEIPT_CLOCK_REWIND")
        if t_ms != wall0 + mono - mono0:
            raise ReplayRefusal("EVENT_TIME_INCONSISTENT_WITH_ANCHOR")
        payload = frames_bytes[offset:offset + size]
        if len(payload) != size or _sha(payload) != entry.get("sha256"):
            raise ReplayRefusal("FRAME_HASH_MISMATCH")
        prev_seq, prev_mono = seq, mono
        events.append({"seq": seq, "venue": entry.get("venue"), "kind": entry.get("kind"),
                       "opcode": entry.get("opcode"), "t_ms": t_ms, "wall_ms": wall, "mono_ms": mono,
                       "offset": offset, "bytes": size, "sha256": entry["sha256"], "payload": payload})
    if len(events) != _int(sealed.get("events"), "SEAL_COUNT_INVALID"):
        raise ReplayRefusal("EVENT_COUNT_DIFFERS_FROM_SEAL")
    return manifest, events


def _seal(manifest_bytes, events_bytes, frames_bytes, count):
    return {"manifest_sha256": _sha(manifest_bytes), "events_sha256": _sha(events_bytes),
            "frames_sha256": _sha(frames_bytes), "events_total": str(count)}


def verify_seal(manifest_bytes, events_bytes, frames_bytes):
    """Verify the sealed journal without replaying it; return its seal summary."""
    _manifest, events = load_journal(manifest_bytes, events_bytes, frames_bytes)
    return _seal(manifest_bytes, events_bytes, frames_bytes, len(events))


# ------------------------------------------------------------------ book


def _ck(text):
    return text.replace(".", "").lstrip("0")


def kraken_checksum(asks, bids):
    """CRC32 of the official v2 guide over the top 10 levels, on the literals as received."""
    a = "".join(_ck(p) + _ck(q) for p, q in asks[:CHECKSUM_LEVELS])
    b = "".join(_ck(p) + _ck(q) for p, q in bids[:CHECKSUM_LEVELS])
    return zlib.crc32((a + b).encode("ascii")) & 0xFFFFFFFF


def _level_text(value):
    if type(value) is not _Num or not _PLAIN_DEC.fullmatch(value):
        raise ValueError("LEVEL_NOT_PLAIN_DECIMAL")
    return str(value)


def _canon_dec(text):
    """The contract form of a received literal: same value, no exponent, no trailing zeros."""
    d = Decimal(text).normalize()
    out = format(d, "f")
    return out


class _KrakenBook:
    """State of the Kraken book of one symbol (port of ``bbo_book.KrakenSource``)."""

    def __init__(self, symbol, depth):
        self.symbol, self.depth = symbol, depth
        self.bids, self.asks = {}, {}
        self.connected = False
        self.unavailable = False
        self.continuity = "NOT_INITIALIZED"
        self.lost_reason = None
        self.break_seq = None
        self.resync_engaged = False
        self.snapshot_expected = False
        self.last_book_seq = None
        self.breaks = []
        self.counters = {}

    def count(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1

    def clear(self):
        self.bids.clear()
        self.asks.clear()

    def lose(self, seq, reason):
        if self.continuity == "CONTINUITY_LOST" and self.breaks and self.breaks[-1]["resolved_receipt_seq"] is None:
            self.count("break_while_lost")
        else:
            self.breaks.append({"receipt_seq": str(seq), "reason": reason, "resolved_receipt_seq": None})
        self.continuity, self.lost_reason, self.break_seq = "CONTINUITY_LOST", reason, seq
        self.resync_engaged = False
        self.clear()

    def synced(self, seq):
        self.continuity, self.lost_reason, self.break_seq = "SYNCED", None, None
        self.resync_engaged = self.snapshot_expected = False
        for b in self.breaks:
            if b["resolved_receipt_seq"] is None:
                b["resolved_receipt_seq"] = str(seq)

    def disconnect(self, seq, reason):
        self.connected = False
        if self.continuity != "NOT_INITIALIZED" or self.bids or self.asks:
            self.lose(seq, reason)
        self.snapshot_expected = False

    def sorted_asks(self):
        return sorted(self.asks.items())

    def sorted_bids(self):
        return sorted(self.bids.items(), reverse=True)

    def set_level(self, side, price_text, qty_text):
        price, qty = Decimal(price_text), Decimal(qty_text)
        if price <= 0:
            raise ValueError("PRICE_NOT_POSITIVE")
        book = self.bids if side == "bid" else self.asks
        if qty == 0:
            book.pop(price, None)
        else:
            book[price] = (qty, price_text, qty_text)

    def truncate(self):
        for price, _ in self.sorted_asks()[self.depth:]:
            del self.asks[price]
        for price, _ in self.sorted_bids()[self.depth:]:
            del self.bids[price]

    def apply_book(self, seq, kind, item):
        """One ``data`` item of a book message. Returns True when the book state was touched."""
        if not isinstance(item, dict) or item.get("symbol") != self.symbol:
            self.count("foreign_item")
            return False
        if kind == "update" and self.continuity != "SYNCED":
            self.count("update_ignored_not_synced")
            return False
        try:
            if kind == "snapshot":
                self.clear()
            for side, key in (("bid", "bids"), ("ask", "asks")):
                levels = item.get(key) or []
                if not isinstance(levels, list):
                    raise ValueError("LEVELS_NOT_LIST")
                for level in levels:
                    self.set_level(side, _level_text(level["price"]), _level_text(level["qty"]))
            self.truncate()
            expected = _int(item["checksum"], "x")
        except (ValueError, KeyError, TypeError, ReplayRefusal):
            self.count("book_invalid_message")
            self.lose(seq, "MESSAGE_INVALID")
            return True
        asks = [(v[1], v[2]) for _, v in self.sorted_asks()]
        bids = [(v[1], v[2]) for _, v in self.sorted_bids()]
        self.count(kind + "s")
        if kraken_checksum(asks, bids) != expected:
            self.count("checksum_mismatch")
            self.lose(seq, "CHECKSUM_MISMATCH")
            return True
        self.count("checksum_ok")
        self.last_book_seq = seq
        if kind == "snapshot":
            self.synced(seq)
        return True

    def native_state(self):
        """BBO native code at the last event, without any time-based class.

        VALID here means: synced, both sides present, not crossed, checksum matched at
        ``last_book_seq``. UNCHANGED_VERIFIED / FRESHNESS_UNKNOWN need an instant and a
        liveness reading: they belong to the availability step, not to this replay.
        """
        if self.unavailable or (not self.connected and self.continuity != "CONTINUITY_LOST"):
            return "SOURCE_UNAVAILABLE"
        if self.continuity == "CONTINUITY_LOST":
            return "CONTINUITY_LOST"
        if self.continuity != "SYNCED":
            return "NOT_INITIALIZED"
        if not self.bids or not self.asks or min(self.asks) <= max(self.bids):
            return "BOOK_INVALID"
        return "VALID"


# ------------------------------------------------------------------ liveness


class _Liveness:
    """Silences of the Kraken connection under LIVENESS_POLICY, from received events only.

    Exactly one of ``open`` (an unattested interval still running) and ``last_proof``
    (receipt_seq, t_ms) is set at any time.
    """

    def __init__(self):
        self.silences = []
        self.last_proof = None
        self.open = self._entry("SILENCE_UNATTESTED_BEFORE_FIRST_PROOF", None)

    def _entry(self, reason, starts_at, opened_by=None):
        proof = self.last_proof
        return {"reason": reason, "starts_at_t_ms": None if starts_at is None else str(starts_at),
                "ends_before_t_ms": None,
                "last_proof_receipt_seq": None if proof is None else str(proof[0]),
                "last_proof_t_ms": None if proof is None else str(proof[1]),
                "opened_by_receipt_seq": None if opened_by is None else str(opened_by),
                "closed_by_receipt_seq": None}

    def _close(self, entry, ev):
        entry["ends_before_t_ms"], entry["closed_by_receipt_seq"] = str(ev["t_ms"]), str(ev["seq"])
        self.silences.append(entry)

    def _gap_until(self, ev):
        expiry = self.last_proof[1] + LIVENESS_MAX_GAP_MS
        if ev["t_ms"] > expiry:
            self._close(self._entry("SILENCE_GAP_EXCEEDS_MAX", expiry), ev)

    def proof(self, ev):
        if self.open is not None:
            self._close(self.open, ev)
            self.open = None
        else:
            self._gap_until(ev)
        self.last_proof = (ev["seq"], ev["t_ms"])

    def disconnect(self, ev):
        if self.open is None:
            self._gap_until(ev)
            self.open = self._entry("SILENCE_UNATTESTED_AFTER_DISCONNECT", ev["t_ms"], ev["seq"])
            self.last_proof = None

    def at_bound(self):
        """Every silence the prefix can see; the last one has no end."""
        if self.open is not None:
            return self.silences + [self.open]
        expiry = self.last_proof[1] + LIVENESS_MAX_GAP_MS
        return self.silences + [self._entry("SILENCE_UNATTESTED_AFTER_LAST_PROOF", expiry)]


# ------------------------------------------------------------------ replay


def _identity(manifest):
    try:
        kraken = manifest["ws"]["kraken"]
        symbol, depth = kraken["symbol"], _int(kraken["depth"], "DEPTH_INVALID")
        instrument = manifest["instrument"]
        base, quote = instrument["base_asset_id"], instrument["quote_asset_id"]
        market_type = manifest["market_type"]
    except (KeyError, TypeError):
        raise ReplayRefusal("MANIFEST_IDENTITY_MISSING") from None
    if type(symbol) is not str or not _SYMBOL.fullmatch(symbol) or not 0 < depth <= CHECKSUM_LEVELS:
        raise ReplayRefusal("MANIFEST_IDENTITY_INVALID")
    for value in (base, quote, market_type):
        if type(value) is not str or not value:
            raise ReplayRefusal("MANIFEST_IDENTITY_INVALID")
    return {"venue": VENUE, "market_type": market_type, "native_symbol": symbol, "base": base,
            "quote": quote, "subscribed_depth": str(depth)}


def _raw_event(session_id, ident, ev, channel, native_time):
    rec = {
        "schema_version": pc.SCHEMA_VERSION, "session_id": session_id, "venue": ident["venue"],
        "market_type": ident["market_type"], "native_symbol": ident["native_symbol"],
        "channel": channel, "kind": ev["kind"], "receipt_seq": str(ev["seq"]),
        "receive_utc_ns": str(ev["wall_ms"] * MS_TO_NS), "receive_mono_ns": str(ev["mono_ms"] * MS_TO_NS),
        "native_time": native_time, "native_sequence": None, "offset_bytes": str(ev["offset"]),
        "length_bytes": str(ev["bytes"]), "payload_sha256": ev["sha256"],
    }
    return pc.validate_raw_event(rec)


def _book_state(book, seq, depth):
    native = book.native_state()
    published = native == "VALID"
    rec = {
        "schema_version": pc.SCHEMA_VERSION, "as_of_receipt_seq": str(seq),
        "last_book_receipt_seq": None if book.last_book_seq is None else str(book.last_book_seq),
        "subscribed_depth": depth,
        "bids": [[_canon_dec(v[1]), _canon_dec(v[2])] for _, v in book.sorted_bids()] if published else None,
        "asks": [[_canon_dec(v[1]), _canon_dec(v[2])] for _, v in book.sorted_asks()] if published else None,
        "native_state": native, "native_reason": book.lost_reason,
    }
    return pc.validate_book_state(rec), native


def _quality(book, native, seq, evidence_kind):
    evidence = book.break_seq if native == "CONTINUITY_LOST" else book.last_book_seq
    projected = pc.project_native_state(
        "BBO", native, book.lost_reason,
        evidence_receipt_seq=None if evidence is None else str(evidence),
        resync_engaged=book.resync_engaged, snapshot_expected=book.snapshot_expected,
    )["projections"]
    rec = {
        "schema_version": pc.SCHEMA_VERSION, "as_of_receipt_seq": str(seq), "evidence_kind": evidence_kind,
        "book_integrity": projected["book_integrity"],
        "book_freshness": pc.quality_result("UNKNOWN", "BOOK_FRESHNESS_NOT_ATTESTED"),
        "trade_coverage": pc.quality_result("UNKNOWN", "TRADE_CHANNEL_NOT_CAPTURED"),
        "event_time_quality": pc.quality_result("UNKNOWN", "NATIVE_TIME_NOT_ATTESTED"),
    }
    if native == "SOURCE_UNAVAILABLE":
        rec["book_freshness"] = projected["book_freshness"]
    return pc.validate_quality_report(rec)


def replay(manifest_bytes, events_bytes, frames_bytes, *, corpus_id, evidence_kind, receipt_bound=None):
    """Replay the Kraken book of one sealed journal. Returns ``(result_bytes, seal)``.

    ``result_bytes`` is canonical JSON that depends only on the journal prefix up to
    ``receipt_bound`` (all of it when None): appending events after the bound changes
    the seal, never the result. ``evidence_kind`` is declared by the caller (SYNTHETIC
    or HISTORICAL); a journal whose manifest says SYNTHETIC cannot be declared HISTORICAL.
    """
    if type(corpus_id) is not str or not _CORPUS.fullmatch(corpus_id):
        raise ReplayRefusal("CORPUS_ID_INVALID")
    if evidence_kind not in pc.EVIDENCE_KINDS:
        raise ReplayRefusal("EVIDENCE_KIND_REFUSED")
    manifest, events = load_journal(manifest_bytes, events_bytes, frames_bytes)
    if manifest.get("evidence_kind") == "SYNTHETIC" and evidence_kind != "SYNTHETIC":
        raise ReplayRefusal("SYNTHETIC_JOURNAL_DECLARED_HISTORICAL")
    if receipt_bound is not None and (type(receipt_bound) is not int or not 0 < receipt_bound <= len(events)):
        raise ReplayRefusal("RECEIPT_BOUND_INVALID")
    bound = len(events) if receipt_bound is None else receipt_bound
    prefix = events[:bound]
    ident = _identity(manifest)
    book = _KrakenBook(ident["native_symbol"], int(ident["subscribed_depth"]))

    records, ignored, live = [], {}, _Liveness()

    for ev in prefix:
        if ev["venue"] != VENUE:
            ignored[str(ev["venue"])] = ignored.get(str(ev["venue"]), 0) + 1
            continue
        kind, channel, native_time, touched = ev["kind"], None, None, False
        if kind == "ws_open":
            book.connected = True
            live.proof(ev)
            touched = True
        elif kind in ("ws_close", "ws_error", "gave_up"):
            live.disconnect(ev)
            if kind == "gave_up":
                book.unavailable = True
            book.disconnect(ev["seq"], "GAVE_UP" if kind == "gave_up" else "DISCONNECTED")
            touched = True
        elif kind == "ws_control":
            live.proof(ev)
        elif kind == "sent":
            try:
                doc = _json_keep_numbers(ev["payload"], refusal="SENT")
            except ReplayRefusal:
                doc = None
            if isinstance(doc, dict) and doc.get("method") == "subscribe" and book.connected:
                if book.continuity == "CONTINUITY_LOST":
                    book.resync_engaged, touched = True, True
                elif book.continuity == "NOT_INITIALIZED":
                    book.snapshot_expected, touched = True, True
        elif kind == "ws_message":
            if ev["opcode"] != _Num(str(OP_TEXT)) and ev["opcode"] != OP_TEXT:
                book.count("unexpected_opcode")
            else:
                try:
                    doc = _json_keep_numbers(ev["payload"], refusal="FRAME")
                except ReplayRefusal:
                    doc = None
                    book.count("text_invalid")
                if doc is not None:
                    live.proof(ev)
                if isinstance(doc, dict):
                    channel = doc.get("channel") if type(doc.get("channel")) is str else None
                    if channel == "trade":
                        raise ReplayRefusal("TRADE_CHANNEL_OUT_OF_SCOPE")
                    if channel == "book" and doc.get("type") in ("snapshot", "update"):
                        data = doc.get("data") or []
                        if len(data) == 1 and isinstance(data[0], dict) and type(data[0].get("timestamp")) is str:
                            native_time = data[0]["timestamp"]
                        for item in data if isinstance(data, list) else []:
                            touched = book.apply_book(ev["seq"], doc["type"], item) or touched
                    elif channel == "heartbeat":
                        book.count("heartbeat")
                    elif doc.get("method") == "pong":
                        book.count("pong")
                    elif channel == "status":
                        book.count("status")
                    elif doc.get("method") in ("subscribe", "unsubscribe"):
                        book.count("ack_" + ("ok" if doc.get("success") is True else "refused"))
                    else:
                        book.count("text_other")
        else:
            book.count("not_replayed_" + str(kind))
        if channel is not None and (type(channel) is not str or not channel.isprintable() or len(channel) > 64):
            channel = None
        records.append({"type": "RAW_EVENT", "record": _raw_event(corpus_id, ident, ev, channel, native_time)})
        if touched:
            state, native = _book_state(book, ev["seq"], ident["subscribed_depth"])
            records.append({"type": "BOOK_STATE", "record": state})
            records.append({"type": "QUALITY_REPORT", "record": _quality(book, native, ev["seq"], evidence_kind)})

    last = prefix[-1] if prefix else None
    prefix_frames_end = max((e["offset"] + e["bytes"] for e in prefix), default=0)
    result = {
        "artifact": ARTIFACT, "replay_version": REPLAY_VERSION, "schema_version": pc.SCHEMA_VERSION,
        "corpus_id": corpus_id, "evidence_kind": evidence_kind,
        "session": {**ident, "session_id": corpus_id, "receipt_time_resolution_ns": str(MS_TO_NS),
                    "ordering": "receipt_seq, then item index; native time never orders the journal"},
        "journal_prefix": {
            "receipt_bound": str(bound), "last_t_ms": None if last is None else str(last["t_ms"]),
            "events_prefix_sha256": _sha(b"".join(_line(ev) for ev in prefix)),
            "frames_prefix_sha256": _sha(b"".join(ev["payload"] for ev in prefix)),
            "frames_prefix_end_offset": str(prefix_frames_end),
        },
        "liveness_policy": LIVENESS_POLICY,
        "silences": live.at_bound(),
        "breaks": book.breaks,
        "counters": {k: str(v) for k, v in sorted(book.counters.items())},
        "ignored_events_by_venue": {k: str(v) for k, v in sorted(ignored.items())},
        "records": records,
    }
    return canonical(result), _seal(manifest_bytes, events_bytes, frames_bytes, len(events))


def _line(ev):
    """Stable fingerprint of one verified event, independent of later events."""
    return canonical({k: (str(v) if not isinstance(v, (str, type(None))) else v)
                      for k, v in ev.items() if k != "payload"}) + b"\n"
