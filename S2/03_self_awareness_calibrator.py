"""
03_self_awareness_calibrator.py — Calibration des seuils SelfAwarenessEngine.

Problème actuel : avec un win rate réel de ~20%, les seuils WR_DROP_CAUTION=15%
et WR_DROP_WARNING=25% ne se déclenchent jamais (il faudrait descendre sous 0%).

Ce script calcule les seuils réalistes basés sur la distribution réelle,
et génère les variables d'env à copier dans .env.

Usage :
    python S2/03_self_awareness_calibrator.py
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from pathlib import Path

MM_PATH = "databases/mistake_memory.jsonl"


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


def compute_rolling_winrates(trades: list[dict], window: int = 10) -> list[float]:
    """Calcule le win rate roulant sur `window` trades."""
    wrs = []
    for i in range(window, len(trades) + 1):
        subset = trades[i - window : i]
        wins = sum(1 for t in subset if t.get("pnl_pct", 0) > 0)
        wrs.append(wins / window)
    return wrs


def analyze() -> None:
    trades = load_trades()
    if not trades:
        print("[sa_calibrator] Aucune donnée dans mistake_memory.jsonl")
        return

    total = len(trades)
    wins = sum(1 for t in trades if t.get("pnl_pct", 0) > 0)
    baseline_wr = wins / total if total else 0

    print(f"\n{'='*60}")
    print(f"  SELF-AWARENESS CALIBRATOR — {total} trades")
    print(f"{'='*60}")
    print(f"  Win rate global (baseline): {baseline_wr:.1%}")
    print(f"  Loss rate global:           {1-baseline_wr:.1%}")

    # ── Seuils actuels ─────────────────────────────────────────────────────────
    sa_window = int(os.getenv("SA_RECENT_WINDOW", "10"))
    sa_caution = float(os.getenv("SA_WR_DROP_CAUTION", "0.15"))
    sa_warning = float(os.getenv("SA_WR_DROP_WARNING", "0.25"))

    print(f"\n  Seuils actuels (SA_RECENT_WINDOW={sa_window}):")
    print(f"    CAUTION si chute WR > {sa_caution:.0%}")
    print(f"    WARNING si chute WR > {sa_warning:.0%}")
    print(f"\n  Avec baseline {baseline_wr:.1%}:")
    print(f"    CAUTION se déclenche si WR récent < {baseline_wr - sa_caution:.1%}")
    print(f"    WARNING se déclenche si WR récent < {baseline_wr - sa_warning:.1%}")

    if baseline_wr - sa_caution < 0:
        print(
            f"\n  ⚠️  CAUTION ne peut JAMAIS se déclencher (seuil négatif impossible)!"
        )
    if baseline_wr - sa_warning < 0:
        print(f"  ⚠️  WARNING ne peut JAMAIS se déclencher (seuil négatif impossible)!")

    # ── Distribution des win rates roulants ───────────────────────────────────
    if total >= sa_window + 5:
        rolling = compute_rolling_winrates(trades, sa_window)
        rolling_sorted = sorted(rolling)
        p5 = rolling_sorted[max(0, int(len(rolling_sorted) * 0.05))]
        p10 = rolling_sorted[max(0, int(len(rolling_sorted) * 0.10))]
        p25 = rolling_sorted[max(0, int(len(rolling_sorted) * 0.25))]
        avg_rolling = sum(rolling) / len(rolling)

        print(f"\n  Distribution WR roulant ({sa_window} trades):")
        print(
            f"    p5={p5:.1%}  p10={p10:.1%}  p25={p25:.1%}  moyenne={avg_rolling:.1%}"
        )

        # Seuils recommandés = percentiles de la distribution roulante
        recommended_caution_drop = avg_rolling - p25  # quart inférieur normal
        recommended_warning_drop = avg_rolling - p10  # décile inférieur
        recommended_danger_drop = avg_rolling - p5  # 5% les pires

        print(f"\n  SEUILS RECOMMANDÉS (basés sur distribution réelle):")
        print(
            f"    SA_WR_DROP_CAUTION={recommended_caution_drop:.2f}  "
            f"(déclenche WR < p25={p25:.1%})"
        )
        print(
            f"    SA_WR_DROP_WARNING={recommended_warning_drop:.2f}  "
            f"(déclenche WR < p10={p10:.1%})"
        )
        print(f"    # DANGER géré par SA_DD_ACCEL (drawdown accélération)")

    # ── Analyse des pertes consécutives ───────────────────────────────────────
    print(f"\n  Analyse pertes consécutives (avec loss_rate={1-baseline_wr:.1%}):")
    for n_consec in [2, 3, 4, 5]:
        prob = (1 - baseline_wr) ** n_consec
        print(
            f"    P({n_consec} pertes d'affilée) = {prob:.1%} → "
            + ("NORMAL" if prob > 0.20 else ("RARE" if prob > 0.05 else "TRÈS RARE"))
        )

    sa_revenge = int(os.getenv("SA_REVENGE_LOSSES", "2"))
    prob_revenge = (1 - baseline_wr) ** sa_revenge
    print(
        f"\n  ⚠️  SA_REVENGE_LOSSES={sa_revenge} → se déclenche {prob_revenge:.0%} du temps!"
    )
    if prob_revenge > 0.30:
        print(
            f"     Recommandation: augmenter SA_REVENGE_LOSSES à "
            + str(min(5, sa_revenge + 2))
        )

    # ── Analyse drawdown accélération ─────────────────────────────────────────
    sa_dd_accel = float(os.getenv("SA_DD_ACCEL", "0.03"))
    recent_pnls = [t.get("pnl_pct", 0) for t in trades[-sa_window:]]
    if recent_pnls:
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in recent_pnls:
            cum += p
            peak = max(peak, cum)
            max_dd = max(max_dd, peak - cum)
        print(f"\n  Drawdown sur les {sa_window} derniers trades: {max_dd:.2%}")
        print(f"  Seuil SA_DD_ACCEL actuel: {sa_dd_accel:.2%}")
        if max_dd > sa_dd_accel * 2:
            print(f"  → DANGER devrait se déclencher!")
        elif max_dd > sa_dd_accel:
            print(f"  → WARNING devrait se déclencher!")

    # ── Lignes .env à copier ───────────────────────────────────────────────────
    if total >= sa_window + 5:
        print(f"\n  LIGNES À AJOUTER/MODIFIER DANS .env:")
        print(f"  {'─'*40}")
        print(f"  SA_WR_DROP_CAUTION={recommended_caution_drop:.2f}")
        print(f"  SA_WR_DROP_WARNING={recommended_warning_drop:.2f}")
        print(f"  SA_REVENGE_LOSSES={min(5, sa_revenge + 2)}")
        print(f"  {'─'*40}")

    # ── Analyse par régime ────────────────────────────────────────────────────
    by_regime: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_regime[t.get("regime", "unknown")].append(t.get("pnl_pct", 0))

    print(f"\n  Win rate par régime:")
    for reg, pnls in sorted(by_regime.items(), key=lambda x: -len(x[1])):
        n = len(pnls)
        wr = sum(1 for p in pnls if p > 0) / n
        avg_pnl = sum(pnls) / n
        print(f"    {reg:<25} n={n:>4}  WR={wr:.0%}  avg_pnl={avg_pnl:.2%}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    analyze()
