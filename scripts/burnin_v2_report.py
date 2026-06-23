#!/usr/bin/env python3
"""
Rapport burn-in v2 — trades post-6ce7fc2 uniquement.

Usage:
    python scripts/burnin_v2_report.py
    python scripts/burnin_v2_report.py --jsonl path/to/paper_trades.jsonl
    python scripts/burnin_v2_report.py --min-trades 50
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Timestamp du premier trade propre enregistré après déploiement 6ce7fc2
# (2026-06-21 07:39:24 UTC — premier OPEN après install pydantic-settings)
BURNIN_V2_START_TS: float = 1_782_025_920.0  # 07:32:00 UTC, activation 6ce7fc2


def load_trades(jsonl_path: Path, since_ts: float) -> list[dict]:
    """Retourne les trades CLOSE complets post-6ce7fc2."""
    closes: dict[str, dict] = {}
    opens: dict[str, dict] = {}

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = ev.get("ts", 0.0)
            if ts < since_ts:
                continue
            tid = ev.get("trade_id", "")
            event = ev.get("event", "")
            if event == "OPEN":
                opens[tid] = ev
            elif event == "CLOSE":
                closes[tid] = ev

    # Ne garder que les CLOSE qui ont un OPEN correspondant (trades complets)
    trades = []
    for tid, close_ev in closes.items():
        if tid in opens:
            trades.append(close_ev)
    return sorted(trades, key=lambda x: x.get("ts", 0.0))


def profit_factor(pnls: list[float]) -> float:
    wins = sum(p for p in pnls if p > 0)
    losses = abs(sum(p for p in pnls if p < 0))
    return wins / losses if losses > 0 else float("inf")


def max_drawdown(pnls_usd: list[float], capital: float = 1000.0) -> float:
    equity = capital
    peak = capital
    max_dd = 0.0
    for p in pnls_usd:
        equity += p
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def report(trades: list[dict], min_trades: int) -> None:
    n = len(trades)
    print(f"\n{'='*55}")
    print(f"  BURN-IN v2 - post-6ce7fc2")
    print(f"{'='*55}")
    print(f"  Trades complets : {n}")

    if n < min_trades:
        print(f"\n  [ATTENTE] Insuffisant pour decision ({n}/{min_trades} requis).")
        print(f"  Revenir quand N >= {min_trades}.\n")
        return

    pnls_usd = [t.get("pnl_usd") or 0.0 for t in trades]
    pnls_pct = [t.get("pnl_pct") or 0.0 for t in trades]

    wins = [p for p in pnls_usd if p > 0]
    losses = [p for p in pnls_usd if p < 0]
    wr = len(wins) / n * 100
    pf = profit_factor(pnls_usd)
    exp_usd = sum(pnls_usd) / n
    exp_pct = sum(pnls_pct) / n
    total_pnl = sum(pnls_usd)
    mdd = max_drawdown(pnls_usd)

    print(f"\n  --- Métriques globales ---")
    print(f"  N                : {n}")
    print(f"  Win Rate         : {wr:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  Profit Factor    : {pf:.3f}")
    print(f"  Expectancy USD   : {exp_usd:+.4f} $")
    print(f"  Expectancy %     : {exp_pct:+.4f}%")
    print(f"  PnL total        : {total_pnl:+.2f} $")
    print(f"  Max Drawdown     : {mdd*100:.2f}%")
    print(f"  Avg win          : {(sum(wins)/len(wins) if wins else 0):+.4f} $")
    print(f"  Avg loss         : {(sum(losses)/len(losses) if losses else 0):+.4f} $")

    # --- Par régime ---
    by_regime: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_regime[t.get("regime") or "unknown"].append(t.get("pnl_usd") or 0.0)

    print(f"\n  --- Par régime ---")
    print(f"  {'Régime':<20} {'N':>4} {'WR':>7} {'PF':>7} {'PnL':>9}")
    print(f"  {'-'*52}")
    for regime in sorted(by_regime, key=lambda r: -len(by_regime[r])):
        ps = by_regime[regime]
        r_wr = sum(1 for p in ps if p > 0) / len(ps) * 100
        r_pf = profit_factor(ps)
        r_pnl = sum(ps)
        pf_str = f"{r_pf:.2f}" if r_pf != float("inf") else "∞"
        print(f"  {regime:<20} {len(ps):>4} {r_wr:>6.1f}% {pf_str:>7} {r_pnl:>+8.2f}$")

    # --- Par score bin ---
    by_score: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_score[t.get("score_bin") or "?"].append(t.get("pnl_usd") or 0.0)

    print(f"\n  --- Par score bin ---")
    print(f"  {'Score':<12} {'N':>4} {'WR':>7} {'PF':>7} {'PnL':>9}")
    print(f"  {'-'*44}")
    for sbin in sorted(by_score, key=lambda s: (s == "?", s)):
        ps = by_score[sbin]
        s_wr = sum(1 for p in ps if p > 0) / len(ps) * 100
        s_pf = profit_factor(ps)
        s_pnl = sum(ps)
        pf_str = f"{s_pf:.2f}" if s_pf != float("inf") else "∞"
        print(f"  {sbin:<12} {len(ps):>4} {s_wr:>6.1f}% {pf_str:>7} {s_pnl:>+8.2f}$")

    # --- Par side (BUY / SELL) ---
    by_side: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        side = (t.get("side") or "?").upper()
        by_side[side].append(t.get("pnl_usd") or 0.0)

    print(f"\n  --- Par side ---")
    print(f"  {'Side':<8} {'N':>4} {'WR':>7} {'PF':>7} {'Exp USD':>10} {'PnL':>9}")
    print(f"  {'-'*48}")
    for side in sorted(by_side):
        ps = by_side[side]
        s_wr = sum(1 for p in ps if p > 0) / len(ps) * 100
        s_pf = profit_factor(ps)
        s_pnl = sum(ps)
        s_exp = s_pnl / len(ps)
        pf_str = f"{s_pf:.2f}" if s_pf != float("inf") else "inf"
        print(
            f"  {side:<8} {len(ps):>4} {s_wr:>6.1f}%"
            f" {pf_str:>7} {s_exp:>+9.4f}$ {s_pnl:>+8.2f}$"
        )

    # --- Par régime x side ---
    by_rx: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        regime = t.get("regime") or "unknown"
        side = (t.get("side") or "?").upper()
        key = f"{regime}+{side}"
        by_rx[key].append(t.get("pnl_usd") or 0.0)

    print(f"\n  --- Par regime x side ---")
    print(f"  {'Régime+Side':<30} {'N':>4} {'WR':>7} {'PF':>7} {'PnL':>9}")
    print(f"  {'-'*60}")
    for key in sorted(by_rx, key=lambda k: (-len(by_rx[k]), k)):
        ps = by_rx[key]
        r_wr = sum(1 for p in ps if p > 0) / len(ps) * 100
        r_pf = profit_factor(ps)
        r_pnl = sum(ps)
        pf_str = f"{r_pf:.2f}" if r_pf != float("inf") else "inf"
        print(f"  {key:<30} {len(ps):>4} {r_wr:>6.1f}%" f" {pf_str:>7} {r_pnl:>+8.2f}$")

    # --- MFE / MAE (qualité du signal) ---
    mfes_all = [t.get("mfe_pct") or 0.0 for t in trades]
    maes_all = [t.get("mae_pct") or 0.0 for t in trades]
    sl_t = [t for t in trades if (t.get("reason") or "") == "SL"]
    tp_t = [t for t in trades if (t.get("reason") or "") == "TP"]
    tout_t = [t for t in trades if (t.get("reason") or "") == "TIMEOUT"]

    avg_mfe = sum(mfes_all) / len(mfes_all) if mfes_all else 0.0
    avg_mae = sum(maes_all) / len(maes_all) if maes_all else 0.0
    print(f"\n  --- MFE / MAE (qualité du signal) ---")
    print(f"  Global     N={n:>3}  avg MFE: {avg_mfe:+.2f}%  avg MAE: {avg_mae:+.2f}%")

    if sl_t:
        sl_mfes = [t.get("mfe_pct") or 0.0 for t in sl_t]
        avg_sl_mfe = sum(sl_mfes) / len(sl_mfes)
        p1 = sum(1 for m in sl_mfes if m > 1.0) / len(sl_mfes) * 100
        p2 = sum(1 for m in sl_mfes if m > 2.0) / len(sl_mfes) * 100
        p3 = sum(1 for m in sl_mfes if m > 3.0) / len(sl_mfes) * 100
        print(
            f"  Trades SL  N={len(sl_t):>3}  avg MFE: {avg_sl_mfe:+.2f}%"
            f"  (>1%:{p1:.0f}%  >2%:{p2:.0f}%  >3%:{p3:.0f}%)"
        )

    if tp_t:
        tp_maes = [t.get("mae_pct") or 0.0 for t in tp_t]
        avg_tp_mae = sum(tp_maes) / len(tp_maes)
        print(f"  Trades TP  N={len(tp_t):>3}  avg MAE: {avg_tp_mae:+.2f}%")

    if tout_t:
        t_mfes = [t.get("mfe_pct") or 0.0 for t in tout_t]
        t_maes = [t.get("mae_pct") or 0.0 for t in tout_t]
        print(
            f"  TIMEOUT    N={len(tout_t):>3}  avg MFE: {sum(t_mfes)/len(t_mfes):+.2f}%"
            f"  avg MAE: {sum(t_maes)/len(t_maes):+.2f}%"
        )

    # --- MFE par régime (signal utile par contexte de marché) ---
    mfe_by_regime: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        reg = t.get("regime") or "unknown"
        mfe_by_regime[reg].append(t.get("mfe_pct") or 0.0)

    print(f"\n  --- MFE par régime (signal utile) ---")
    print(f"  {'Régime':<25} {'N':>4} {'avg MFE':>9} {'>1%':>5} {'>2%':>5}")
    print(f"  {'-'*52}")
    for reg in sorted(mfe_by_regime, key=lambda r: -len(mfe_by_regime[r])):
        ms = mfe_by_regime[reg]
        avg = sum(ms) / len(ms)
        a1 = sum(1 for m in ms if m > 1.0) / len(ms) * 100
        a2 = sum(1 for m in ms if m > 2.0) / len(ms) * 100
        print(f"  {reg:<25} {len(ms):>4} {avg:>+8.2f}%" f" {a1:>4.0f}% {a2:>4.0f}%")

    # --- Raisons de fermeture ---
    by_reason: dict[str, int] = defaultdict(int)
    for t in trades:
        by_reason[t.get("reason") or "?"] += 1
    reasons_str = "  ".join(f"{r}={n}" for r, n in sorted(by_reason.items()))
    print(f"\n  Fermetures : {reasons_str}")

    # --- Verdict ---
    print(f"\n  --- Verdict ---")
    go = pf > 1.20 and exp_usd > 0 and mdd < 0.15
    if go:
        print(f"  [GO] prelive_gate (PF>{1.20:.2f} OK, Exp>0 OK, MaxDD<15% OK)")
    else:
        reasons = []
        if pf <= 1.20:
            reasons.append(f"PF={pf:.3f} ≤ 1.20")
        if exp_usd <= 0:
            reasons.append(f"Expectancy={exp_usd:+.4f}$ ≤ 0")
        if mdd >= 0.15:
            reasons.append(f"MaxDD={mdd*100:.1f}% ≥ 15%")
        print(f"  [NO-GO] ({' | '.join(reasons)})")
    print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--jsonl",
        default="databases/paper_trades.jsonl",
        help="Chemin vers paper_trades.jsonl",
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=50,
        help="Minimum de trades pour afficher le rapport complet",
    )
    parser.add_argument(
        "--since-ts",
        type=float,
        default=BURNIN_V2_START_TS,
        help="Timestamp Unix de début du burn-in v2",
    )
    args = parser.parse_args()

    jsonl = Path(args.jsonl)
    if not jsonl.exists():
        print(f"[Erreur] Fichier introuvable : {jsonl}", file=sys.stderr)
        sys.exit(1)

    trades = load_trades(jsonl, args.since_ts)
    report(trades, args.min_trades)


if __name__ == "__main__":
    main()
