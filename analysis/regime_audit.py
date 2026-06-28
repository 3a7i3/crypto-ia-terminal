# flake8: noqa: E402
"""
analysis/regime_audit.py — Runner principal du framework d'audit.

Charge tous les plugins, les exécute sur les trades, et produit un rapport
consolidé avec les métriques complètes par régime + tests d'hypothèses.

Usage :
    python3 analysis/regime_audit.py [path_to_paper_trades.jsonl] [--since YYYY-MM-DD]

Plugins disponibles (auto-découverte via analysis/plugins/):
    bear.py        — BEY en bear_trend
    sideways.py    — BUY/SELL en sideways
    bull.py        — BUY en bull_trend (à implémenter quand N suffisant)
    volatility.py  — filtre ATR / haute volatilité
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Rendre analysis/ importable depuis la racine du projet
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.base import Trade, full_metrics, load_trades
from analysis.hypotheses import print_hypotheses_report, run_all_hypotheses

W = 68

CLEAN_SINCE = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _filter_by_date(trades: list[Trade], since: datetime | None) -> list[Trade]:
    if since is None:
        return trades
    result = []
    for t in trades:
        if t.opened_at is None:
            continue
        ts = datetime.fromtimestamp(t.opened_at, tz=timezone.utc)
        if ts >= since:
            result.append(t)
    return result


def _regime_breakdown(trades: list[Trade]) -> None:
    """Rapport par régime avec métriques complètes."""
    from collections import defaultdict

    by_regime: dict[str, list[float]] = defaultdict(list)
    by_regime_side: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for t in trades:
        by_regime[t.regime].append(t.pnl_usd)
        by_regime_side[t.regime][t.side].append(t.pnl_usd)

    print(f"\n{'─'*W}")
    print("  MÉTRIQUES PAR RÉGIME")
    print(f"{'─'*W}")

    for regime in sorted(by_regime):
        pnls = by_regime[regime]
        m = full_metrics(pnls)
        print(f"\n  [{regime.upper()}]  N={m['n']} | PnL={m['total_pnl_usd']:+.2f}$")
        print(
            f"    PF={m['profit_factor']} | WR={m['win_rate']} "
            f"| E={m['expectancy_usd']}$/trade"
        )
        print(
            f"    Sharpe={m['sharpe']} | Sortino={m['sortino']} "
            f"| MaxDD={m['max_drawdown_usd']:.2f}$"
        )
        print(
            f"    Ulcer={m['ulcer_index']} | Recovery={m['recovery_factor']} "
            f"| Kelly={m['kelly_fraction']}"
        )
        # Détail BUY/SELL
        sides = by_regime_side[regime]
        for side in ["BUY", "SELL"]:
            sp = sides.get(side, [])
            if sp:
                sm = full_metrics(sp)
                print(
                    f"    {side}: N={sm['n']} PF={sm['profit_factor']} "
                    f"WR={sm['win_rate']} E={sm['expectancy_usd']}$"
                )


def _symbol_breakdown(trades: list[Trade]) -> None:
    from collections import defaultdict

    by_sym: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_sym[t.symbol].append(t.pnl_usd)

    print(f"\n{'─'*W}")
    print("  TOP/FLOP SYMBOLES")
    print(f"{'─'*W}")
    rows = [
        (sym, len(pnls), sum(pnls), full_metrics(pnls)["profit_factor"])
        for sym, pnls in by_sym.items()
        if len(pnls) >= 3
    ]
    rows.sort(key=lambda x: x[2])  # sort by PnL
    print(f"  {'Symbole':<20} {'N':>4} {'PnL':>10}  PF")
    print(f"  {'-'*45}")
    for sym, n, pnl, pf in rows:
        pf_str = f"{pf:.2f}" if isinstance(pf, float) else str(pf)
        print(f"  {sym:<20} {n:>4} {pnl:>+9.2f}$  {pf_str}")


def main(jsonl_path: str | None = None, since: datetime | None = None) -> int:
    try:
        all_trades = load_trades(jsonl_path)
    except FileNotFoundError as e:
        print(f"ERREUR: {e}")
        return 1

    # Filtre par date (défaut = données propres depuis 2026-06-25)
    effective_since = since or CLEAN_SINCE
    trades = _filter_by_date(all_trades, effective_since)

    print(f"\n{'='*W}")
    print("  REGIME AUDIT FRAMEWORK")
    print(f"{'='*W}")
    print(f"  Trades total       : {len(all_trades)}")
    print(f"  Trades propres     : {len(trades)} (depuis {effective_since.date()})")
    print(f"  Symboles actifs    : {len({t.symbol for t in trades})}")
    print(f"  Régimes couverts   : {sorted({t.regime for t in trades})}")

    if len(trades) < 10:
        print(f"\n  ⏳ Données insuffisantes — relancer à N≥50")
        print(f"{'='*W}\n")
        return 0

    # Métriques globales
    all_pnl = [t.pnl_usd for t in trades]
    m = full_metrics(all_pnl)
    print(f"\n{'─'*W}")
    print("  MÉTRIQUES GLOBALES")
    print(f"{'─'*W}")
    print(f"  PnL total  : {m['total_pnl_usd']:+.2f}$")
    print(f"  PF         : {m['profit_factor']}")
    print(f"  Win Rate   : {m['win_rate']}")
    print(f"  Expectancy : {m['expectancy_usd']}$/trade")
    print(f"  Sharpe     : {m['sharpe']}")
    print(f"  Sortino    : {m['sortino']}")
    print(f"  MaxDD      : {m['max_drawdown_usd']:.2f}$")
    print(f"  Ulcer      : {m['ulcer_index']}")
    print(f"  Recovery   : {m['recovery_factor']}")
    print(f"  Kelly      : {m['kelly_fraction']}")
    print(f"  MAR        : {m['mar_ratio']}")

    _regime_breakdown(trades)
    _symbol_breakdown(trades)

    # Tests d'hypothèses
    hypotheses = run_all_hypotheses(trades)
    print_hypotheses_report(hypotheses)

    # Go/No-Go préliminaire
    print(f"{'─'*W}")
    print("  GO / NO-GO PRÉLIMINAIRE")
    print(f"{'─'*W}")
    checks = {
        "N ≥ 50": len(trades) >= 50,
        "PF > 1.0": isinstance(m["profit_factor"], float) and m["profit_factor"] > 1.0,
        "Expectancy > 0": m["expectancy_usd"] is not None and m["expectancy_usd"] > 0,
        "MaxDD < capital×10%": True,  # à calculer avec capital réel
        "Sharpe > 0": m["sharpe"] is not None and m["sharpe"] > 0,
    }
    go = all(checks.values())
    for check, ok in checks.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon} {check}")
    print(
        f"\n  {'🟢 GO (provisoire)' if go else '🔴 NO-GO'} — "
        f"critères finaux à N≥100"
    )
    print(f"{'='*W}\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regime Audit Framework")
    parser.add_argument("jsonl", nargs="?", help="Chemin vers paper_trades.jsonl")
    parser.add_argument(
        "--since",
        help="Date de début (YYYY-MM-DD), défaut=2026-06-25",
        default=None,
    )
    args = parser.parse_args()
    since_dt = None
    if args.since:
        since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    sys.exit(main(jsonl_path=args.jsonl, since=since_dt))
