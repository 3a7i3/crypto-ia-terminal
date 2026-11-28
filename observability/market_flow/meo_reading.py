"""MEO-03: descriptive reading of a MEO-01 replay report (pure projection, no new engine).

Every number comes from the replay report built by ``kraken_trades.replay_journal``
(itself ``trades.build_bars`` and ``trades.rolling_delta``). This module copies
those values, sums the minute volumes of a window to cross-check them, takes
signs, and applies the versioned rule DESALIGN-1 v1. It recomputes no bar, no
Delta and no CVD; CVD values and their anchor are the source engine's.

Scope (operator GO MEO-03, 2026-11-28): INSTRUMENT_ADMISSION = PROBATION for the
TRADE_FLOW use, ``time_basis`` UNATTESTED, windows on the native axis. A reading
never claims ADMITTED_PARTIAL, never states an UTC instant, and a SYNTHETIC
report stays SYNTHETIC: it is never projected as HISTORICAL or OBSERVATION.
"""

from decimal import Decimal
import hashlib
import json

from . import trades as tr
from .exact import exact
from .kraken_trades import WINDOW_NS, report_sha256

SCHEMA = "meo-03-reading/0.1"
RULE = {"id": "DESALIGN-1", "version": "1",
        "definition": "sign(price_last - price_first) against sign(Delta 300 s bounds), per covered 5-minute "
                      "window; no threshold"}
QUALIFICATION = "CONDITIONAL_ON_UNPROVEN_NATIVE_UTC_ALIGNMENT"
MIN_TRADES_FOR_ALIGNMENT = 2  # operator precision: fewer than two trades -> UNKNOWN, even with a zero change

# State table of DESALIGN-1 v1: (price sign, flow sign) -> alignment.
_TABLE = {
    ("+", "+"): "ALIGNED", ("+", "-"): "DIVERGENT", ("+", "0"): "FLAT_FLOW",
    ("-", "+"): "DIVERGENT", ("-", "-"): "ALIGNED", ("-", "0"): "FLAT_FLOW",
    ("0", "+"): "FLAT_PRICE", ("0", "-"): "FLAT_PRICE", ("0", "0"): "FLAT",
}

LIMITS = [
    "Descriptive reading under PROBATION; it does not claim ADMITTED_PARTIAL.",
    "time_basis UNATTESTED: windows and minutes are on the native axis; no UTC instant is asserted.",
    "A first observed desalignment is not a demonstrated instant of formation.",
    "Inside a minute, trades are ordered by trade_id only.",
    "DESALIGN-1 has no threshold and measures neither size nor persistence; it states no cause.",
    "Comparisons between windows of different captures are not part of this reading.",
]


class ReadingRefusal(ValueError):
    pass


def _sign(lo, hi):
    if lo > 0:
        return "+"
    if hi < 0:
        return "-"
    if lo == 0 and hi == 0:
        return "0"
    return "?"


def _evidence(report):
    kind = report.get("evidence_kind")
    if report.get("synthetic") is True or kind == "SYNTHETIC":
        return "SYNTHETIC", "SYNTHETIC"  # a fixture never becomes HISTORICAL or OBSERVATION
    if kind == "OBSERVATION" and report.get("synthetic") is False:
        # Operator decision MEO-02 RV01: OBSERVATION kept at the source, HISTORICAL projection offline.
        return "HISTORICAL", "OBSERVATION"
    raise ReadingRefusal("EVIDENCE_KIND_NOT_READABLE")


def _anchors(report):
    """First bar start of each CVD segment, as numbered by the source engine."""
    anchors = {}
    for w in report["windows"]:
        for b in w["bars"]:
            seg = b.get("segment")
            if seg is not None:
                anchors[seg] = min(anchors.get(seg, int(b["start_ns"])), int(b["start_ns"]))
    return {k: str(v) for k, v in anchors.items()}


