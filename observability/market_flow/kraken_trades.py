"""MEO-01: Kraken Spot WS v2 ``trade`` channel (BTC/USDT) into the market_flow trade core.

SOURCE ONLY / SYNTHETIC FIXTURES. Pure functions: no clock, transport, file,
float or runtime wiring (package rules). Bytes come in, plain data comes out.

What this module adds, and only that (``trades.py`` is reused unchanged):
- a strict JSON reader that keeps every JSON number as its exact literal text;
- a decoder of ``trade`` frames into the project record layout of
  ``trades.make_trade`` (identity, literal price/size, raw side, native time);
- the documented Kraken TAKER side convention, tied to a hashed excerpt;
- two distinct notions, never merged:
  * transport continuity (receipt axis): the subscription was alive;
  * effective trade coverage (native axis): proven only by contiguous trade ids;
- the replay of a sealed capture journal and the REST cross-check comparison.

Unknown stays unknown: an uncovered bar is NOT_COVERED (never zero), a missing
proof leaves the coverage UNKNOWN, and no admission verdict is produced here.
"""

from decimal import Decimal
import hashlib
import json
import re

from . import trades as tr
from .exact import exact
from .l2 import L2Refusal, parse_rfc3339_ns

SCHEMA = "meo-01-trades-report/1"
NORMALIZED_SCHEMA_VERSION = "1"  # CH1-01 NORMALIZED_TRADE record version
VENUE = "kraken"
WS_SYMBOL = "BTC/USDT"
BASE, QUOTE = "BTC", "USDT"
REST_PAIR_KEY = "XBTUSDT"
SIDE_BASIS = "TAKER"

NS = 1_000_000_000
BAR_NS = 60 * NS
WINDOW_NS = 300 * NS
SILENCE_BUDGET_NS = 2 * NS  # one received frame attests [r, r + 2 s) (CH1 silence rule)
LIST_CAP = 50  # bounded lists in the report; totals always kept

EVIDENCE_EXCERPT_SHA256 = "a99cb899e26aef22a336452f6441037a668b55a3deccabea323b0a892110cb03"
EVIDENCE_REF = ("docs/contracts/MEO_01_TRADES_CAPTURE.md#KRAKEN-EXCERPT read_utc=2026-11-28 sha256="
                + EVIDENCE_EXCERPT_SHA256)

# D2: documented and hashed TAKER convention. Any other raw value stays UNKNOWN.
KRAKEN_TAKER_CONVENTION = tr.SideConvention(
    mapping=(("buy", tr.BUY), ("sell", tr.SELL)), attested=True, evidence_ref=EVIDENCE_REF,
)
# D3: trade ids are unique per book, so the deduplication domain is the instrument.
KRAKEN_BTC_USDT_FLOW = tr.TradeFlow(VENUE, WS_SYMBOL, BASE, QUOTE, "SPOT", "INSTRUMENT",
                                    KRAKEN_TAKER_CONVENTION)

ITEM_KEYS = frozenset(("symbol", "side", "price", "qty", "ord_type", "trade_id", "timestamp"))
_ID = re.compile(r"(0|[1-9][0-9]{0,19})", re.ASCII)
_DIGITS = re.compile(r"[0-9]{1,30}", re.ASCII)
_REST_TIME = re.compile(r"[0-9]{1,12}(\.[0-9]{1,9})?", re.ASCII)
_HEX = re.compile(r"[0-9a-f]{64}", re.ASCII)
OP_TEXT = 1


class JournalRefusal(ValueError):
    """The sealed journal cannot be trusted; the message is a stable code."""


# --------------------------------------------------------------------------- strict JSON

class Literal(str):
    """A JSON number kept as its exact literal text (pattern of ``bbo_book.Num``)."""


def literal_json(raw):
    """Strict UTF-8 JSON: duplicate keys and non-finite constants refused, numbers kept as text."""
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("BYTES_REQUIRED")

    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("DUPLICATE_KEY")
            out[k] = v
        return out

    def bad_constant(name):
        raise ValueError("NON_FINITE_CONSTANT")

    return json.loads(bytes(raw).decode("utf-8"), object_pairs_hook=pairs,
                      parse_float=Literal, parse_int=Literal, parse_constant=bad_constant)


