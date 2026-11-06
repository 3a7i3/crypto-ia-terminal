"""Offline analysis of a campaign directory: deterministic, no network, no clock.

What it produces (everything keeps its session):
- per session x channel sequence analysis and the four candidate counter domains
  (REFUTED or not refuted, never "confirmed"); counters are never concatenated
  across sessions and heartbeats never certify L2;
- a time inventory that keeps provider send time and provider event time apart
  from the observer's UTC / monotonic receipt, counting MISSING, INVALID,
  SENTINEL_EPOCH and AFTER_CUT values;
- per-session book reconstruction: a gap/repeat/rewind or malformed message
  INVALIDATES the book at that message, deltas never prime a book, a snapshot of
  the same session rebuilds it, a new session starts from nothing;
- trades deduplicated on (provider, product, trade_id) across sessions; an exact
  repeat counts once; a contradictory identity is excluded, in all its variants,
  from every aggregate and kept consultable;
- an explicit, unattested maker -> taker inversion for delta.

The report is canonical JSON; ``report_sha256`` is the replay fingerprint.
"""

from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .exactjson import EXACT, exact  # noqa: F401
from . import protocol as P
from .messages import snapshot_defect, MessageRefusal, SENTINEL, MISSING, INVALID, OK, after_cut, parse_message
from .sequence import GAP, REPEAT, REWIND, SequenceTracker
from .store import read_raw_file, record_bytes

ANALYSIS_VERSION = "pilot-analysis-1.0.0"
MAX_LEVELS_PER_SIDE = 20_000
LOCATOR_CAP = 20
MAKER_TO_AGGRESSOR = {"BUY": "SELL", "SELL": "BUY"}  # EXPLICIT inversion; attested=False


def derive_aggressor(maker_side):
    """Taker side from the raw MAKER side (AsyncAPI text: 'The maker's side of the trade').

    Unmapped or absent -> UNKNOWN, never a default. The convention itself is NOT
    attested by any capture (see ``CONVENTION``).
    """
    return MAKER_TO_AGGRESSOR.get(maker_side, "UNKNOWN") if isinstance(maker_side, str) else "UNKNOWN"


CONVENTION = {
    "raw_side": "MAKER_SIDE_PER_ASYNCAPI_TEXT",
    "aggressor_derivation": "INVERSE_OF_MAKER_SIDE",
    "attested": False,
    "note": "A capture shows raw values only; it cannot attest which side a provider means.",
}


