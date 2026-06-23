"""
delta_sensitivity.py — Analyse de sensibilité du delta sur le nombre de trades.

Lit cycle_data.jsonl et simule combien de trades auraient été acceptés
sous différentes hypothèses de delta (governor_delta + regret_delta).

Usage:
    python -X utf8 scripts/delta_sensitivity.py
    python -X utf8 scripts/delta_sensitivity.py --file databases/cycle_data.jsonl
    python -X utf8 scripts/delta_sensitivity.py --hours 24
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

# ── Bases de score par régime (miroir de market_regime_classifier.py) ─────────
_REGIME_BASES: dict[str, int] = {
    "sideways": int(os.getenv("REGIME_SIDEWAYS_MIN_SCORE", "60")),
    "RANGE": int(os.getenv("REGIME_SIDEWAYS_MIN_SCORE", "60")),
    "bull_trend": 72,
    "TREND_BULL": 72,
    "bear_trend": 68,
    "TREND_BEAR": 68,
    "high_volatility_regime": 68,
    "VOLATILE": 68,
    "flash_crash": 999,
    "unknown": 72,
    "UNKNOWN": 72,
}
_ABSOLUTE_FLOOR = int(os.getenv("REGIME_ABSOLUTE_FLOOR", "55"))


def effective_min_score(regime: str, delta: int) -> int:
    base = _REGIME_BASES.get(regime, 72)
    if base >= 999:
        return 999
    return max(base + delta, _ABSOLUTE_FLOOR)


def load_signals(path: Path, hours: float | None) -> list[dict]:
    """Extrait tous les signaux non-HOLD de cycle_data.jsonl."""
    cutoff_ts = (time.time() - hours * 3600) if hours else None
    signals: list[dict] = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cycle = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = cycle.get("ts", 0)
            if cutoff_ts and ts < cutoff_ts:
                continue

            for sym in cycle.get("symbols", []):
                score = sym.get("score", 0)
                signal = sym.get("signal", "HOLD")
                regime = sym.get("regime", "unknown")
                gate_allowed = sym.get("gate_allowed", False)
                confirmed = sym.get("confirmed", False)

                # Ne garder que les signaux directionnels (pas HOLD)
                if signal == "HOLD" or score < 50:
                    continue

                signals.append(
                    {
                        "ts": ts,
                        "symbol": sym.get("symbol", ""),
                        "score": score,
                        "signal": signal,
                        "regime": regime,
                        "gate_allowed": gate_allowed,
                        "confirmed": confirmed,
                        "cycle": cycle.get("cycle", 0),
                    }
                )

    return signals


def run_sensitivity(signals: list[dict], deltas: list[int]) -> None:
    if not signals:
        print("Aucun signal trouvé.")
        return

    total = len(signals)
    hours_span = (
        (signals[-1]["ts"] - signals[0]["ts"]) / 3600 if len(signals) > 1 else 0
    )
    n_cycles = len({s["cycle"] for s in signals})

    print(f"\n{'='*60}")
    print(f"  ANALYSE DE SENSIBILITÉ DELTA")
    print(f"{'='*60}")
    print(f"  Signaux directionnels (score≥50) : {total}")
    print(f"  Cycles analysés                  : {n_cycles}")
    print(f"  Durée couverte                   : {hours_span:.1f}h")

    # Distribution des scores
    score_bins = defaultdict(int)
    for s in signals:
        bucket = (s["score"] // 5) * 5
        score_bins[bucket] += 1

    print(f"\n  Distribution des scores :")
    for bucket in sorted(score_bins):
        bar = "█" * (score_bins[bucket])
        print(f"    {bucket:2d}-{bucket+4:2d} : {score_bins[bucket]:4d}  {bar}")

    # Distribution des régimes
    regime_counts: dict[str, int] = defaultdict(int)
    for s in signals:
        regime_counts[s["regime"]] += 1
    print(f"\n  Distribution des régimes :")
    for r, c in sorted(regime_counts.items(), key=lambda x: -x[1]):
        print(f"    {r:<30s} : {c:4d} ({100*c/total:.0f}%)")

    # Analyse de sensibilité
    print(f"\n{'─'*60}")
    print(f"  {'Delta':>6}  {'Acceptés':>10}  {'%':>6}  Seuils effectifs")
    print(f"{'─'*60}")

    for delta in deltas:
        accepted = 0
        regime_accepted: dict[str, int] = defaultdict(int)
        for s in signals:
            thresh = effective_min_score(s["regime"], delta)
            if s["score"] >= thresh:
                accepted += 1
                regime_accepted[s["regime"]] += 1

        pct = 100 * accepted / total if total else 0
        # Affiche les seuils effectifs pour les régimes principaux
        sw_thr = effective_min_score("sideways", delta)
        bt_thr = effective_min_score("bull_trend", delta)
        be_thr = effective_min_score("bear_trend", delta)
        label = f"sideways≥{sw_thr}  bull≥{bt_thr}  bear≥{be_thr}"
        marker = "  ← ESTIMÉ ACTUEL" if delta == 6 else ""

        print(f"  {delta:>+6d}  {accepted:>10d}  {pct:>5.1f}%  {label}{marker}")

    # Zoom : combien de signaux manquent de 1 point ?
    print(f"\n{'─'*60}")
    print(f"  ZOOM : Signaux à N points du seuil (delta=+6)")
    print(f"{'─'*60}")
    for gap in [1, 2, 3]:
        near_miss = sum(
            1
            for s in signals
            if effective_min_score(s["regime"], 6) - s["score"] == gap
        )
        print(f"  Manquent de {gap} point(s) : {near_miss}")

    # Cross-table : régime × score bucket par delta
    print(f"\n{'─'*60}")
    print(f"  CROSS-TABLE REGIME x SCORE  (signaux acceptés par delta)")
    print(f"{'─'*60}")

    # Buckets de score à 5 pts
    all_buckets = sorted({(s["score"] // 5) * 5 for s in signals})
    all_regimes = sorted(regime_counts.keys(), key=lambda r: -regime_counts[r])

    for delta in deltas:
        sw = effective_min_score("sideways", delta)
        bt = effective_min_score("bull_trend", delta)
        be = effective_min_score("bear_trend", delta)
        total_acc = sum(
            1 for s in signals if s["score"] >= effective_min_score(s["regime"], delta)
        )
        pct_acc = 100 * total_acc / total if total else 0
        print(f"\n  delta={delta:+d}  seuils: sideways>={sw}  bull>={bt}  bear>={be}")
        print(f"  Total acceptés: {total_acc}/{total}  ({pct_acc:.0f}%)")

        # Header
        bucket_labels = [f"{b}-{b+4}" for b in all_buckets]
        header = (
            f"  {'Regime':<22}"
            + "".join(f"  {lab:>6}" for lab in bucket_labels)
            + "  TOTAL"
        )
        print(header)
        print(f"  {'-'*len(header)}")

        for regime in all_regimes:
            r_sigs = [s for s in signals if s["regime"] == regime]
            row = f"  {regime:<22}"
            r_total = 0
            for b in all_buckets:
                bucket_sigs = [s for s in r_sigs if (s["score"] // 5) * 5 == b]
                accepted = sum(
                    1
                    for s in bucket_sigs
                    if s["score"] >= effective_min_score(s["regime"], delta)
                )
                r_total += accepted
                cell = f"{accepted}/{len(bucket_sigs)}" if bucket_sigs else "   -"
                row += f"  {cell:>6}"
            row += f"  {r_total:>5}"
            print(row)

    # Détail par régime avec delta référence vs delta=0
    ref_delta = deltas[-1] if deltas else 6
    print(f"\n{'─'*60}")
    print(f"  IMPACT PAR REGIME  (delta={ref_delta:+d} vs delta=0)")
    print(f"{'─'*60}")
    for regime in sorted(regime_counts.keys(), key=lambda r: -regime_counts[r]):
        r_sigs = [s for s in signals if s["regime"] == regime]
        acc_ref = sum(
            1 for s in r_sigs if s["score"] >= effective_min_score(regime, ref_delta)
        )
        acc_0 = sum(1 for s in r_sigs if s["score"] >= effective_min_score(regime, 0))
        n = len(r_sigs)
        print(
            f"  {regime:<30s} N={n:4d}  "
            f"delta{ref_delta:+d}->{acc_ref:4d} ({100*acc_ref/n:.0f}%)  "
            f"delta+0->{acc_0:4d} ({100*acc_0/n:.0f}%)"
        )

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sensibilité delta sur cycle_data.jsonl"
    )
    parser.add_argument(
        "--file",
        default="databases/cycle_data.jsonl",
        help="Chemin vers cycle_data.jsonl",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=None,
        help="Fenêtre temporelle en heures (ex: 24 pour les 24 dernières heures)",
    )
    parser.add_argument(
        "--deltas",
        default="-2,0,+3,+6,+9",
        help="Valeurs de delta à simuler, séparées par virgule (défaut: -2,0,+3,+6,+9)",
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Fichier introuvable : {path}", file=sys.stderr)
        sys.exit(1)

    deltas = [int(d.strip().lstrip("+")) for d in args.deltas.split(",")]

    signals = load_signals(path, args.hours)
    run_sensitivity(signals, deltas)


if __name__ == "__main__":
    main()
