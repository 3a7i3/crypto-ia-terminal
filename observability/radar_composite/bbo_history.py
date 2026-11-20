"""Compact, read-only historical publication of the BBO Spot composite.

Built offline from a sealed BBO evidence directory (manifest, events, frames)
and its replay outputs (``replay/summary.json`` and ``replay/window_N_primary.json``).
Values are copied from the replayed publications; nothing is recomputed here
except presence checks, sums of published counts and file fingerprints.

The publication is a presentation artifact for the Radar: it does not prove any
freshness, it opens no network connection and it is never an input to a
decision. Schema ``bbo-composite-history/1.0.0``.

Usage:
    python3 -m observability.radar_composite.bbo_history build \\
        --evidence DIR [--evidence DIR ...] --archive TAR.GZ [--archive TAR.GZ ...] \\
        --report NAME --out FILE
    python3 -m observability.radar_composite.bbo_history validate FILE
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from observability.radar_composite.bbo_schema import validate_bbo

SCHEMA_VERSION = "bbo-composite-history/1.0.0"
LABEL = "Composite de milieux de carnet · Spot · Historique"
VENUES = ("mexc", "kraken")
CATEGORIES = ("COMPOSITE", "SINGLE_SOURCE", "SOURCE_EXCLUDED", "EXCESSIVE_GAP", "NOT_EVALUATED")
SOURCE_STATES = ("VALID", "UNCHANGED_VERIFIED", "FRESHNESS_UNKNOWN", "CONTINUITY_LOST",
                 "BOOK_INVALID", "NOT_INITIALIZED", "SOURCE_UNAVAILABLE")
CANDLE_STATUSES = ("COMPLETE", "INCOMPLETE")
SENS_KEYS = tuple(f"L{ls}s_G{g}bps" for ls in (1, 2, 5, 10) for g in (10, 25, 50, 100))
A_ORDER = ("the server sends on one connection in order: a PONG received after earlier "
           "diffs proves those diffs were delivered (hypothesis, not qualified at runtime)")
DEC = re.compile(r"^-?(0|[1-9][0-9]{0,30})(\.[0-9]{1,18})?$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
MAX_BYTES = 200_000


class HistoryError(ValueError):
    """The evidence or a publication does not satisfy the contract."""


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise HistoryError(f"duplicate field {k}")
            out[k] = v
        return out

    def constant(_):
        raise HistoryError("non-finite number")

    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=constant)


def _candle(c):
    return {k: c.get(k) for k in ("open", "high", "low", "close", "points", "status")}


def pair_entry(evidence_dir, archive_path):
    d = Path(evidence_dir)
    manifest = _load(d / "manifest.json")
    summary = _load(d / "replay" / "summary.json")
    sealed = manifest["sealed"]
    if _sha(d / "events.jsonl") != sealed["events_sha256"] or _sha(d / "frames.bin") != sealed["frames_sha256"]:
        raise HistoryError("sealed evidence does not match its manifest")
    if manifest["status"] != "COMPLETED" or manifest.get("stop_code") is not None:
        raise HistoryError("run did not complete")
    if summary["code"]["git_head"] != manifest["code"]["git_head"]:
        raise HistoryError("replay and manifest name different commits")
    archive = Path(archive_path)
    if manifest["pair"] not in archive.name or d.name not in archive.name:
        raise HistoryError("archive name does not match the evidence directory")
    windows, window_sha = [], []
    for w in summary["windows"]:
        path = d / "replay" / f"window_{w['window']}_primary.json"
        pub = _load(path)
        errors = validate_bbo(pub)
        if errors:
            raise HistoryError(f"window {w['window']} publication invalid: {errors[:3]}")
        if pub["window"]["start_ms"] != w["start_ms"] or pub["counts"]["by_category"] != w["by_category"]:
            raise HistoryError(f"window {w['window']} disagrees with the replay summary")
        window_sha.append(_sha(path))
        windows.append({
            "index": w["window"], "start_ms": pub["window"]["start_ms"], "end_ms": pub["window"]["end_ms"],
            "planned": w["planned"], "evaluated": w["evaluated"], "composite": w["composite"],
            "by_category": {k: w["by_category"][k] for k in CATEGORIES},
            "by_source_state": {v: {s: w["by_source_state"][v][s] for s in SOURCE_STATES} for v in VENUES},
            "candle": _candle(pub["candles"]["composite"]),
            "venue_candles": {v: _candle(pub["candles"][v]) for v in VENUES},
            "sensitivity_composite": {k: w["sensitivity_composite"][k] for k in SENS_KEYS},
        })
    t = summary["totals"]
    evaluated = t["evaluated"]
    flux = {v: {"eligible": summary["flux"][v]["eligible"],
                "unchanged_verified": summary["flux"][v]["of_which_unchanged_verified"],
                "evaluated": summary["flux"][v]["evaluated"],
                "unresolved_breaks": summary["flux"][v]["unresolved_breaks"],
                "verdict": summary["flux"][v]["verdict"]} for v in VENUES}
    # Pure presentation flag: published counts only, no new metric.
    a_order_majority = any(2 * flux[v]["unchanged_verified"] > evaluated for v in VENUES)
    sens_totals = {k: sum(w["sensitivity_composite"][k] for w in windows) for k in SENS_KEYS}
    venues = manifest["ws"]
    params = manifest["parameters_primary"]
    pair = manifest["pair"]
    return {
        "pair": pair,
        "display_symbol": f"{manifest['instrument']['base_asset_id']}/{manifest['instrument']['quote_asset_id']}",
        "market_type": manifest["market_type"],
        "evidence_kind": manifest["evidence_kind"],
        "venues": [{"venue": "mexc", "native_symbol": venues["mexc"]["symbol"], "feed": "aggre.depth protobuf 100 ms + REST depth"},
                   {"venue": "kraken", "native_symbol": venues["kraken"]["symbol"], "feed": "book v2 depth 10 + CRC32"}],
        "thresholds": {"liveness_max_ms": params["liveness_max_ms"], "gap_max_bps": params["gap_max_bps"],
                       "gap_boundary": params["gap_boundary"], "step_ms": params["step_ms"],
                       "points_per_window": params["points_per_window"], "weights": params["weights"],
                       "reference_venue": params["reference_venue"]},
        "window_utc": {"start_ms": windows[0]["start_ms"], "end_ms": windows[-1]["end_ms"]},
        "coverage": {"planned": t["planned"], "evaluated": evaluated, "composite": t["composite"],
                     "complete_composite_candles": t["complete_composite_candles"],
                     "candles": len(windows), "verdict_pre_registered": t["verdict_pre_registered"]},
        "windows": windows,
        "sensitivity_composite_totals": sens_totals,
        "flux": flux,
        "hypotheses": {"A_ORDER": {"statement": A_ORDER, "majority_unchanged_verified": a_order_majority}},
        "kraken_checksums": {"match": sum(x["match"] for x in summary["kraken_checksum_audit"]["checked_by_type"].values()),
                             "mismatch": len(summary["kraken_checksum_audit"]["mismatches"])},
        "provenance": {
            "pilot": manifest["pilot"], "collection_commit": manifest["code"]["git_head"],
            "host": manifest["host"], "run_status": manifest["status"], "exit_code": manifest["exit_code"],
            "started_utc_ms": manifest["created_wall_ms"], "ended_utc_ms": manifest["ended_wall_ms"],
            "rest_used": manifest["rest_used"], "reconnects": manifest["reconnects"], "resyncs": manifest["resyncs"],
            "frames": manifest["frames"], "events": sealed["events"],
            "events_sha256": sealed["events_sha256"], "frames_sha256": sealed["frames_sha256"],
            "summary_sha256": _sha(d / "replay" / "summary.json"), "window_sha256": window_sha,
            "archive_name": archive.name, "archive_sha256": _sha(archive),
            "replay": "DOUBLE_REPLAY_IDENTICAL",
        },
    }


def build(evidence_dirs, archives, report, *, now=None):
    if len(evidence_dirs) != len(archives) or not evidence_dirs:
        raise HistoryError("one archive per evidence directory")
    pairs = [pair_entry(e, a) for e, a in zip(evidence_dirs, archives)]
    kinds = {p["evidence_kind"] for p in pairs}
    instant = now or datetime.now(timezone.utc)
    doc = {
        "schema_version": SCHEMA_VERSION, "label": LABEL, "scope": "HISTORICAL_PREVIEW_READ_ONLY",
        "evidence_kind": kinds.pop() if len(kinds) == 1 else "MIXED",
        "generated_at_utc": instant.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "report": report, "pairs": pairs,
        "limits": ["NOT_LIVE", "SAMPLED_BOOK_MIDS_NOT_TRADES", "SINGLE_SHORT_SESSION_PER_PAIR",
                   "MEXC_MARGIN_ESTIMATE_ONLY", "NO_SIGNAL_NO_DECISION"],
    }
    errors = validate_history(doc)
    if errors:
        raise HistoryError(f"built publication invalid: {errors[:5]}")
    return doc


def _int(v, lo=0, hi=2**53 - 1):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _keys(o, keys):
    return isinstance(o, dict) and set(o) == set(keys)


def _candle_ok(c, points_per_window):
    if not _keys(c, ("open", "high", "low", "close", "points", "status")) or c["status"] not in CANDLE_STATUSES:
        return False
    if not _int(c["points"], 0, points_per_window):
        return False
    if c["status"] == "INCOMPLETE":
        # The replay publishes no OHLC for an incomplete candle; nothing is invented.
        return c["points"] < points_per_window and all(c[k] is None for k in ("open", "high", "low", "close"))
    if not all(isinstance(c[k], str) and DEC.match(c[k]) for k in ("open", "high", "low", "close")):
        return False
    o, h, lo, cl = (Decimal(c[k]) for k in ("open", "high", "low", "close"))
    return lo <= min(o, cl) and h >= max(o, cl) and c["points"] == points_per_window


def validate_history(doc):
    """Structural and arithmetic invariants of the publication. Returns a list of error codes."""
    e = []
    top = ("schema_version", "label", "scope", "evidence_kind", "generated_at_utc", "report", "pairs", "limits")
    if not _keys(doc, top):
        return ["TOP_KEYS"]
    if doc["schema_version"] != SCHEMA_VERSION or doc["label"] != LABEL or doc["scope"] != "HISTORICAL_PREVIEW_READ_ONLY":
        e.append("SCHEMA_ID")
    if doc["evidence_kind"] not in ("OBSERVATION", "SYNTHETIC", "MIXED"):
        e.append("EVIDENCE_KIND")
    if not isinstance(doc["generated_at_utc"], str) or not re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", doc["generated_at_utc"]):
        e.append("GENERATED_AT")
    if not isinstance(doc["pairs"], list) or not 1 <= len(doc["pairs"]) <= 8:
        return e + ["PAIRS"]
    if len({p.get("pair") for p in doc["pairs"] if isinstance(p, dict)}) != len(doc["pairs"]):
        e.append("PAIR_DUPLICATE")
    for i, p in enumerate(doc["pairs"]):
        e += [f"P{i}_{x}" for x in _pair_errors(p)]
    return e


def _pair_errors(p):
    keys = ("pair", "display_symbol", "market_type", "evidence_kind", "venues", "thresholds", "window_utc",
            "coverage", "windows", "sensitivity_composite_totals", "flux", "hypotheses", "kraken_checksums",
            "provenance")
    if not _keys(p, keys):
        return ["KEYS"]
    e = []
    if p["market_type"] != "SPOT" or [v.get("venue") for v in p["venues"]] != list(VENUES):
        e.append("VENUES")
    th = p["thresholds"]
    ppw = th.get("points_per_window") if isinstance(th, dict) else None
    if not _int(ppw, 1, 1000) or not _int(th.get("step_ms"), 1) or not _int(th.get("liveness_max_ms"), 1):
        return e + ["THRESHOLDS"]
    ws = p["windows"]
    if not isinstance(ws, list) or not 1 <= len(ws) <= 288:
        return e + ["WINDOWS"]
    for i, w in enumerate(ws):
        if not isinstance(w, dict) or w.get("index") != i:
            e.append(f"W{i}_INDEX")
            continue
        if not (_int(w.get("start_ms")) and _int(w.get("end_ms")) and w["end_ms"] - w["start_ms"] == ppw * th["step_ms"]):
            e.append(f"W{i}_BOUNDS")
        elif i and w["start_ms"] < ws[i - 1]["end_ms"]:
            e.append(f"W{i}_ORDER")
        cats = w.get("by_category")
        if not _keys(cats, CATEGORIES) or not all(_int(v) for v in cats.values()):
            e.append(f"W{i}_CATEGORIES")
            continue
        if w.get("planned") != ppw or sum(cats.values()) != ppw:
            e.append(f"W{i}_PLANNED")
        if w.get("composite") != cats["COMPOSITE"] or w.get("evaluated") != ppw - cats["NOT_EVALUATED"]:
            e.append(f"W{i}_COUNTS")
        src = w.get("by_source_state")
        if not _keys(src, VENUES) or any(not _keys(src[v], SOURCE_STATES) or sum(src[v].values()) != ppw for v in VENUES):
            e.append(f"W{i}_SOURCES")
        if not _candle_ok(w.get("candle"), ppw) or not _keys(w.get("venue_candles"), VENUES) \
                or not all(_candle_ok(w["venue_candles"][v], ppw) for v in VENUES):
            e.append(f"W{i}_CANDLE")
        sens = w.get("sensitivity_composite")
        if not _keys(sens, SENS_KEYS) or not all(_int(v, 0, ppw) for v in sens.values()) \
                or sens.get("L2s_G50bps") != w.get("composite"):
            e.append(f"W{i}_SENSITIVITY")
    if e:
        return e
    c = p["coverage"]
    if c.get("planned") != sum(w["planned"] for w in ws) or c.get("evaluated") != sum(w["evaluated"] for w in ws) \
            or c.get("composite") != sum(w["composite"] for w in ws) or c.get("candles") != len(ws) \
            or c.get("complete_composite_candles") != sum(w["candle"]["status"] == "COMPLETE" for w in ws):
        e.append("COVERAGE")
    if p["window_utc"] != {"start_ms": ws[0]["start_ms"], "end_ms": ws[-1]["end_ms"]}:
        e.append("WINDOW_UTC")
    if p["sensitivity_composite_totals"] != {k: sum(w["sensitivity_composite"][k] for w in ws) for k in SENS_KEYS}:
        e.append("SENSITIVITY_TOTALS")
    for v in VENUES:
        f = p["flux"].get(v) if isinstance(p["flux"], dict) else None
        if not isinstance(f, dict) or f.get("evaluated") != c["evaluated"] \
                or f.get("eligible") != sum(w["by_source_state"][v]["VALID"] + w["by_source_state"][v]["UNCHANGED_VERIFIED"] for w in ws) \
                or f.get("unchanged_verified") != sum(w["by_source_state"][v]["UNCHANGED_VERIFIED"] for w in ws):
            e.append(f"FLUX_{v.upper()}")
    if not e:
        majority = any(2 * p["flux"][v]["unchanged_verified"] > c["evaluated"] for v in VENUES)
        if p["hypotheses"].get("A_ORDER", {}).get("majority_unchanged_verified") is not majority:
            e.append("A_ORDER_FLAG")
    pv = p["provenance"]
    if not isinstance(pv, dict) or not HEX40.match(str(pv.get("collection_commit"))) \
            or not all(HEX64.match(str(pv.get(k))) for k in ("events_sha256", "frames_sha256", "summary_sha256", "archive_sha256")) \
            or not isinstance(pv.get("window_sha256"), list) or len(pv["window_sha256"]) != len(ws) \
            or not all(HEX64.match(str(h)) for h in pv["window_sha256"]):
        e.append("PROVENANCE")
    return e


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bbo_history")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--evidence", action="append", required=True)
    b.add_argument("--archive", action="append", required=True)
    b.add_argument("--report", required=True)
    b.add_argument("--out", required=True)
    v = sub.add_parser("validate")
    v.add_argument("file")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "build":
            doc = build(a.evidence, a.archive, a.report)
            raw = (json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()
            if len(raw) > MAX_BYTES:
                raise HistoryError("publication too large")
            Path(a.out).write_bytes(raw)
            print(hashlib.sha256(raw).hexdigest(), a.out)
            return 0
        errors = validate_history(_load(a.file))
        print(json.dumps({"valid": not errors, "errors": errors}))
        return 0 if not errors else 1
    except (HistoryError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
