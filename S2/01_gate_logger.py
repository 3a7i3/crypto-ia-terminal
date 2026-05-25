"""
01_gate_logger.py — Analyse des refus du GlobalRiskGate.

Lit databases/gate_rejections.csv (écrit par global_risk_gate.py)
et produit un rapport structuré : top raisons de blocage, distribution
par régime, score moyen bloqué vs passé.

Usage :
    python S2/01_gate_logger.py
    python S2/01_gate_logger.py --tail 200   # seulement les 200 derniers
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

CSV_PATH = os.getenv("GATE_LOG_CSV", "databases/gate_rejections.csv")


def load(path: str, tail: int = 0) -> list[dict]:
    p = Path(path)
    if not p.exists():
        print(f"[gate_logger] Fichier absent: {path}")
        print("  → Assurez-vous que global_risk_gate.py logue les rejets.")
        print(
            "  → Variable d'env: GATE_LOG_CSV (défaut: databases/gate_rejections.csv)"
        )
        return []
    rows = []
    with open(p, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows[-tail:] if tail else rows


def report(rows: list[dict]) -> None:
    if not rows:
        print("[gate_logger] Aucune donnée à analyser.")
        return

    total = len(rows)
    blocked = [r for r in rows if r.get("allowed", "True") == "False"]
    passed = total - len(blocked)

    print(f"\n{'='*60}")
    print(f"  GATE LOGGER — {total} événements")
    print(
        f"  Passés : {passed} ({passed/total:.0%})  |  Bloqués : {len(blocked)} ({len(blocked)/total:.0%})"
    )
    print(f"{'='*60}")

    if not blocked:
        print("  Aucun blocage enregistré.")
        return

    # ── Top raisons de blocage ─────────────────────────────────────────────────
    failed_counter: Counter = Counter()
    for r in blocked:
        try:
            failed_list = json.loads(r.get("failed", "[]"))
        except Exception:
            failed_list = [r.get("failed", "unknown")]
        for f in failed_list:
            failed_counter[f] += 1

    print("\n  Top raisons de blocage:")
    for reason, count in failed_counter.most_common(10):
        pct = count / len(blocked) * 100
        bar = "█" * int(pct / 5)
        print(f"    {reason:<35} {count:>4}x  {pct:>5.1f}%  {bar}")

    # ── Distribution par régime ────────────────────────────────────────────────
    by_regime: dict[str, dict] = defaultdict(lambda: {"total": 0, "blocked": 0})
    for r in rows:
        reg = r.get("regime", "unknown")
        by_regime[reg]["total"] += 1
        if r.get("allowed", "True") == "False":
            by_regime[reg]["blocked"] += 1

    print("\n  Blocages par régime:")
    for reg, counts in sorted(by_regime.items(), key=lambda x: -x[1]["blocked"]):
        t, b = counts["total"], counts["blocked"]
        br = b / t * 100 if t else 0
        print(f"    {reg:<25} bloqué {b:>3}/{t:<4} ({br:.0f}%)")

    # ── Distribution des scores bloqués ───────────────────────────────────────
    blocked_scores = []
    for r in blocked:
        try:
            blocked_scores.append(float(r.get("score", 0)))
        except ValueError:
            pass

    if blocked_scores:
        avg = sum(blocked_scores) / len(blocked_scores)
        mn, mx = min(blocked_scores), max(blocked_scores)
        # Percentiles manuels
        s = sorted(blocked_scores)
        p50 = s[len(s) // 2]
        p90 = s[int(len(s) * 0.9)]
        print(f"\n  Scores des signaux bloqués:")
        print(
            f"    min={mn:.0f}  p50={p50:.0f}  p90={p90:.0f}  max={mx:.0f}  avg={avg:.1f}"
        )

    # ── Seuil effectif vs score bloqué ────────────────────────────────────────
    gap_sum = 0.0
    gap_count = 0
    for r in blocked:
        try:
            score = float(r.get("score", 0))
            eff_min = float(r.get("effective_min", 0))
            if eff_min > 0:
                gap_sum += eff_min - score
                gap_count += 1
        except ValueError:
            pass

    if gap_count:
        avg_gap = gap_sum / gap_count
        print(f"\n  Gap moyen seuil-score (bloqués): +{avg_gap:.1f} pts")
        if avg_gap <= 3:
            print(
                "  → PROCHE: réduire le seuil de 3-5 pts suffirait à débloquer beaucoup."
            )
        elif avg_gap <= 8:
            print("  → MODÉRÉ: score max trop bas OU seuil trop élevé.")
        else:
            print(
                "  → LARGE: signaux fondamentalement trop faibles — vérifier le scorer."
            )

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse des rejets du GlobalRiskGate")
    parser.add_argument(
        "--tail", type=int, default=0, help="Limiter aux N dernières lignes"
    )
    parser.add_argument("--csv", default=CSV_PATH, help="Chemin du CSV")
    args = parser.parse_args()

    rows = load(args.csv, args.tail)
    report(rows)


if __name__ == "__main__":
    main()