# --------------------------------------------------------------------------- frames

def classify_frame(payload):
    """Kind of one Kraken WS v2 text frame. Never raises; a bad frame is a kind."""
    try:
        doc = literal_json(payload)
    except (ValueError, RecursionError):
        return {"kind": "malformed", "reason": "JSON_REFUSED"}
    if not isinstance(doc, dict):
        return {"kind": "malformed", "reason": "NOT_OBJECT"}
    channel, method = doc.get("channel"), doc.get("method")
    if channel == "heartbeat" and set(doc) == {"channel"}:
        return {"kind": "heartbeat"}
    if channel == "status":
        return {"kind": "status"}
    if method == "pong":
        return {"kind": "pong"}
    if method == "subscribe":
        res = doc.get("result") if isinstance(doc.get("result"), dict) else {}
        sym = res.get("symbol")
        return {"kind": "subscribe_ack", "success": doc.get("success") is True,
                "channel": res.get("channel") if isinstance(res.get("channel"), str) else None,
                "symbol": sym if isinstance(sym, str) else None,
                "snapshot": res.get("snapshot") is True}
    if channel == "trade":
        if set(doc) != {"channel", "type", "data"} or doc["type"] not in ("snapshot", "update") \
                or not isinstance(doc["data"], list):
            return {"kind": "malformed", "reason": "TRADE_ENVELOPE_REFUSED"}
        return {"kind": "trade", "type": doc["type"], "items": doc["data"]}
    if doc.get("error") is not None or doc.get("success") is False:
        return {"kind": "provider_error"}
    return {"kind": "unknown"}


def decode_item(item):
    """One trade object -> (record for ``trades.make_trade``, None) or (None, refusal code).

    Price and quantity keep their literal text: an exponent such as ``1e-05`` is
    passed on and refused by ``trades.make_trade`` (DECIMAL_TEXT_REFUSED), never
    converted. An unreadable native time becomes ``event_ns=None`` (counted).
    """
    if not isinstance(item, dict):
        return None, "ITEM_NOT_OBJECT"
    if set(item) != ITEM_KEYS:
        return None, "ITEM_KEYS_REFUSED"
    tid = item["trade_id"]
    if not isinstance(tid, Literal) or not _ID.fullmatch(tid):
        return None, "TRADE_ID_INVALID"
    if not isinstance(item["price"], Literal) or not isinstance(item["qty"], Literal):
        return None, "NUMBER_REQUIRED"
    sym = item["symbol"]
    if not isinstance(sym, str) or isinstance(sym, Literal) or sym.count("/") != 1:
        return None, "SYMBOL_INVALID"
    try:
        event_ns = parse_rfc3339_ns(item["timestamp"])
    except L2Refusal:
        event_ns = None
    return {
        "trade_id": str(tid), "instrument": sym, "quote": sym.split("/", 1)[1],
        "price": str(item["price"]), "size": str(item["qty"]),
        "side": str(item["side"]) if isinstance(item["side"], str) else item["side"],
        "event_ns": event_ns,
    }, None


# --------------------------------------------------------------------------- journal