def _canon(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


@exact
def _norm(text):
    return format(Decimal(text).normalize(), "f")


def fingerprint(product, bids, asks):
    doc = {"product": product,
           "bids": [[_norm(p), _norm(q)] for p, q in bids],
           "asks": [[_norm(p), _norm(q)] for p, q in asks]}
    return hashlib.sha256(_canon(doc)).hexdigest()


class _Book:
    def __init__(self):
        self.state, self.reason = "NO_SNAPSHOT", None
        self.bids, self.asks = {}, {}
        self.invalidations = []
        self.publications = []  # (idx, fingerprint)
        self.updates_ignored = 0
        self.snapshots = 0
        self.resyncs = 0

    def side(self, name):
        return self.bids if name == "bid" else self.asks

    def invalidate(self, idx, reason):
        if self.state == "LIVE":
            self.state, self.reason = "INVALID", reason
        self.invalidations.append({"idx": idx, "reason": reason, "state_after": self.state})

    def crossed(self):
        return bool(self.bids and self.asks and max(self.bids) >= min(self.asks))

    def apply(self, idx, kind, ups):
        """Stage on copies; a refused message leaves the book untouched and invalid."""
        if kind == "snapshot":
            was_invalid = self.state == "INVALID"
            defect = snapshot_defect(ups)
            if defect is not None:  # same criterion as runner/verifier: no usable book, later updates wait
                self.bids, self.asks = {}, {}
                self.state, self.reason = "INVALID", defect
                self.invalidations.append({"idx": idx, "reason": defect, "state_after": "INVALID"})
                return
            bids, asks = {}, {}
            for side, price, ptxt, qty, qtxt, _t in ups:
                (bids if side == "bid" else asks)[price] = (ptxt, qtxt)
            self.bids, self.asks = bids, asks
            self.state, self.reason = "LIVE", None
            self.snapshots += 1
            if was_invalid:
                self.resyncs += 1
        else:
            if self.state != "LIVE":
                self.updates_ignored += 1  # deltas never prime or repair a book
                return
            bids, asks = dict(self.bids), dict(self.asks)
            for side, price, ptxt, qty, qtxt, _t in ups:
                lv = bids if side == "bid" else asks
                if qty == 0:
                    if price not in lv:
                        self.invalidate(idx, "REMOVE_UNKNOWN_LEVEL")
                        return
                    del lv[price]
                else:
                    lv[price] = (ptxt, qtxt)  # absolute quantity replaces the level
            self.bids, self.asks = bids, asks
        if len(self.bids) > MAX_LEVELS_PER_SIDE or len(self.asks) > MAX_LEVELS_PER_SIDE:
            self.invalidate(idx, "LEVEL_LIMIT_EXCEEDED")
            return
        if self.crossed():
            self.invalidate(idx, "CROSSED_OR_LOCKED_BOOK")
            return

    def levels(self):
        return ([(self.bids[k][0], self.bids[k][1]) for k in sorted(self.bids, reverse=True)],
                [(self.asks[k][0], self.asks[k][1]) for k in sorted(self.asks)])

    def publish(self, idx):
        if self.state == "LIVE":  # nothing is ever published from an invalid state
            b, a = self.levels()
            self.publications.append((idx, fingerprint(P.PRODUCT, b, a)))

    def report(self):
        chain = hashlib.sha256(_canon(self.publications)).hexdigest()
        final = None
        if self.state == "LIVE":
            b, a = self.levels()
            final = fingerprint(P.PRODUCT, b, a)
        return {"final_state": self.state, "final_reason": self.reason, "final_fingerprint": final,
                "publications": len(self.publications), "published_idx": [i for i, _ in self.publications][:1000],
                "publication_chain_sha256": chain,
                "invalidations": self.invalidations[:LOCATOR_CAP], "invalidation_count": len(self.invalidations),
                "updates_ignored_without_valid_book": self.updates_ignored,
                "snapshots_applied": self.snapshots, "resyncs": self.resyncs,
                "levels": {"bids": len(self.bids), "asks": len(self.asks)}}


def _states(counter, obs, cut, own_recv, key, locs, where):
    state = obs.state
    if after_cut(obs, cut):
        counter["AFTER_CUT"] += 1
    if obs.state == OK and own_recv is not None and obs.ns > own_recv:
        counter["AFTER_OWN_RECEIPT"] += 1
    counter[state] += 1
    if state != OK and len(locs) < LOCATOR_CAP:
        locs.append({"at": where, "field": key, "state": state})


def _new_counter():
    return {OK: 0, MISSING: 0, INVALID: 0, SENTINEL: 0, "AFTER_CUT": 0, "AFTER_OWN_RECEIPT": 0}


def _load(directory):
    base = Path(directory)
    sessions, problems = {}, []
    for p in sorted(base.glob("S??.raw.jsonl")):
        recs, probs, data = read_raw_file(p)
        sessions[p.name[:3]] = recs
        problems += [p.name[:3] + ":" + x for x in probs]
    intent = base / "intent.json"
    final = base / "final.receipt.json"
    cfg = json.loads(intent.read_bytes()) if intent.exists() else {}
    fin = json.loads(final.read_bytes()) if final.exists() else {}
    return sessions, problems, cfg, fin


def analyze(directory, *, policy=None, cut_utc_ns=None):
    sessions, problems, cfg, fin = _load(directory)
    policy = policy or cfg.get("sequence_policy") or P.DEFAULT_SEQUENCE_POLICY
    if cut_utc_ns is None:
        cut_utc_ns = fin.get("ended_utc_ns")
        if cut_utc_ns is None:
            cut_utc_ns = max((r["recv_utc_ns"] for rs in sessions.values() for r in rs), default=None)
    out_sessions, trades_seen = {}, {}
    totals_time = {k: _new_counter() for k in ("send_time", "l2_event_time", "trade_time", "heartbeat_current_time")}
    for sid, recs in sessions.items():
        tracker = SequenceTracker(policy)
        book = _Book()
        refused, channels = {}, {}
        times = {k: _new_counter() for k in totals_time}
        locs = []
        hb_prev, hb_gaps = None, 0
        for rec in recs:
            idx = rec["idx"]
            raw = record_bytes(rec)
            where = "%s#%d" % (sid, idx)
            try:
                m = parse_message(raw)
            except MessageRefusal as e:
                refused[str(e)] = refused.get(str(e), 0) + 1
                book.invalidate(idx, "MALFORMED_MESSAGE:" + str(e))
                continue
            if m.kind == "error":
                refused["PROVIDER_ERROR_MESSAGE"] = refused.get("PROVIDER_ERROR_MESSAGE", 0) + 1
                book.invalidate(idx, "PROVIDER_ERROR_MESSAGE")
                continue
            channels[m.channel] = channels.get(m.channel, 0) + 1
            own = rec["recv_utc_ns"]
            _states(times["send_time"], m.send, cut_utc_ns, own, "timestamp", locs, where)
            for t in m.heartbeat_times:
                _states(times["heartbeat_current_time"], t, cut_utc_ns, own, "current_time", locs, where)
            for c in m.heartbeat_counters:
                if c is not None:
                    if hb_prev is not None and c != hb_prev + 1:
                        hb_gaps += 1
                    hb_prev = c
            for t in m.trades:
                _states(times["trade_time"], t["time"], cut_utc_ns, own, "trade.time", locs, where)
            for _k, _p, ups in m.l2_events:
                for u in ups:
                    _states(times["l2_event_time"], u[5], cut_utc_ns, own, "l2.event_time", locs, where)
            verdict = tracker.observe(idx, m.channel, m.seq, m.products)
            skip_apply = False
            if verdict["kind"] in (GAP, REPEAT, REWIND):
                book.invalidate(idx, "SEQUENCE_%s expected=%s got=%s domain=%s" % (
                    verdict["kind"], verdict["expected"], verdict["got"], verdict["domain"]))
                skip_apply = verdict["kind"] in (REPEAT, REWIND)  # a stale message is never applied
            if m.channel == P.L2_CHANNEL and not skip_apply:
                touched = False
                for kind, product, ups in m.l2_events:
                    book.apply(idx, kind, ups)
                    touched = True
                if touched:
                    book.publish(idx)
            if m.channel == P.TRADES_CHANNEL:
                for t in m.trades:
                    key = (P.PROVIDER, t["product"], t["trade_id"])
                    payload = (t["price"], t["size"], t["side"] if isinstance(t["side"], str) else None, t["time_text"])
                    v = trades_seen.setdefault(key, {})
                    e = v.setdefault(payload, {"count": 0, "locators": []})
                    e["count"] += 1
                    if len(e["locators"]) < LOCATOR_CAP:
                        e["locators"].append(where)
        for k in totals_time:
            for st, n in times[k].items():
                totals_time[k][st] += n
        out_sessions[sid] = {
            "messages": len(recs), "channels": dict(sorted(channels.items())), "refused": dict(sorted(refused.items())),
            "sequence": tracker.report(), "book": book.report(), "times": times,
            "time_locators": locs, "heartbeat_counter_gaps": hb_gaps,
            "first_recv_utc_ns": recs[0]["recv_utc_ns"] if recs else None,
            "last_recv_utc_ns": recs[-1]["recv_utc_ns"] if recs else None,
            "first_recv_mono_ns": recs[0]["recv_mono_ns"] if recs else None,
            "last_recv_mono_ns": recs[-1]["recv_mono_ns"] if recs else None,
        }
    report = {
        "analysis_version": ANALYSIS_VERSION, "policy": policy, "cut_utc_ns": cut_utc_ns,
        "read_problems": problems, "campaign_end_reason": fin.get("end_reason"),
        "campaign_complete": fin.get("complete"), "sessions": out_sessions, "time_totals": totals_time,
        "trades": _trades(trades_seen), "side_convention": CONVENTION,
        "notes": ["Counters are never concatenated across sessions.",
                  "Heartbeats are never used to certify L2.",
                  "Provider send time and event time are kept apart from observer UTC/monotonic receipt."],
    }
    report["report_sha256"] = hashlib.sha256(_canon(report)).hexdigest()
    return report


@exact
def _trades(seen):
    accepted = {}
    conflicts = []
    exact_dups = 0
    for key in sorted(seen):
        variants = seen[key]
        if len(variants) > 1:
            conflicts.append({"identity": list(key), "variants": [
                {"price": p[0], "size": p[1], "maker_side": p[2], "time": p[3], "count": e["count"],
                 "locators": e["locators"]} for p, e in sorted(variants.items(), key=lambda kv: repr(kv[0]))]})
            continue
        (payload, e), = variants.items()
        exact_dups += e["count"] - 1
        accepted[key] = (payload, e["count"])
    vol = {"BUY": Decimal(0), "SELL": Decimal(0), "UNKNOWN": Decimal(0)}
    total = Decimal(0)
    for _key, (payload, _n) in accepted.items():
        size = Decimal(payload[1])
        total += size
        vol[payload[2] if payload[2] in ("BUY", "SELL") else "UNKNOWN"] += size
    def fmt(d):
        return format(d, "f")

    taker = {"BUY": vol["SELL"], "SELL": vol["BUY"]}  # explicit inversion of the maker side
    d, u = taker["BUY"] - taker["SELL"], vol["UNKNOWN"]
    return {
        "identity": "provider+product+trade_id", "identities_seen": len(seen),
        "identities_counted": len(accepted), "exact_duplicates_collapsed": exact_dups,
        "conflicting_identities": len(conflicts), "conflicts": conflicts,
        "excluded_from_aggregates": "all variants of every conflicting identity",
        "aggregates": {
            "volume_base": fmt(total),
            "volume_by_raw_maker_side": {"BUY": fmt(vol["BUY"]), "SELL": fmt(vol["SELL"]), "UNKNOWN": fmt(vol["UNKNOWN"])},
            "derived_taker_volume": {"BUY": fmt(taker["BUY"]), "SELL": fmt(taker["SELL"])},
            "derived_delta": fmt(d) if u == 0 else None,
            "derived_delta_bounds": [fmt(d - u), fmt(d + u)],
            "cvd": "NOT_COMPUTED",
            "convention_attested": False,
        },
    }
