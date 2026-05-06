"""
stress_test_cli.py — Lance le Monte Carlo Stress Test depuis la ligne de commande.

Usage :
    python stress_test_cli.py                        # params par défaut ($1000, 55% win)
    python stress_test_cli.py --equity 1000          # capital initial
    python stress_test_cli.py --win-rate 0.55        # taux de réussite estimé
    python stress_test_cli.py --avg-win 0.015        # gain moyen par trade (fraction)
    python stress_test_cli.py --avg-loss 0.010       # perte moyenne par trade (fraction)
    python stress_test_cli.py --paths 2000           # nombre de simulations (précision)
    python stress_test_cli.py --steps 200            # trades simulés par chemin
    python stress_test_cli.py --from-shadow          # calibre depuis les shadow trades réels
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from quant_hedge_ai.agents.quant.stress_test import MonteCarloStressTester, StressReport

SHADOW_LOG = Path("databases/shadow_execution/shadow_log.jsonl")

_VERDICT = [
    (90, "EXCELLENT  — le système survit dans tous les scénarios"),
    (75, "BON        — quelques scénarios extrêmes posent problème"),
    (60, "ACCEPTABLE — attention aux séries de pertes"),
    (40, "FRAGILE    — risk management à renforcer avant le live"),
    (0,  "CRITIQUE   — ne pas trader en live dans ces conditions"),
]


def _verdict(min_survival: float) -> str:
    for threshold, label in _VERDICT:
        if min_survival >= threshold:
            return label
    return "CRITIQUE"


def calibrate_from_shadow() -> dict:
    """Lit les shadow trades pour estimer win_rate, avg_win, avg_loss."""
    if not SHADOW_LOG.exists():
        return {}
    trades = []
    try:
        with SHADOW_LOG.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    trades.append(json.loads(line))
    except Exception:
        return {}

    if len(trades) < 3:
        return {}

    wins  = [t for t in trades if t.get("action", "") == "BUY"]
    total = len(trades)
    win_rate = len(wins) / total if total else 0.55

    slippages = [t.get("slippage_pct", 0.05) / 100.0 for t in trades]
    avg_slippage = sum(slippages) / len(slippages) if slippages else 0.0005

    # Estimation basée sur le slippage observé
    avg_win  = max(0.005, 0.015 - avg_slippage)
    avg_loss = max(0.005, 0.010 + avg_slippage)

    return {
        "win_rate":  round(win_rate, 3),
        "avg_win":   round(avg_win, 4),
        "avg_loss":  round(avg_loss, 4),
        "n_trades":  total,
        "avg_slippage_pct": round(avg_slippage * 100, 4),
    }


def print_report(report: StressReport, calibration: dict) -> None:
    print(report.summary())

    if calibration:
        print(f"\nCalibration depuis {calibration['n_trades']} shadow trades :")
        print(f"  Win rate estime  : {calibration['win_rate']:.1%}")
        print(f"  Gain moyen       : {calibration['avg_win']:.2%}")
        print(f"  Perte moyenne    : {calibration['avg_loss']:.2%}")
        print(f"  Slippage moyen   : {calibration['avg_slippage_pct']:.4f}%")

    # Résumé des drawdowns
    print(f"\n{'─'*58}")
    print(f"{'Scénario':<28} {'DD moy':>8} {'DD pire':>8} {'Retour':>10}")
    print(f"{'─'*58}")
    for s in report.scenarios:
        r = s.result
        print(
            f"{s.name:<28} "
            f"{r.get('avg_max_drawdown_pct', 0):>7.1f}% "
            f"{r.get('worst_max_drawdown_pct', 0):>7.1f}% "
            f"{r.get('median_return_pct', 0):>+9.1f}%"
        )
    print(f"{'─'*58}")

    # Verdict global
    worst = report.worst_scenario()
    if worst:
        min_surv = worst.survival_rate()
        verdict = _verdict(min_surv)
        print(f"\nVERDICT : {verdict}")
        print(f"  Pire scenario   : {worst.name}")
        print(f"  Taux de survie  : {min_surv:.1f}%")
        print(f"  Taux de ruine   : {worst.ruin_rate():.1f}%")
        capital = report.initial_equity
        p05 = worst.result.get("p05_final_equity", 0)
        perte_max = capital - p05
        print(f"  Perte p5 (pire) : -${perte_max:,.0f} (capital: ${p05:,.0f})")

    # Recommandation live
    print(f"\n{'═'*58}")
    normal_sc = next((s for s in report.scenarios if s.name == "Normal"), None)
    chaos_sc  = next((s for s in report.scenarios if "chaos" in s.name.lower()), None)
    if normal_sc and chaos_sc:
        if normal_sc.survival_rate() >= 90 and chaos_sc.survival_rate() >= 70:
            print("  GO LIVE         : parametres robustes")
        elif normal_sc.survival_rate() >= 80:
            print("  PRUDENCE        : reduire position_pct avant live")
        else:
            print("  ATTENDRE        : affiner win_rate / risk management")
    print(f"{'═'*58}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Monte Carlo Stress Test")
    parser.add_argument("--equity",      type=float, default=float(os.getenv("V9_INITIAL_CAPITAL", "1000")))
    parser.add_argument("--win-rate",    type=float, default=0.55)
    parser.add_argument("--avg-win",     type=float, default=0.015)
    parser.add_argument("--avg-loss",    type=float, default=0.010)
    parser.add_argument("--position",    type=float, default=0.02,
                        help="Fraction du capital par trade (defaut: 2%%)")
    parser.add_argument("--paths",       type=int,   default=1000)
    parser.add_argument("--steps",       type=int,   default=200)
    parser.add_argument("--seed",        type=int,   default=None)
    parser.add_argument("--from-shadow", action="store_true",
                        help="Calibre les parametres depuis les shadow trades reels")
    parser.add_argument("--json",        action="store_true",
                        help="Sortie JSON brute")
    args = parser.parse_args()

    calibration: dict = {}
    win_rate  = args.win_rate
    avg_win   = args.avg_win
    avg_loss  = args.avg_loss

    if args.from_shadow:
        calibration = calibrate_from_shadow()
        if calibration:
            win_rate = calibration["win_rate"]
            avg_win  = calibration["avg_win"]
            avg_loss = calibration["avg_loss"]
            print(f"Calibration shadow: win_rate={win_rate:.1%}  "
                  f"avg_win={avg_win:.2%}  avg_loss={avg_loss:.2%}\n")
        else:
            print("Pas assez de shadow trades pour calibrer — parametres par defaut.\n")

    tester = MonteCarloStressTester(
        equity=args.equity,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        position_pct=args.position,
        seed=args.seed,
    )

    print(f"Simulation en cours... ({args.paths} chemins x {args.steps} trades)")
    report = tester.run_all(paths=args.paths, steps=args.steps)

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print_report(report, calibration)


if __name__ == "__main__":
    main()