def verify_journal(manifest, log_bytes, frame_bytes):
    """Check a sealed capture and return its events (each with its ``payload`` bytes).

    Refuses: unsealed manifest, hash mismatch, non-contiguous sequence numbers,
    offsets that do not tile ``frames.bin`` exactly, or a payload whose SHA-256
    differs from its event. Form only: a valid journal is not a true market.
    """
    sealed = manifest.get("sealed") if isinstance(manifest, dict) else None
    if not isinstance(sealed, dict):
        raise JournalRefusal("NOT_SEALED")
    if hashlib.sha256(log_bytes).hexdigest() != sealed.get("events_sha256"):
        raise JournalRefusal("EVENTS_SHA256_MISMATCH")
    if hashlib.sha256(frame_bytes).hexdigest() != sealed.get("frames_sha256"):
        raise JournalRefusal("FRAMES_SHA256_MISMATCH")
    events, offset = [], 0
    for i, line in enumerate(log_bytes.splitlines()):
        try:
            ev = json.loads(line)
        except ValueError:
            raise JournalRefusal("EVENT_LINE_MALFORMED") from None
        if not isinstance(ev, dict) or ev.get("seq") != i + 1:
            raise JournalRefusal("SEQUENCE_NOT_CONTIGUOUS")
        size = ev.get("bytes")
        if ev.get("offset") != offset or type(size) is not int or size < 0:
            raise JournalRefusal("OFFSETS_NOT_CONTIGUOUS")
        payload = frame_bytes[offset:offset + size]
        if len(payload) != size or hashlib.sha256(payload).hexdigest() != ev.get("sha256"):
            raise JournalRefusal("PAYLOAD_SHA256_MISMATCH")
        for k in ("recv_wall_ns", "recv_mono_ns"):
            if type(ev.get(k)) is not int or ev[k] < 0:
                raise JournalRefusal("RECEIPT_NS_REQUIRED")
        offset += size
        events.append({**ev, "payload": payload})
    if offset != len(frame_bytes):
        raise JournalRefusal("FRAMES_NOT_FULLY_REFERENCED")
    if len(events) != sealed.get("events"):
        raise JournalRefusal("EVENT_COUNT_MISMATCH")
    return events


def transport_spans(start_ns, live_ns, end_ns, *, budget_ns=SILENCE_BUDGET_NS):
    """Receipt-axis continuity: [start, ...) extended by each frame's [r, r + budget), cut at end."""
    if start_ns is None:
        return []
    spans = tr.merge_coverage([(start_ns, start_ns + budget_ns)]
                              + [(r, r + budget_ns) for r in live_ns if r >= start_ns])
    out = []
    for a, b in spans:
        b = min(b, end_ns)
        if a < b:
            out.append([a, b])
    return out


def trade_coverage(trades, conflict_ids):
    """Native-axis coverage proven by contiguous trade ids (and nothing else).

    ``trades`` are the accepted trades that ``build_bars`` would count. A run of
    ids A..Z (+1 each, native time never decreasing) covers [t(A) + 1, t(Z)):
    a trade sharing t(A) or t(Z) could lie outside the run, so both ends are
    open. Gaps, conflicts, and time inversions cut a run; none is filled.
    """
    ordered = sorted((int(t.trade_id), t.event_ns) for t in trades if t.trade_id not in conflict_ids)
    runs, gaps, inversions = [], [], 0
    for tid, ev in ordered:
        if runs and tid == runs[-1][-1][0] + 1 and ev >= runs[-1][-1][1]:
            runs[-1].append((tid, ev))
            continue
        if runs:
            last_id, last_ev = runs[-1][-1]
            if tid == last_id + 1:
                inversions += 1
            elif tid > last_id + 1:
                gaps.append({"after_id": str(last_id), "before_id": str(tid), "missing": tid - last_id - 1})
        runs.append([(tid, ev)])
    spans = []
    for run in runs:
        a, b = run[0][1] + 1, run[-1][1]
        if len(run) >= 2 and a < b:
            spans.append([a, b])
    return {
        "spans": spans,
        "runs": len(runs),
        "longest_run": max((len(r) for r in runs), default=0),
        "id_gaps": gaps,
        "time_inversions": inversions,
        "first_id": str(ordered[0][0]) if ordered else None,
        "last_id": str(ordered[-1][0]) if ordered else None,
    }


# --------------------------------------------------------------------------- REST cross-check

