"""
02_score_distribution.py — Distribution des scores réels + seuil optimal.

Lit databases/mistake_memory.jsonl et databases/paper_trades.jsonl
pour calculer la vraie distribution des scores de signaux générés.

Suggère le seuil optimal = percentile qui maximise le ratio win_rate / volume.

Usage :
    python S2/02_score_distribution.py
    python S2/02_score_distribution.py --source mistake  # seulement mistake_memory
    python S2/02_score_distribution.py --source paper    # seulement paper_trades
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

MM_PATH = "databases/mistake_memory.jsonl"
PT_PATH = "databases/paper_trades.jsonl"


def load_mistake_memory() -> list[dict]:
    p = Path(MM_PATH)
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def load_paper_trades() -> list[dict]:
    p = Path(PT_PATH)
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    d = json.loads(line)
                    # Normaliser le format paper_trades vers mistake_memory format
                    if d.get("event") == "CLOSE" and d.get("pnl_pct") is not None:
                        rows.append(
                            {
                                "score": d.get("score", 0),
                                "pnl_pct": d.get("pnl_pct", 0),
                                "regime": d.get("regime", "unknown"),
                            }
                        )
                except json.JSONDecodeError:
                    pass
    return rows


def analyze(trades: list[dict]) -> None:
    if not trades:
        print("[score_distribution] Aucune donnée disponible.")
        return

    valid = [
        t for t in trades if isinstance(t.get("score"), (int, float)) and t["score"] > 0
    ]
    if not valid:
        print("[score_distribution] Scores absents ou nuls dans toutes les entrées.")
        return

    scores = sorted(t["score"] for t in valid)
    total = len(scores)

    mn, mx = scores[0], scores[-1]
    avg = sum(scores) / total
    p25 = scores[total // 4]
    p50 = scores[total // 2]
    p75 = scores[total * 3 // 4]
    p90 = scores[int(total * 0.9)]

    print(f"\n{'='*60}")
    print(f"  SCORE DISTRIBUTION — {total} signaux")
    print(f"{'='*60}")
    print(
        f"  min={mn}  p25={p25}  p50={p50}  p75={p75}  p90={p90}  max={mx}  avg={avg:.1f}"
    )

    # ── Histogramme en tranches de 5 ──────────────────────────────────────────
    print("\n  Histogramme (tranches de 5 pts):")
    buckets: dict[int, list[float]] = defaultdict(list)
    for t in valid:
        b = (int(t["score"]) // 5) * 5
        buckets[b].append(t.get("pnl_pct", 0))

    for b in sorted(buckets):
        pnls = buckets[b]
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / n * 100 if n else 0
        bar = "█" * min(30, n)
        wr_indicator = "✓" if wr >= 50 else ("~" if wr >= 35 else "✗")
        print(
            f"    [{b:>2}-{b+4:<2}]  {n:>4} signaux  WR={wr:>4.0f}%  {wr_indicator}  {bar}"
        )

    # ── Seuil optimal ─────────────────────────────────────────────────────────
    print("\n  Analyse seuil par seuil (trades conservés si score >= seuil):")
    print(f"    {'Seuil':>6}  {'Signaux':>8}  {'Win Rate':>9}  {'Recommandé'}")
    print(f"    {'-'*50}")

    best_threshold = None
    best_score_metric = -1.0

    for threshold in range(mn, mx + 1, 5):
        subset = [t for t in valid if t["score"] >= threshold]
        if len(subset) < 5:
            break
        wins = sum(1 for t in subset if t.get("pnl_pct", 0) > 0)
        wr = wins / len(subset)
        volume_ratio = len(subset) / total
        # Metric: cherche à maximiser win_rate * sqrt(volume)
        metric = wr * (volume_ratio**0.5)
        if metric > best_score_metric:
            best_score_metric = metric
            best_threshold = threshold
        tag = " ← OPTIMAL" if threshold == best_threshold else ""
        print(f"    {threshold:>6}  {len(subset):>8}  {wr:>8.0%}  {tag}")

    if best_threshold is not None:
        print(f"\n  RECOMMANDATION: threshold optimal = {best_threshold}")
        subset_opt = [t for t in valid if t["score"] >= best_threshold]
        wr_opt = sum(1 for t in subset_opt if t.get("pnl_pct", 0) > 0) / len(subset_opt)
        print(
            f"  → {len(subset_opt)}/{total} signaux conservés ({len(subset_opt)/total:.0%})"
        )
        print(f"  → Win rate attendu : {wr_opt:.0%}")
        print(
            f"\n  Pour appliquer: mettre REGIME_SIDEWAYS_MIN_SCORE={best_threshold} dans .env"
        )
        print(f"                  ou SIGNAL_MIN_SCORE={best_threshold}")

    # ── Score actuel vs signaux générés ───────────────────────────────────────
    print(f"\n  Note: score max observé dans les données = {mx}")
    if mx < 66:
        print(f"  ⚠️  PROBLÈME DÉTECTÉ: seuil gate > score max → 0 trade possible!")
        print(
            f"  → Réduire le seuil gate sous {mx} ou améliorer la qualité des signaux."
        )

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Distribution des scores de signaux")
    parser.add_argument(
        "--source",
        choices=["mistake", "paper", "both"],
        default="both",
        help="Source de données",
    )
    args = parser.parse_args()

    trades: list[dict] = []
    if args.source in ("mistake", "both"):
        mm = load_mistake_memory()
        print(f"[score_distribution] mistake_memory: {len(mm)} entrées chargées")
        trades += mm
    if args.source in ("paper", "both"):
        pt = load_paper_trades()
        print(f"[score_distribution] paper_trades:   {len(pt)} clôtures chargées")
        trades += pt

    analyze(trades)


if __name__ == "__main__":
    main()
