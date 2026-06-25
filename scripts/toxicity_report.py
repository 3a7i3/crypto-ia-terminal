#!/usr/bin/env python3
"""
Rapport de toxicité de l'univers perp.

Identifie les tokens ayant produit des signaux de rug pull / délisting :
  - MAE <= -50%  (crash structurel, quasi-délisting)
  - close_reason = SL et MAE <= -20%  (SL avalé sans résistance)

Usage : python3 scripts/toxicity_report.py [path_to_paper_trades.jsonl]

Par défaut : databases/paper_trades.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

JSONL = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("databases/paper_trades.jsonl")

if not JSONL.exists():
    print(f"ERREUR: fichier introuvable: {JSONL}")
    sys.exit(1)

opens: dict[str, dict] = {}
closes: dict[str, dict] = {}
with JSONL.open(encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        tid = ev.get("trade_id", "")
        if ev.get("event") == "OPEN":
            opens[tid] = ev
        elif ev.get("event") == "CLOSE":
            closes[tid] = ev

# ── Reconstruct trades ───────────────────────────────────────────────────────
trades = []
for tid, cl in closes.items():
    op = opens.get(tid, {})
    mae = cl.get("mae_pct")
    if mae is None:
        continue
    mae = float(mae)
    reason = (cl.get("reason") or "").lower()
    is_sl = any(k in reason for k in ("sl", "stop", "stoploss", "stop_loss"))
    trades.append(
        {
            "trade_id": tid,
            "symbol": cl.get("symbol") or op.get("symbol", "?"),
            "regime": op.get("regime") or cl.get("regime") or "unknown",
            "side": (op.get("side") or cl.get("side") or "?").upper(),
            "pnl_usd": float(cl.get("pnl_usd") or 0.0),
            "pnl_pct": float(cl.get("pnl_pct") or 0.0),
            "mae_pct": mae,
            "mfe_pct": float(cl.get("mfe_pct") or 0.0),
            "reason": cl.get("reason") or "?",
            "is_sl": is_sl,
        }
    )

# ── Identify toxic trades ────────────────────────────────────────────────────
toxic_trades = [
    t for t in trades if t["mae_pct"] <= -50.0 or (t["is_sl"] and t["mae_pct"] <= -20.0)
]

# ── Aggregate by symbol ──────────────────────────────────────────────────────
by_symbol: dict[str, list] = defaultdict(list)
for t in toxic_trades:
    by_symbol[t["symbol"]].append(t)

# All symbols stats for context
all_by_symbol: dict[str, list] = defaultdict(list)
for t in trades:
    all_by_symbol[t["symbol"]].append(t)

W = 72
print(f"\n{'='*W}")
print(f"  RAPPORT TOXICITÉ — {len(trades)} trades total, {len(toxic_trades)} toxiques")
print(f"{'='*W}")
print(f"  Critères: MAE<=-50% OU (SL ET MAE<=-20%)")
print()

if not by_symbol:
    print("  Aucun token toxique détecté.")
else:
    print(f"  {'Symbole':<20} {'N_tox':>5} {'N_tot':>5} {'MAE':>7} {'PnL':>10}  Raison")
    print(f"  {'-'*65}")
    rows = []
    for sym, ttrades in by_symbol.items():
        all_t = all_by_symbol[sym]
        mae_min = min(t["mae_pct"] for t in ttrades)
        pnl_tox = sum(t["pnl_usd"] for t in ttrades)
        reasons = set(t["reason"][:20] for t in ttrades)
        rows.append((sym, len(ttrades), len(all_t), mae_min, pnl_tox, reasons))
    rows.sort(key=lambda x: x[3])  # trier par MAE le plus négatif d'abord
    for sym, n_tox, n_tot, mae_min, pnl_tox, reasons in rows:
        r_str = " | ".join(sorted(reasons))[:22]
        fields = f"{sym:<16} {n_tox:>4} {n_tot:>5} {mae_min:>6.1f}% {pnl_tox:>+9.2f}$"
        print(f"  {fields}  {r_str}")

    print()
    total_tox_pnl = sum(t["pnl_usd"] for t in toxic_trades)
    total_pnl = sum(t["pnl_usd"] for t in trades)
    print(f"  IMPACT: {len(by_symbol)} token(s) toxiques")
    print(f"  PnL toxique : {total_tox_pnl:+.2f}$ / PnL total : {total_pnl:+.2f}$")
    if total_pnl != 0:
        print(f"  Part du PnL total : {total_tox_pnl/total_pnl*100:.0f}%")

    bl = ",".join(sorted(by_symbol.keys()))
    print(
        "\n  BLACKLIST SUGGÉRÉE (ajouter à SYMBOL_BLACKLIST ou _HARDCODED_BLACKLIST):"
    )
    print(f'  export SYMBOL_BLACKLIST="{bl}"')

# ── Regime breakdown of toxic trades ────────────────────────────────────────
print(f"\n  Régimes des trades toxiques:")
by_regime: dict[str, list] = defaultdict(list)
for t in toxic_trades:
    by_regime[t["regime"]].append(t["pnl_usd"])
for regime, pnls in sorted(by_regime.items(), key=lambda x: sum(x[1])):
    print(f"    {regime:<20} N={len(pnls):>3}  PnL={sum(pnls):>+8.2f}$")

print(f"\n{'='*W}\n")