def decode_rest_trades(payload):
    """``GET /0/public/Trades`` body -> ({id: row}, last). Strict; raises ValueError(code)."""
    doc = literal_json(payload)
    if not isinstance(doc, dict) or set(doc) != {"error", "result"} or doc["error"] != []:
        raise ValueError("REST_ENVELOPE_REFUSED")
    res = doc["result"]
    if not isinstance(res, dict) or set(res) != {REST_PAIR_KEY, "last"}:
        raise ValueError("REST_PAIR_KEY_REFUSED")
    last = res["last"]
    if not isinstance(last, str) or not _DIGITS.fullmatch(last):
        raise ValueError("REST_LAST_REFUSED")
    rows = {}
    for row in res[REST_PAIR_KEY]:
        if not isinstance(row, list) or len(row) != 7:
            raise ValueError("REST_ROW_REFUSED")
        price, qty, when, side, _type, _misc, tid = row
        if not (isinstance(price, str) and isinstance(qty, str) and isinstance(when, Literal)
                and _REST_TIME.fullmatch(when) and side in ("b", "s")
                and isinstance(tid, Literal) and _ID.fullmatch(tid)):
            raise ValueError("REST_ROW_REFUSED")
        rows[str(tid)] = {"price": str(price), "qty": str(qty), "side": "buy" if side == "b" else "sell",
                          "time_ns": _seconds_to_ns(str(when)), "time_text": str(when)}
    return rows, last


@exact
def _seconds_to_ns(text):
    return int(Decimal(text) * NS)


@exact
def compare_with_rest(ws_trades, rest_rows, start_ns, end_ns):
    """Compare WS and REST rows of one native window [start, end). Lists are bounded."""
    if not rest_rows:
        return {"status": "NOT_AVAILABLE", "reason": "NO_REST_ROWS"}
    times = [r["time_ns"] for r in rest_rows.values()]
    if min(times) >= start_ns or max(times) < end_ns:
        # The fetched REST range does not enclose the window: no conclusion.
        return {"status": "UNKNOWN", "reason": "REST_RANGE_DOES_NOT_ENCLOSE_WINDOW",
                "rest_first_time_ns": str(min(times)), "rest_last_time_ns": str(max(times))}
    ws_by_id = {t.trade_id: t for t in ws_trades}
    ws_in = {i for i, t in ws_by_id.items() if start_ns <= t.event_ns < end_ns}
    rest_in = {i for i, r in rest_rows.items() if start_ns <= r["time_ns"] < end_ns}
    out = {"matched": 0, "content_mismatch": [], "missing_in_ws": [], "missing_in_rest": [],
           "window_boundary_only": [], "side_agreement": 0, "max_abs_time_diff_ns": None}
    max_diff = None
    for i in sorted(ws_in | rest_in, key=int):
        w, r = ws_by_id.get(i), rest_rows.get(i)
        if w is None:
            out["missing_in_ws"].append(i)
            continue
        if r is None:
            out["missing_in_rest"].append(i)
            continue
        if (i in ws_in) != (i in rest_in):
            out["window_boundary_only"].append(i)  # REST time has a coarser resolution
        same = (Decimal(w.price_text) == Decimal(r["price"]) and Decimal(w.size_text) == Decimal(r["qty"])
                and w.raw_side == r["side"])
        if w.raw_side == r["side"]:
            out["side_agreement"] += 1
        if same:
            out["matched"] += 1
        else:
            out["content_mismatch"].append(i)
        d = abs(w.event_ns - r["time_ns"])
        max_diff = d if max_diff is None or d > max_diff else max_diff
    out["max_abs_time_diff_ns"] = None if max_diff is None else str(max_diff)
    bad = len(out["content_mismatch"]) + len(out["missing_in_ws"]) + len(out["missing_in_rest"])
    out["status"] = "MATCH" if bad == 0 else "MISMATCH"
    out["compared_ids"] = len(ws_in | rest_in)
    for k in ("content_mismatch", "missing_in_ws", "missing_in_rest", "window_boundary_only"):
        out[k + "_count"] = len(out[k])
        out[k] = out[k][:LIST_CAP]
    return out


# --------------------------------------------------------------------------- replay

def _bar_covered(bar):
    return bar["status"] in ("OBSERVED", "OBSERVED_ZERO")


