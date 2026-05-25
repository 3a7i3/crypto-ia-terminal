"""
04_conviction_calibrator.py — Calibration des niveaux de conviction et tailles.

Calcule, par score percentile, le win rate observé et suggère les seuils
SKIP / LOW / MEDIUM / HIGH / STRONG basés sur les données réelles.

Usage :
    python S2/04_conviction_calibrator.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

MM_PATH = "databases/mistake_memory.jsonl"

# Niveaux de conviction actuels (source: conviction_engine.py)
CONVICTION_LEVELS = {
    "SKIP": 0.0,
    "LOW": 0.25,
    "MEDIUM": 0.5,
    "HIGH": 0.75,
    "STRONG": 1.0,
    "ULTRA": 1.25,
}


def load_trades() -> list[dict]:
    p = Path(MM_PATH)
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def analyze() -> None:
    trades = load_trades()
    valid = [
        t for t in trades if isinstance(t.get("score"), (int, float)) and t["score"] > 0
    ]

    if not valid:
        print("[conviction_calibrator] Aucune donnée avec score valide.")
        return

    total = len(valid)
    scores = sorted(t["score"] for t in valid)
    mn, mx = scores[0], scores[-1]

    print(f"\n{'='*60}")
    print(f"  CONVICTION CALIBRATOR — {total} trades (scores {mn}-{mx})")
    print(f"{'='*60}")

    # ── Win rate par tranche de 5 pts ──────────────────────────────────────────
    buckets: dict[int, list[float]] = defaultdict(list)
    for t in valid:
        b = (int(t["score"]) // 5) * 5
        buckets[b].append(t.get("pnl_pct", 0))

    print("\n  Win rate par score (tranches 5 pts):")
    print(
        f"    {'Score':>8}  {'N':>5}  {'Win Rate':>9}  {'Avg PnL':>9}  {'Suggestion taille'}"
    )
    print(f"    {'─'*60}")

    for b in sorted(buckets):
        pnls = buckets[b]
        n = len(pnls)
        wr = sum(1 for p in pnls if p > 0) / n
        avg_pnl = sum(pnls) / n

        # Suggestion taille basée sur Kelly simplifié : f = wr - (1-wr)/ratio
        # Avec ratio moyen de ~1.5 (TP/SL)
        ratio = 1.5
        kelly = max(0, wr - (1 - wr) / ratio)
        size_pct = min(1.0, kelly * 2)  # demi-Kelly, cap 100%

        if wr >= 0.60:
            conviction_tag = "→ STRONG (1.25×)"
        elif wr >= 0.50:
            conviction_tag = "→ HIGH   (0.75×)"
        elif wr >= 0.40:
            conviction_tag = "→ MEDIUM (0.50×)"
        elif wr >= 0.30:
            conviction_tag = "→ LOW    (0.25×)"
        else:
            conviction_tag = "→ SKIP   (0.00×)"

        print(
            f"    [{b:>2}-{b+4:<2}]  {n:>5}  {wr:>8.0%}  {avg_pnl:>+8.2%}  {conviction_tag}"
        )

    # ── Seuils recommandés ────────────────────────────────────────────────────
    print("\n  SEUILS DE SCORE RECOMMANDÉS PAR CONVICTION:")

    # Trouver les percentiles de score où WR dépasse les seuils
    thresholds: dict[str, int] = {}
    all_buckets_sorted = sorted(buckets.items())

    for level_name, min_wr in [
        ("STRONG (WR≥60%)", 0.60),
        ("HIGH   (WR≥50%)", 0.50),
        ("MEDIUM (WR≥40%)", 0.40),
        ("LOW    (WR≥30%)", 0.30),
    ]:
        for b, pnls in all_buckets_sorted:
            n = len(pnls)
            if n < 3:
                continue
            wr = sum(1 for p in pnls if p > 0) / n
            if wr >= min_wr:
                thresholds[level_name] = b
                break

    for level_name, threshold in thresholds.items():
        print(f"    {level_name}  score >= {threshold}")

    if not thresholds:
        print("    ⚠️  Win rate insuffisant pour calibrer les niveaux.")
        print("    → Collecter plus de trades ou améliorer le scorer.")

    # ── Score moyen par conviction existante ──────────────────────────────────
    by_conviction: dict[str, list] = defaultdict(list)
    for t in valid:
        cv = t.get("conviction_level", "unknown")
        by_conviction[cv].append((t["score"], t.get("pnl_pct", 0)))

    if any(len(v) >= 3 for v in by_conviction.values()):
        print("\n  Win rate par niveau de conviction actuel:")
        for cv in ["low", "medium", "high", "ultra", "unknown"]:
            data = by_conviction.get(cv, [])
            if len(data) < 3:
                continue
            scores_cv = [d[0] for d in data]
            pnls_cv = [d[1] for d in data]
            wr_cv = sum(1 for p in pnls_cv if p > 0) / len(pnls_cv)
            avg_score = sum(scores_cv) / len(scores_cv)
            print(
                f"    {cv:<10}  n={len(data):>4}  WR={wr_cv:.0%}  "
                f"score_moyen={avg_score:.1f}"
            )

    # ── Recommandation finale ──────────────────────────────────────────────────
    print(f"\n  RECOMMANDATION:")
    if mn == mx:
        print(f"  ⚠️  Tous les scores identiques ({mn}) — vérifier le scorer.")
    elif mx < 70:
        print(
            f"  ⚠️  Score max = {mx} < 70 → scorer sous-calibré ou seuil gate trop élevé."
        )
        print(f"     → Baisser SIGNAL_MIN_SCORE ou REGIME_SIDEWAYS_MIN_SCORE")
    else:
        best_wr = 0.0
        best_bucket = mn
        for b, pnls in buckets.items():
            if len(pnls) >= 3:
                wr = sum(1 for p in pnls if p > 0) / len(pnls)
                if wr > best_wr:
                    best_wr = wr
                    best_bucket = b
        print(
            f"  Meilleure tranche: score [{best_bucket}-{best_bucket+4}] → WR={best_wr:.0%}"
        )

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    analyze()
