#!/usr/bin/env python3
"""
regret_horizons_analysis.py — Analyse multi-horizon du dataset de regret v2.

Equivalent de regret_audit.py pour les données v2 (regret_horizons_*.jsonl).
Lecture seule — aucune influence sur le moteur (ADR-0007).

Lenses :
  [1] PANORAMA        — MW / GR / NEUTRAL par horizon (matrice complète)
  [2] BLOCKER         — par couche bloquante × verdict au canonical horizon
  [3] REGIME          — par régime de marché × verdict
  [4] SCORE BIN       — par tranche de score × verdict (la question du user)
  [5] CROSS-ANALYSIS  — blocker × score bin → missed_win rate
  [6] SYMBOLES        — top symboles par missed_win_count et regret_score
  [7] TRAJECTOIRE     — évolution hebdomadaire MW rate

Usage :
    python3 scripts/regret_horizons_analysis.py
    python3 scripts/regret_horizons_analysis.py --dir /path/to/regret/
    python3 scripts/regret_horizons_analysis.py --since-days 14
    python3 scripts/regret_horizons_analysis.py --horizon 4h
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.data_quality import CLEAN_DATA_SINCE_ACTIVE

_CANONICAL_HORIZON = "1h"
_SCORE_BINS: list[tuple[float, float, str]] = [
    (0, 60, "<60"),
    (60, 65, "60-64"),
    (65, 70, "65-69"),
    (70, 75, "70-74"),
    (75, 80, "75-79"),
    (80, 85, "80-84"),
    (85, 90, "85-89"),
    (90, 100, "90+"),
]
_HORIZONS_ORDER = ["5m", "15m", "30m", "1h", "4h", "12h", "24h"]

W = 78


def _score_bin(score: float) -> str:
    for lo, hi, label in _SCORE_BINS:
        if lo <= score < hi:
            return label
    if score >= 100:
        return "90+"
    return "<?>"


def _ts_to_week(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-W%V")


def _ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def _pct(num: int, den: int) -> str:
    if den == 0:
        return "   -"
    return f"{num / den * 100:4.0f}%"


def _load_records(regret_dir: Path, since_ts: float) -> list[dict[str, Any]]:
    pattern = str(regret_dir / "regret_horizons_*.jsonl")
    records: list[dict[str, Any]] = []
    for fp in sorted(glob.glob(pattern)):
        try:
            with open(fp, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = d.get("ts_signal")
                    if ts is None:
                        continue
                    if float(ts) < since_ts:
                        continue
                    records.append(d)
        except FileNotFoundError:
            continue
    return records


def _horizon_verdict(record: dict, horizon: str) -> str | None:
    h = (record.get("horizons") or {}).get(horizon)
    if h is None:
        return None
    return h.get("regret_type")


# ── Lens 1 : Panorama multi-horizon ─────────────────────────────────────────


def lens_panorama(records: list[dict], horizon: str = _CANONICAL_HORIZON) -> None:
    print("=" * W)
    print("  [1] PANORAMA — Verdicts par horizon")
    print("=" * W)

    stats: dict[str, Counter] = {h: Counter() for h in _HORIZONS_ORDER}
    for r in records:
        horizons = r.get("horizons") or {}
        for h in _HORIZONS_ORDER:
            hr = horizons.get(h)
            if hr is None:
                stats[h]["ABSENT"] += 1
            else:
                stats[h][hr.get("regret_type", "UNKNOWN")] += 1

    header = f"{'Horizon':<8} {'MW':>6} {'GR':>6} {'NEU':>6} {'ABS':>5} {'Total':>6}  {'MW%':>5} {'GR%':>5}"
    print(header)
    print("-" * len(header))
    for h in _HORIZONS_ORDER:
        c = stats[h]
        mw, gr, neu, ab = c["MISSED_WIN"], c["GOOD_REFUSAL"], c["NEUTRAL"], c["ABSENT"]
        evaluated = mw + gr + neu
        total = evaluated + ab
        print(
            f"{h:<8} {mw:>6} {gr:>6} {neu:>6} {ab:>5} {total:>6}"
            f"  {_pct(mw, evaluated)} {_pct(gr, evaluated)}"
        )
    print()

    # Regret score distribution at canonical horizon
    scores: list[float] = []
    for r in records:
        hr = (r.get("horizons") or {}).get(horizon)
        if hr and hr.get("regret_type") == "MISSED_WIN":
            scores.append(hr.get("regret_score", 0.0))
    if scores:
        scores.sort()
        p50 = scores[len(scores) // 2]
        p90 = scores[int(len(scores) * 0.9)]
        avg = sum(scores) / len(scores)
        print(f"  Regret score (MISSED_WIN @ {horizon}): "
              f"avg={avg:.3f}  p50={p50:.3f}  p90={p90:.3f}  max={max(scores):.3f}")
    print()


# ── Lens 2 : Blocker ────────────────────────────────────────────────────────


def lens_blocker(records: list[dict], horizon: str) -> None:
    print("=" * W)
    print(f"  [2] BLOCKER — first_blocker × verdict @ {horizon}")
    print("=" * W)

    by_blocker: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        fb = r.get("first_blocker") or "none"
        verdict = _horizon_verdict(r, horizon) or "ABSENT"
        by_blocker[fb][verdict] += 1

    header = f"{'Blocker':<16} {'MW':>6} {'GR':>6} {'NEU':>6} {'Total':>6}  {'MW%':>5}"
    print(header)
    print("-" * len(header))
    for fb in sorted(by_blocker, key=lambda b: -sum(by_blocker[b].values())):
        c = by_blocker[fb]
        mw, gr, neu = c["MISSED_WIN"], c["GOOD_REFUSAL"], c["NEUTRAL"]
        total = mw + gr + neu
        print(f"{fb:<16} {mw:>6} {gr:>6} {neu:>6} {total:>6}  {_pct(mw, total)}")
    print()


# ── Lens 3 : Regime ─────────────────────────────────────────────────────────


def lens_regime(records: list[dict], horizon: str) -> None:
    print("=" * W)
    print(f"  [3] REGIME — régime de marché × verdict @ {horizon}")
    print("=" * W)

    by_regime: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        regime = r.get("regime") or "unknown"
        verdict = _horizon_verdict(r, horizon) or "ABSENT"
        by_regime[regime][verdict] += 1

    header = f"{'Regime':<24} {'MW':>6} {'GR':>6} {'NEU':>6} {'Total':>6}  {'MW%':>5}"
    print(header)
    print("-" * len(header))
    for reg in sorted(by_regime, key=lambda b: -sum(by_regime[b].values())):
        c = by_regime[reg]
        mw, gr, neu = c["MISSED_WIN"], c["GOOD_REFUSAL"], c["NEUTRAL"]
        total = mw + gr + neu
        print(f"{reg:<24} {mw:>6} {gr:>6} {neu:>6} {total:>6}  {_pct(mw, total)}")
    print()


# ── Lens 4 : Score bin ──────────────────────────────────────────────────────


def lens_score_bin(records: list[dict], horizon: str) -> None:
    print("=" * W)
    print(f"  [4] SCORE BIN — tranche de score × verdict @ {horizon}")
    print("=" * W)

    by_bin: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        score = r.get("score")
        if score is None:
            continue
        sb = _score_bin(float(score))
        verdict = _horizon_verdict(r, horizon) or "ABSENT"
        by_bin[sb][verdict] += 1

    labels = [label for _, _, label in _SCORE_BINS]
    header = f"{'Score':>8} {'MW':>6} {'GR':>6} {'NEU':>6} {'Total':>6}  {'MW%':>5} {'GR%':>5} {'MW-GR':>6}"
    print(header)
    print("-" * len(header))
    for label in labels:
        c = by_bin.get(label, Counter())
        mw, gr, neu = c["MISSED_WIN"], c["GOOD_REFUSAL"], c["NEUTRAL"]
        total = mw + gr + neu
        delta = mw - gr
        print(
            f"{label:>8} {mw:>6} {gr:>6} {neu:>6} {total:>6}"
            f"  {_pct(mw, total)} {_pct(gr, total)} {delta:>+6}"
        )

    # Avg return_pct per score bin for MISSED_WIN
    print()
    print(f"  Retours moyens des MISSED_WIN par score bin @ {horizon} :")
    for label in labels:
        returns = []
        for r in records:
            score = r.get("score")
            if score is None:
                continue
            if _score_bin(float(score)) != label:
                continue
            hr = (r.get("horizons") or {}).get(horizon)
            if hr and hr.get("regret_type") == "MISSED_WIN":
                returns.append(hr.get("return_pct", 0.0))
        if returns:
            avg_r = sum(returns) / len(returns)
            max_r = max(returns)
            print(f"    {label:>8} : n={len(returns):<5} avg_return={avg_r:+.2f}%  max={max_r:+.2f}%")
    print()


# ── Lens 5 : Cross-analysis blocker × score bin ────────────────────────────


def lens_cross(records: list[dict], horizon: str) -> None:
    print("=" * W)
    print(f"  [5] CROSS — blocker × score bin → MW rate @ {horizon}")
    print("=" * W)

    cells: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in records:
        fb = r.get("first_blocker") or "none"
        score = r.get("score")
        if score is None:
            continue
        sb = _score_bin(float(score))
        verdict = _horizon_verdict(r, horizon) or "ABSENT"
        cells[(fb, sb)][verdict] += 1

    blockers = sorted(
        {k[0] for k in cells},
        key=lambda b: -sum(sum(cells[(b, s)].values()) for s in [l for _, _, l in _SCORE_BINS]),
    )
    labels = [label for _, _, label in _SCORE_BINS]

    header = f"{'Blocker':<14}" + "".join(f" {l:>9}" for l in labels)
    print(header)
    print("-" * len(header))
    for fb in blockers:
        row = f"{fb:<14}"
        for label in labels:
            c = cells.get((fb, label), Counter())
            mw = c["MISSED_WIN"]
            total = mw + c["GOOD_REFUSAL"] + c["NEUTRAL"]
            if total == 0:
                cell = "·"
            else:
                cell = f"{mw}/{total} {mw / total * 100:.0f}%"
            row += f" {cell:>9}"
        print(row)
    print()


# ── Lens 6 : Symboles ──────────────────────────────────────────────────────


def lens_symbols(records: list[dict], horizon: str, top_n: int = 15) -> None:
    print("=" * W)
    print(f"  [6] SYMBOLES — top {top_n} par MISSED_WIN @ {horizon}")
    print("=" * W)

    by_sym: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"mw": 0, "gr": 0, "neu": 0, "regret_sum": 0.0, "returns": []}
    )
    for r in records:
        sym = r.get("symbol") or "?"
        hr = (r.get("horizons") or {}).get(horizon)
        if hr is None:
            continue
        rt = hr.get("regret_type", "NEUTRAL")
        if rt == "MISSED_WIN":
            by_sym[sym]["mw"] += 1
            by_sym[sym]["regret_sum"] += hr.get("regret_score", 0.0)
            by_sym[sym]["returns"].append(hr.get("return_pct", 0.0))
        elif rt == "GOOD_REFUSAL":
            by_sym[sym]["gr"] += 1
        else:
            by_sym[sym]["neu"] += 1

    ranked = sorted(by_sym.items(), key=lambda x: -x[1]["mw"])[:top_n]
    header = f"{'Symbol':<14} {'MW':>5} {'GR':>5} {'Total':>5}  {'MW%':>5} {'AvgRegret':>9} {'AvgRet%':>8}"
    print(header)
    print("-" * len(header))
    for sym, s in ranked:
        total = s["mw"] + s["gr"] + s["neu"]
        avg_regret = s["regret_sum"] / s["mw"] if s["mw"] else 0
        avg_ret = sum(s["returns"]) / len(s["returns"]) if s["returns"] else 0
        print(
            f"{sym:<14} {s['mw']:>5} {s['gr']:>5} {total:>5}"
            f"  {_pct(s['mw'], total)} {avg_regret:>9.3f} {avg_ret:>+7.2f}%"
        )
    print()


# ── Lens 7 : Trajectoire hebdomadaire ──────────────────────────────────────


def lens_trajectory(records: list[dict], horizon: str) -> None:
    print("=" * W)
    print(f"  [7] TRAJECTOIRE — MW rate hebdomadaire @ {horizon}")
    print("=" * W)

    by_week: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        ts = r.get("ts_signal")
        if ts is None:
            continue
        week = _ts_to_week(float(ts))
        verdict = _horizon_verdict(r, horizon) or "ABSENT"
        by_week[week][verdict] += 1

    weeks = sorted(by_week.keys())
    header = f"{'Week':<10} {'MW':>5} {'GR':>5} {'NEU':>5} {'Total':>5}  {'MW%':>5} {'GR%':>5} {'Bar'}"
    print(header)
    print("-" * len(header))
    for week in weeks:
        c = by_week[week]
        mw, gr, neu = c["MISSED_WIN"], c["GOOD_REFUSAL"], c["NEUTRAL"]
        total = mw + gr + neu
        mw_rate = mw / total if total else 0
        bar = "#" * int(mw_rate * 30) + "." * (30 - int(mw_rate * 30))
        print(
            f"{week:<10} {mw:>5} {gr:>5} {neu:>5} {total:>5}"
            f"  {_pct(mw, total)} {_pct(gr, total)} {bar}"
        )
    print()


# ── Summary ─────────────────────────────────────────────────────────────────


def summary(records: list[dict], horizon: str) -> None:
    print("=" * W)
    print(f"  SUMMARY — dataset v2, canonical horizon = {horizon}")
    print("=" * W)

    n = len(records)
    if n == 0:
        print("  Aucun enregistrement trouvé.")
        return

    ts_vals = [float(r["ts_signal"]) for r in records if r.get("ts_signal")]
    ts_vals.sort()
    first = _ts_to_iso(ts_vals[0]) if ts_vals else "?"
    last = _ts_to_iso(ts_vals[-1]) if ts_vals else "?"

    mw_total = sum(
        1 for r in records
        if _horizon_verdict(r, horizon) == "MISSED_WIN"
    )
    gr_total = sum(
        1 for r in records
        if _horizon_verdict(r, horizon) == "GOOD_REFUSAL"
    )
    neu_total = sum(
        1 for r in records
        if _horizon_verdict(r, horizon) == "NEUTRAL"
    )
    absent = n - mw_total - gr_total - neu_total
    evaluated = mw_total + gr_total + neu_total

    symbols = {r.get("symbol") for r in records}
    blockers = {r.get("first_blocker") for r in records}
    regimes = {r.get("regime") for r in records}

    print(f"  Records         : {n}")
    print(f"  Période         : {first}  →  {last}")
    print(f"  Symbols uniques : {len(symbols)}")
    print(f"  Blockers uniques: {len(blockers)}")
    print(f"  Regimes uniques : {len(regimes)}")
    print()
    print(f"  @ {horizon}:")
    print(f"    Evaluated     : {evaluated}  (absent: {absent})")
    print(f"    MISSED_WIN    : {mw_total:>6}  ({_pct(mw_total, evaluated).strip()})")
    print(f"    GOOD_REFUSAL  : {gr_total:>6}  ({_pct(gr_total, evaluated).strip()})")
    print(f"    NEUTRAL       : {neu_total:>6}  ({_pct(neu_total, evaluated).strip()})")
    if mw_total + gr_total > 0:
        precision = gr_total / (mw_total + gr_total)
        print(f"    Precision     : {precision:.1%}  (GR / (MW+GR) — efficacité du refus)")
    print()


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse multi-horizon du dataset de regret v2."
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path("databases/regret"),
        help="Répertoire des fichiers regret_horizons_*.jsonl",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Limiter aux N derniers jours (sinon : depuis CLEAN_DATA_SINCE_V4)",
    )
    parser.add_argument(
        "--horizon",
        default=_CANONICAL_HORIZON,
        help=f"Horizon canonique pour les lenses 2-7 (défaut: {_CANONICAL_HORIZON})",
    )
    parser.add_argument(
        "--top-symbols",
        type=int,
        default=15,
        help="Nombre de symboles à afficher dans la lens 6 (défaut: 15)",
    )
    parser.add_argument(
        "--lens",
        type=int,
        nargs="*",
        default=None,
        help="Lenses à afficher (1-7, défaut: toutes)",
    )
    args = parser.parse_args()

    if args.since_days is not None:
        import time
        since_ts = time.time() - args.since_days * 86400
    else:
        since_ts = CLEAN_DATA_SINCE_ACTIVE.timestamp()

    records = _load_records(args.dir, since_ts)

    since_label = (
        f"last {args.since_days} days"
        if args.since_days
        else f"CLEAN_DATA_SINCE_V4 ({CLEAN_DATA_SINCE_ACTIVE.isoformat()})"
    )

    print()
    print(f"  regret_horizons_analysis.py — {len(records)} records since {since_label}")
    print(f"  Source: {args.dir.resolve()}")
    print()

    if not records:
        print("  Aucun enregistrement trouvé. Vérifiez le chemin et la date.")
        return

    lenses = args.lens or [0, 1, 2, 3, 4, 5, 6, 7]

    if 0 in lenses:
        summary(records, args.horizon)
    if 1 in lenses:
        lens_panorama(records, args.horizon)
    if 2 in lenses:
        lens_blocker(records, args.horizon)
    if 3 in lenses:
        lens_regime(records, args.horizon)
    if 4 in lenses:
        lens_score_bin(records, args.horizon)
    if 5 in lenses:
        lens_cross(records, args.horizon)
    if 6 in lenses:
        lens_symbols(records, args.horizon, top_n=args.top_symbols)
    if 7 in lenses:
        lens_trajectory(records, args.horizon)


if __name__ == "__main__":
    main()