@exact
def replay_journal(manifest, events, *, as_of_ns=None):
    """Sealed capture -> MEO-01 report (plain data, deterministic for the same inputs)."""
    flow = KRAKEN_BTC_USDT_FLOW
    if as_of_ns is None:
        as_of_ns = max((e["recv_wall_ns"] for e in events), default=0)
    if type(as_of_ns) is not int or as_of_ns < 0:
        raise ValueError("AS_OF_INTEGER_REQUIRED")
    ledger = tr.TradeLedger(flow)
    frames = {}
    decoder_refusals = {}
    sessions, ack, ack_refused, after = 0, None, 0, 0
    start_ns = end_ns = None
    live = []
    frame_order_inversions = 0
    symbol_mismatch = 0
    exponent_literals = 0
    origin = {}  # trade_id -> (receipt seq, item index, frame type) of the accepted trade
    rest_rows, rest_last, rest_errors = {}, None, {}
    arrival = 0
    for ev in events:
        r = ev["recv_wall_ns"]
        if r > as_of_ns:
            after += 1
            continue
        kind = ev.get("kind")
        if ev.get("venue") == "kraken" and kind == "ws_open":
            sessions += 1
        if ev.get("venue") == "kraken" and kind == "rest" and ev.get("endpoint") == "trades":
            if ev.get("status") != 200:
                rest_errors["HTTP_OR_TRANSPORT"] = rest_errors.get("HTTP_OR_TRANSPORT", 0) + 1
                continue
            try:
                rows, last = decode_rest_trades(ev["payload"])
            except (ValueError, RecursionError) as exc:
                code = str(exc) if str(exc).isupper() else "REST_BODY_REFUSED"
                rest_errors[code] = rest_errors.get(code, 0) + 1
                continue
            rest_rows.update(rows)
            rest_last = last
            continue
        if ev.get("venue") == "kraken" and kind in ("ws_close", "ws_error", "closed_by_pilot") \
                or (ev.get("venue") == "pilot" and kind == "stop"):
            if start_ns is not None:
                end_ns = r if end_ns is None else min(end_ns, r)
            continue
        if ev.get("venue") != "kraken" or kind not in ("ws_message", "ws_control"):
            continue
        if start_ns is not None and end_ns is None:
            live.append(r)
        if kind != "ws_message" or ev.get("opcode") != OP_TEXT:
            frames["non_text"] = frames.get("non_text", 0) + 1
            continue
        c = classify_frame(ev["payload"])
        key = c["kind"] if c["kind"] != "trade" else "trade_" + c["type"]
        frames[key] = frames.get(key, 0) + 1
        if c["kind"] == "subscribe_ack":
            if c["success"] and c["channel"] == "trade" and c["symbol"] == WS_SYMBOL and start_ns is None:
                ack, start_ns = c, r
            elif not c["success"]:
                ack_refused += 1
            elif c["symbol"] != WS_SYMBOL:
                symbol_mismatch += 1
            continue
        if c["kind"] != "trade":
            continue
        prev_id = None
        for idx, item in enumerate(c["items"]):
            rec, why = decode_item(item)
            if why:
                decoder_refusals[why] = decoder_refusals.get(why, 0) + 1
                continue
            if rec["instrument"] != WS_SYMBOL:
                symbol_mismatch += 1
            if "e" in rec["price"].lower() or "e" in rec["size"].lower():
                exponent_literals += 1
            tid = int(rec["trade_id"])
            if prev_id is not None and tid <= prev_id:
                frame_order_inversions += 1
            prev_id = tid
            arrival += 1
            status = ledger.ingest(rec, session_id="ws-%d" % max(sessions, 1), received_ns=r,
                                   arrival_seq=arrival)
            if status == "ACCEPTED":
                origin[rec["trade_id"]] = (ev["seq"], idx, c["type"])
    transport_end = as_of_ns if end_ns is None else min(end_ns, as_of_ns)
    t_spans = transport_spans(start_ns, live, transport_end)
    conflict_ids = {x["trade_id"] for x in ledger.conflicts}
    counted = [t for t in ledger.trades
               if t.received_ns <= as_of_ns and t.event_ns is not None and t.event_ns <= t.received_ns]
    cov = trade_coverage(counted, conflict_ids)
    windows, built = [], {"bars": [], "excluded": {"no_event_time": 0, "future_event_time": 0,
                                                   "outside_range": 0}}
    if counted:
        anchor = min(t.event_ns for t in counted) // WINDOW_NS * WINDOW_NS
        if as_of_ns >= anchor:
            built = tr.build_bars(ledger, anchor_ns=anchor, bar_ns=BAR_NS, as_of_ns=as_of_ns,
                                  coverage=[tuple(s) for s in cov["spans"]])
        per = WINDOW_NS // BAR_NS
        for w in range(len(built["bars"]) // per):
            bars = built["bars"][w * per:(w + 1) * per]
            lo, hi = anchor + w * WINDOW_NS, anchor + (w + 1) * WINDOW_NS
            windows.append(_window(bars, lo, hi, counted, t_spans))
    # Exit window: fully covered by contiguous ids AND observed live, i.e. starting at or after the
    # subscription and inside one transport-continuity span. Snapshot-only windows stay reported.
    exit_window = next((w for w in windows if w["status"] == "COVERED" and start_ns is not None
                        and int(w["start_ns"]) >= start_ns and w["transport_continuous_receipt_axis"]), None)
    cross = None
    if exit_window is not None:
        cross = compare_with_rest(counted, rest_rows, int(exit_window["start_ns"]),
                                  int(exit_window["end_ns"]))
    hyp = _hypotheses(ack, ledger, decoder_refusals, symbol_mismatch, exponent_literals,
                      frame_order_inversions, cov, counted, rest_rows, cross)
    normalized = []
    if exit_window is not None:
        lo, hi = int(exit_window["start_ns"]), int(exit_window["end_ns"])
        for t in sorted((t for t in counted if lo <= t.event_ns < hi), key=lambda t: int(t.trade_id)):
            seq, idx, _ = origin[t.trade_id]
            side_known = t.aggressor in (tr.BUY, tr.SELL)
            normalized.append({
                "schema_version": NORMALIZED_SCHEMA_VERSION, "receipt_seq": str(seq), "item_index": str(idx),
                "trade_id": t.trade_id, "price": t.price_text, "quantity": t.size_text,
                "aggressor_side": t.aggressor, "side_basis": SIDE_BASIS if side_known else "UNKNOWN",
            })
    sealed = manifest.get("sealed") or {}
    pre = manifest.get("preflight") or {}
    end_clock = manifest.get("clock_end") or {}
    code = manifest.get("code") or {}
    report = {
        "schema": SCHEMA,
        "evidence_kind": manifest.get("evidence_kind"),
        "synthetic": manifest.get("evidence_kind") != "OBSERVATION",
        "source": {"events_sha256": sealed.get("events_sha256"), "frames_sha256": sealed.get("frames_sha256"),
                   "events": sealed.get("events"), "capture_code_digest": code.get("digest"),
                   "capture_status": manifest.get("status"), "capture_stop_code": manifest.get("stop_code")},
        "flow": {"venue": flow.venue, "instrument": flow.instrument, "base": flow.base, "quote": flow.quote,
                 "market_kind": flow.market_kind, "id_domain": flow.id_domain,
                 "side_convention": {"mapping": [list(m) for m in flow.side.mapping], "basis": SIDE_BASIS,
                                     "attested": flow.side.attested, "evidence_ref": flow.side.evidence_ref}},
        "time_bases": {
            "bars_axis": "NATIVE_TIMESTAMP_UNQUALIFIED",
            "receipt_axis": "HOST_UTC_RECEIPT_NS",
            "receipt_clock_check": {"reference": "KRAKEN_PUBLIC_TIME_1S",
                                    "start_offset_ms": _int_or_none(pre.get("kraken_clock_offset_ms")),
                                    "end_offset_ms": _int_or_none(end_clock.get("kraken_offset_ms")),
                                    "tolerance_ms": _int_or_none(manifest.get("clock_tolerance_ms"))},
            "receipt_minus_native_ns": _latency(counted),
        },
        "as_of_receipt_ns": str(as_of_ns),
        "events_after_as_of_not_read": after,
        "frames": dict(sorted(frames.items())),
        "ws_sessions": sessions,
        "subscription": {"acknowledged": ack is not None, "refused": ack_refused,
                         "snapshot": bool(ack and ack["snapshot"]),
                         "acknowledged_receipt_ns": None if start_ns is None else str(start_ns)},
        "decoder_refusals": dict(sorted(decoder_refusals.items())),
        "ledger": {"accepted": len(ledger.trades), "duplicates": ledger.duplicates,
                   "conflicts": ledger.conflicts[:LIST_CAP], "conflicts_count": len(ledger.conflicts),
                   "refused": dict(sorted(ledger.refused.items())),
                   "counted_in_bars": len(counted), "excluded": built["excluded"]},
        "transport_continuity": {
            "axis": "RECEIPT", "silence_budget_ns": str(SILENCE_BUDGET_NS),
            "spans_ns": [[str(a), str(b)] for a, b in t_spans],
            "ended_by": None if end_ns is None else "CLOSE_ERROR_OR_STOP",
            "note": "Transport continuity does not prove that no trade is missing.",
        },
        "trade_coverage": {
            "axis": "NATIVE", "basis": "CONTIGUOUS_TRADE_IDS",
            "state": "COVERED_SPANS" if cov["spans"] else "UNKNOWN",
            "reason": None if cov["spans"] else "NO_CONTIGUOUS_TRADE_ID_RUN",
            "spans_ns": [[str(a), str(b)] for a, b in cov["spans"]],
            "runs": cov["runs"], "longest_run": cov["longest_run"],
            "first_id": cov["first_id"], "last_id": cov["last_id"],
            "id_gaps": cov["id_gaps"][:LIST_CAP], "id_gaps_count": len(cov["id_gaps"]),
            "missing_ids_total": sum(g["missing"] for g in cov["id_gaps"]),
            "time_inversions": cov["time_inversions"],
        },
        "windows": windows,
        "exit_window": None if exit_window is None else {"start_ns": exit_window["start_ns"],
                                                         "end_ns": exit_window["end_ns"]},
        "rest_cross_check": {"rows_fetched": len(rest_rows), "last": rest_last,
                             "errors": dict(sorted(rest_errors.items())), "exit_window": cross},
        "hypotheses": hyp,
        "normalized_trades_exit_window": normalized,
        "limits": [
            "No admission verdict (MEO-02) and no scientific reading (MEO-03).",
            "Native times are unqualified; receipt times are host UTC bounded only by the clock check.",
            "Coverage is proven by contiguous trade ids under H2/H5; the tail after the last trade is never covered.",
            "Form and consistency only: a valid journal does not certify the market.",
        ],
    }
    return report


def _int_or_none(v):
    return v if type(v) is int else None


def _latency(counted):
    if not counted:
        return {"min": None, "max": None}
    d = [t.received_ns - t.event_ns for t in counted]
    return {"min": str(min(d)), "max": str(max(d))}


def _window(bars, lo, hi, counted, t_spans):
    covered = [b for b in bars if _bar_covered(b)]
    status = ("COVERED" if len(covered) == len(bars)
              else "NOT_COVERED" if not covered else "PARTIALLY_COVERED")
    w = {"start_ns": str(lo), "end_ns": str(hi), "status": status,
         "transport_continuous_receipt_axis": any(a <= lo and hi <= b for a, b in t_spans),
         "bars": bars, "totals": None, "side_coverage": None, "delta_300s": None}
    if status != "COVERED":
        return w  # no total over an uncovered part: UNKNOWN is never 0
    inside = [t for t in counted if lo <= t.event_ns < hi]
    vol = sum((t.size for t in inside), Decimal(0))
    known = [t for t in inside if t.aggressor in (tr.BUY, tr.SELL)]
    kvol = sum((t.size for t in known), Decimal(0))
    w["totals"] = {"trade_count": len(inside), "volume_base": tr._text(vol)}
    w["side_coverage"] = {"known_count": len(known), "total_count": len(inside),
                          "known_volume_base": tr._text(kvol), "total_volume_base": tr._text(vol)}
    w["delta_300s"] = tr.rolling_delta(bars, BAR_NS, [WINDOW_NS])[str(WINDOW_NS)]
    return w


def _hypotheses(ack, ledger, decoder_refusals, symbol_mismatch, exponent_literals,
                frame_order_inversions, cov, counted, rest_rows, cross):
    def h(status, **evidence):
        return {"status": status, "evidence": evidence}

    n = len(counted)
    # H2: WS gaps confronted with REST ids (when REST encloses the gap).
    if not cov["id_gaps"] and n >= 2:
        h2 = h("CONFIRMED_ON_CAPTURE", ws_gaps=0)
    elif cov["id_gaps"] and rest_rows:
        rest_ids = {int(i) for i in rest_rows}
        lo, hi = min(rest_ids), max(rest_ids)
        enclosed = [g for g in cov["id_gaps"] if lo <= int(g["after_id"]) and int(g["before_id"]) <= hi]
        holes = [g for g in enclosed
                 if any(i not in rest_ids for i in range(int(g["after_id"]) + 1, int(g["before_id"])))]
        if holes:
            h2 = h("REFUTED", gaps_also_absent_from_rest=len(holes))
        elif enclosed and len(enclosed) == len(cov["id_gaps"]):
            h2 = h("CONFIRMED_ON_CAPTURE", ws_gaps=len(cov["id_gaps"]), all_present_in_rest=True)
        else:
            h2 = h("UNKNOWN", ws_gaps=len(cov["id_gaps"]), gaps_enclosed_by_rest=len(enclosed))
    else:
        h2 = h("UNKNOWN", ws_gaps=len(cov["id_gaps"]), rest_rows=len(rest_rows))
    decimal_refused = ledger.refused.get("DECIMAL_TEXT_REFUSED", 0)
    if exponent_literals or decimal_refused:
        h4 = h("REFUTED", exponent_literals=exponent_literals, decimal_text_refused=decimal_refused)
    else:
        h4 = h("CONFIRMED_ON_CAPTURE" if n else "UNKNOWN", trades=n)
    if frame_order_inversions or cov["time_inversions"]:
        h5 = h("REFUTED", in_frame_id_inversions=frame_order_inversions,
               native_time_inversions=cov["time_inversions"])
    else:
        h5 = h("CONFIRMED_ON_CAPTURE" if n >= 2 else "UNKNOWN", trades=n)
    instrument_refused = ledger.refused.get("INSTRUMENT_MISMATCH", 0) + ledger.refused.get("QUOTE_MISMATCH", 0)
    if ack is None:
        h6 = h("UNKNOWN", acknowledged=False)
    elif symbol_mismatch or instrument_refused:
        h6 = h("REFUTED", symbol_mismatch=symbol_mismatch, instrument_refused=instrument_refused)
    else:
        h6 = h("CONFIRMED_ON_CAPTURE", ack_symbol=ack["symbol"])
    if cross is None or cross.get("status") not in ("MATCH", "MISMATCH"):
        h7 = h("UNKNOWN", reason=None if cross is None else cross.get("reason"))
    else:
        h7 = h("CONFIRMED_ON_CAPTURE" if cross["status"] == "MATCH" else "REFUTED",
               matched=cross["matched"], content_mismatch=cross["content_mismatch_count"],
               missing_in_ws=cross["missing_in_ws_count"], missing_in_rest=cross["missing_in_rest_count"])
    side_agreement = None if cross is None else cross.get("side_agreement")
    return {
        "H1_side_is_taker": h("DOCUMENTARY", evidence_ref=EVIDENCE_REF, rest_side_agreement=side_agreement),
        "H2_trade_id_plus_one": h2,
        "H3_timestamp_meaning": h("UNKNOWN", reason="DOCUMENTED_AS_BOOK_ORDER_UPDATE_TIMESTAMP"),
        "H4_plain_decimal_numbers": h4,
        "H5_order_and_time_follow_ids": h5,
        "H6_symbol_echo": h6,
        "H7_ws_row_equals_rest_row": h7,
    }


def canonical(report):
    """Canonical bytes of a report (sorted keys, ASCII, no spaces)."""
    return json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def report_sha256(report):
    return hashlib.sha256(canonical(report)).hexdigest()


def is_sha256(text):
    return isinstance(text, str) and bool(_HEX.fullmatch(text))