@exact
def _read_window(w, ack_ns, anchors):
    lo, hi = int(w["start_ns"]), int(w["end_ns"])
    bars = w["bars"]
    out = {"start_ns": w["start_ns"], "end_ns": w["end_ns"], "status": w["status"],
           "transport_continuous_if_native_aligned": w["transport_continuous_if_native_aligned"],
           "minutes": [{k: b.get(k) for k in ("start_ns", "status", "trade_count", "open", "close",
                                               "buy_volume", "sell_volume", "unknown_volume",
                                               "delta_base", "delta_base_bounds", "cvd_base",
                                               "cvd_base_bounds", "segment")} for b in bars]}
    # First-desalignment eligibility (operator M3): no window before or overlapping the subscription,
    # none without transport continuity. Comparing native bounds with the receipt ack is conditional.
    if ack_ns is None:
        reason = "NO_SUBSCRIPTION_ACK"
    elif hi <= ack_ns:
        reason = "PRE_SUBSCRIPTION"
    elif lo < ack_ns:
        reason = "OVERLAPS_SUBSCRIPTION"
    elif not w["transport_continuous_if_native_aligned"]:
        reason = "TRANSPORT_NOT_CONTINUOUS"
    elif w["status"] != "COVERED":
        reason = "NOT_COVERED"
    else:
        reason = None
    out["eligible_for_first_desalignment"] = reason is None
    out["exclusion_reason"] = reason

    keys = ("price_first", "price_last", "price_change", "trade_count", "volume_base", "buy_volume",
            "sell_volume", "unknown_volume", "delta", "delta_bounds", "delta_status", "cvd_end",
            "cvd_end_bounds", "cvd_segment", "cvd_anchor_ns")
    if w["status"] != "COVERED":
        out.update({k: None for k in keys})  # UNKNOWN is never 0
        out.update(signs=None, alignment="UNKNOWN", alignment_reason="WINDOW_NOT_COVERED")
        return out

    priced = [b for b in bars if b["status"] == "OBSERVED"]
    total = Decimal(w["totals"]["volume_base"])
    sums = {k: sum((Decimal(b[k]) for b in bars), Decimal(0)) for k in ("buy_volume", "sell_volume",
                                                                          "unknown_volume")}
    if sums["buy_volume"] + sums["sell_volume"] + sums["unknown_volume"] != total:
        raise ReadingRefusal("WINDOW_VOLUMES_INCONSISTENT")  # a projection never invents a total
    d = w["delta_300s"] or {}
    bounds = d.get("delta_base_bounds")
    last = bars[-1]
    seg = last.get("segment")
    out.update({
        "price_first": priced[0]["open"] if priced else None,
        "price_last": priced[-1]["close"] if priced else None,
        "price_change": (tr._text(Decimal(priced[-1]["close"]) - Decimal(priced[0]["open"]))
                         if priced else None),
        "trade_count": w["totals"]["trade_count"], "volume_base": w["totals"]["volume_base"],
        "buy_volume": tr._text(sums["buy_volume"]), "sell_volume": tr._text(sums["sell_volume"]),
        "unknown_volume": tr._text(sums["unknown_volume"]),
        "delta": d.get("delta_base"), "delta_bounds": bounds, "delta_status": d.get("status"),
        # CVD exactly as the source engine anchored it: value, bounds, segment and its first bar.
        "cvd_end": last.get("cvd_base"), "cvd_end_bounds": last.get("cvd_base_bounds"),
        "cvd_segment": seg, "cvd_anchor_ns": anchors.get(seg) if seg is not None else None,
    })
    sp = "?" if out["price_change"] is None else _sign(Decimal(out["price_change"]), Decimal(out["price_change"]))
    sf = "?" if not bounds else _sign(Decimal(bounds[0]), Decimal(bounds[1]))
    out["signs"] = {"price": sp, "flow": sf}
    if out["trade_count"] < MIN_TRADES_FOR_ALIGNMENT:
        out.update(alignment="UNKNOWN", alignment_reason="FEWER_THAN_TWO_TRADES")
    elif "?" in (sp, sf):
        out.update(alignment="UNKNOWN",
                   alignment_reason="PRICE_UNKNOWN" if sp == "?" else "FLOW_SIGN_UNRESOLVED")
    else:
        out.update(alignment=_TABLE[(sp, sf)], alignment_reason=None)
    return out


def read_report(report):
    """Project one MEO-01 replay report into a MEO-03 reading (deterministic, pure)."""
    if not isinstance(report, dict) or report.get("schema") != "meo-01-trades-report/1":
        raise ReadingRefusal("REPORT_SCHEMA_UNSUPPORTED")
    kind, source_kind = _evidence(report)
    ack = report["subscription"]["acknowledged_receipt_ns"]
    ack_ns = int(ack) if report["subscription"]["acknowledged"] and ack is not None else None
    for w in report["windows"]:
        if int(w["end_ns"]) - int(w["start_ns"]) != WINDOW_NS:
            raise ReadingRefusal("WINDOW_GEOMETRY_UNSUPPORTED")
    anchors = _anchors(report)
    windows = [_read_window(w, ack_ns, anchors) for w in report["windows"]]

    divergent = [{"start_ns": w["start_ns"], "segment": w["cvd_segment"],
                  "eligible_for_first_desalignment": w["eligible_for_first_desalignment"],
                  "exclusion_reason": w["exclusion_reason"]}
                 for w in windows if w["alignment"] == "DIVERGENT"]
    by_segment = {}
    for w in windows:  # chronological; the search restarts in each coverage segment
        if w["eligible_for_first_desalignment"] and w["alignment"] == "DIVERGENT":
            by_segment.setdefault(w["cvd_segment"], w["start_ns"])
    firsts = [{"segment": s, "start_ns": t} for s, t in sorted(by_segment.items(), key=lambda x: int(x[1]))]
    src = report["source"]
    return {
        "schema": SCHEMA, "rule": RULE,
        "admission": {"instrument_admission": "PROBATION", "use": "TRADE_FLOW", "claims_admitted_partial": False},
        "evidence_kind": kind, "source_evidence_kind": source_kind,
        "time_basis": "UNATTESTED", "axis": "NATIVE", "qualification": QUALIFICATION,
        "quality": {"state": "DEGRADED", "reason_codes": ["NATIVE_TIME_UNATTESTED", "SIDE_BASIS_DOCUMENTARY",
                                                          "PROBATION"]},
        "flow": report["flow"],
        "corpus_ref": {"events_sha256": src["events_sha256"], "frames_sha256": src["frames_sha256"],
                       "capture_code_digest": src["capture_code_digest"],
                       "source_report_sha256": report_sha256(report)},
        "subscription_acknowledged_receipt_ns": ack,
        "windows": windows,
        "divergent_windows": divergent,
        "first_desalignment_by_segment": firsts,
        "first_desalignment": ({**firsts[0], "meaning": "FIRST_OBSERVED_NOT_FORMATION_INSTANT"}
                               if firsts else None),
        "limits": LIMITS,
    }


def canonical(reading):
    return json.dumps(reading, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def reading_sha256(reading):
    return hashlib.sha256(canonical(reading)).hexdigest()
