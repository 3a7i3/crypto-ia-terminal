"""Closed MarketFlowArtifact v1 builder, validator and deterministic replay.

Chain: conserved events -> versioned backend calculation -> closed artifact ->
(reader/API GET) -> frontend. Everything is synthetic here: the artifact says
so and the validator refuses one that does not.
"""

import hashlib
import json

from . import CALC_VERSION, CONTRACT_VERSION
from . import contract, l2, trades as tr
from .heatmap import book_sample, build_heatmap, level_events
from .interval import Span

TOP_KEYS = {
    "schema_version", "product", "calc_version", "evidence_kind", "synthetic", "state_label",
    "flow", "as_of_receipt_ns", "anchor_ns", "bar_ns", "inputs", "trades", "bars",
    "rolling_delta", "book", "heatmap", "level_events", "assumptions", "limits",
    "economic_metrics", "score", "recommendation",
}


def canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _walk_no_float(x, path="$"):
    if isinstance(x, float):
        raise ValueError("FLOAT_REFUSED:" + path)
    if isinstance(x, dict):
        for k, v in x.items():
            _walk_no_float(v, path + "." + str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _walk_no_float(v, path + "[%d]" % i)


def validate_artifact(doc):
    """Closed, nested check of form and internal consistency (never of truth)."""
    if not isinstance(doc, dict) or set(doc) != TOP_KEYS:
        raise ValueError("CLOSED_TOP_LEVEL_KEYS_REQUIRED")
    _walk_no_float(doc)
    if doc["schema_version"] != CONTRACT_VERSION or doc["product"] != "MarketFlowArtifact":
        raise ValueError("CONTRACT_VERSION_REFUSED")
    if doc["calc_version"] != CALC_VERSION:
        raise ValueError("CALC_VERSION_REFUSED")
    if doc["synthetic"] is not True or doc["evidence_kind"] not in ("SYNTHETIC", "HISTORICAL"):
        raise ValueError("EVIDENCE_KIND_REQUIRED")
    if doc["state_label"] != ("SYNTHETIC" if doc["evidence_kind"] == "SYNTHETIC" else "HISTORICAL"):
        raise ValueError("STATE_LABEL_MISMATCH")
    for k in ("economic_metrics", "score", "recommendation"):
        if doc[k] is not None:
            raise ValueError("NO_METRIC_SCORE_OR_RECOMMENDATION")
    as_of = contract.ns(doc["as_of_receipt_ns"], "as_of_receipt_ns")
    anchor = contract.ns(doc["anchor_ns"], "anchor_ns")
    bar_ns = contract.ns(doc["bar_ns"], "bar_ns")
    if bar_ns <= 0 or as_of < anchor:
        raise ValueError("BAR_GEOMETRY_INVALID")
    contract.check_flow(doc["flow"])
    contract.check_inputs(doc["inputs"])
    contract.check_trades(doc["trades"])
    contract.check_bars(doc["bars"], anchor, bar_ns, as_of)
    contract.check_rolling(doc["rolling_delta"], bar_ns)
    contract.check_book(doc["book"], doc["flow"])
    contract.check_heatmap(doc["heatmap"], as_of)
    contract.check_level_events(doc["level_events"])
    for k in ("assumptions", "limits"):
        contract.str_list(doc[k], k)
    return doc


def _receipt(r):
    return l2.Receipt(Span(*r["mono"]), Span(*r["utc"]))


def _check_identity(c):
    """One instrument, one identity: the book layer is the Coinbase L2 candidate only."""
    flow = c["trade_flow"]
    if (flow.venue != l2.COINBASE_L2_FLOW.venue or c["product"] != flow.instrument
            or l2.INSTRUMENTS.get(c["product"]) != (flow.base, flow.quote)):
        raise ValueError("FLOW_BOOK_IDENTITY_MISMATCH")


def _window(ev):
    """(first, last) observer UTC bound of one event's full receipt."""
    if ev["kind"] == "trade":
        return ev["received_ns"], ev["received_ns"]
    if ev["kind"] in ("l2", "sample"):
        lo, hi = ev["receipt"]["utc"]
        return lo, hi
    raise ValueError("EVENT_KIND_UNKNOWN")


def _ns_as_text(book):
    """Contract: every nanosecond value is a decimal string (JS numbers lose integers)."""
    f = book["freshness"]
    if f is not None:
        for k in ("connection_silence_ns", "state_age_ns"):
            if f[k] is not None:
                f[k] = [str(v) for v in f[k]]
    for side in ("bid", "ask"):
        lv = book["bbo"][side]
        if lv is not None and lv["level_event_time_ns"] is not None:
            lv["level_event_time_ns"] = str(lv["level_event_time_ns"])


def replay(events, config):
    """Deterministic: same events + config + version => identical artifact bytes.

    ``events`` are processed in the given (arrival) order. An event is read only
    if its FULL receipt is at or before ``as_of_receipt_ns``. One that begins
    before and ends after the cut is not read and makes the book UNRESOLVED at
    ``as_of``; so are the later book events (message order is not guessed).
    Events starting after ``as_of`` are not read: no future data reaches the result.
    """
    c = config
    _check_identity(c)
    as_of = c["as_of_receipt_ns"]
    flow = c["trade_flow"]
    ledger = tr.TradeLedger(flow)
    conn = l2.L2Connection(c["connection_id"], l2.COINBASE_L2_FLOW)
    samples, used = [], []
    after = straddle = halted = 0
    book_halted = False
    last_receipt = None  # only used to know whether any l2 message was read
    for ev in events:
        lo, hi = _window(ev)
        if lo > as_of:
            after += 1
            continue
        if ev["kind"] != "trade":
            if hi > as_of:
                straddle += 1
                book_halted = True
                continue
            if book_halted:
                halted += 1
                continue
        used.append(ev)
        if ev["kind"] == "l2":
            last_receipt = _receipt(ev["receipt"])
            res = conn.feed(json.dumps(ev["message"]).encode(), last_receipt)
            del res  # refusals are visible through the book state sampled below
            # A sample is dated at the END of the full receipt, never before it.
            samples.append(book_sample(conn, c["product"], hi,
                                       depth_levels_limit=c.get("depth_levels_limit")))
        elif ev["kind"] == "sample":
            # Periodic sample: the book is only called LIVE if the connection was
            # not silent beyond the explicit budget at that instant.
            smp = book_sample(conn, c["product"], hi, depth_levels_limit=c.get("depth_levels_limit"))
            if smp["state"] == "LIVE":
                f = conn.freshness(c["product"], _receipt(ev["receipt"]),
                                   silence_budget_ns=c["silence_budget_ns"])
                if f["connection_silence_status"] != "WITHIN_BUDGET":
                    smp["state"] = f["connection_silence_status"]
            samples.append(smp)
        else:
            ledger.ingest(ev["record"], session_id=ev["session_id"],
                          received_ns=ev["received_ns"], arrival_seq=ev["arrival_seq"])
    built = tr.build_bars(ledger, anchor_ns=c["anchor_ns"], bar_ns=c["bar_ns"],
                          as_of_ns=as_of, coverage=c["coverage"])
    roll = tr.rolling_delta(built["bars"], c["bar_ns"], c["windows_ns"])
    heat = build_heatmap(samples, as_of_ns=as_of, **c["heatmap"])
    lev, truncated = level_events(samples, as_of_ns=as_of, trades=ledger.trades)
    book = {"state": list(conn.state(c["product"])), "bbo": conn.bbo(c["product"]), "freshness": None}
    if book_halted:
        # A message may have been received after the cut: the book at as_of is unknown.
        book["state"] = ["UNRESOLVED", "MESSAGE_STRADDLES_AS_OF"]
        book["bbo"].update(status="NOT_AVAILABLE", reason="MESSAGE_STRADDLES_AS_OF", bid=None, ask=None)
    elif last_receipt is not None:
        now = l2.Receipt(Span(as_of, as_of), Span(as_of, as_of))  # synthetic: one clock
        book["freshness"] = conn.freshness(c["product"], now, silence_budget_ns=c["silence_budget_ns"])
    _ns_as_text(book)
    doc = {
        "schema_version": CONTRACT_VERSION, "product": "MarketFlowArtifact", "calc_version": CALC_VERSION,
        "evidence_kind": "SYNTHETIC", "synthetic": True, "state_label": "SYNTHETIC",
        "flow": {
            "venue": flow.venue, "instrument": flow.instrument, "base": flow.base, "quote": flow.quote,
            "market_kind": flow.market_kind, "id_domain": flow.id_domain,
            "side_convention": {"attested": flow.side.attested, "evidence_ref": flow.side.evidence_ref},
        },
        "as_of_receipt_ns": str(as_of), "anchor_ns": str(c["anchor_ns"]), "bar_ns": str(c["bar_ns"]),
        "inputs": {
            "events_sha256": hashlib.sha256(canonical(used)).hexdigest(),
            "event_count": len(used), "events_after_as_of_not_read": after,
            "events_straddling_as_of_not_read": straddle, "l2_events_not_read_after_straddle": halted,
        },
        "trades": {
            "accepted": len(ledger.trades), "duplicates": ledger.duplicates, "conflicts": ledger.conflicts,
            "refused": dict(sorted(ledger.refused.items())), "sessions": ledger.sessions,
            "excluded": built["excluded"],
        },
        "bars": built["bars"], "rolling_delta": roll, "book": book, "heatmap": heat,
        "level_events": {"items": lev, "truncated": truncated},
        "assumptions": sorted(l2.ASSUMPTIONS),
        "limits": [
            "Synthetic fixtures only: nothing here is provider output.",
            "Delta/CVD use an aggressor convention that is unattested unless side_convention.attested.",
            "Displayed quantity is not executed volume; a vanished level has no proven cause.",
            "Native times are unqualified; no age is certified without provider and observer proofs.",
        ],
        "economic_metrics": None, "score": None, "recommendation": None,
    }
    return validate_artifact(json.loads(json.dumps(doc)))
