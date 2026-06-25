#!/usr/bin/env python3
"""Analyse ciblée des trades bear_trend — H0 vs H1."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

JSONL = (
    Path(sys.argv[1]) if len(sys.argv) > 1 else Path("databases/paper_trades_vps.jsonl")
)

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

trades = []
for tid, cl in closes.items():
    op = opens.get(tid, {})
    regime = op.get("regime") or cl.get("regime") or "unknown"
    if regime != "bear_trend":
        continue
    trades.append(
        {
            "trade_id": tid,
            "symbol": cl.get("symbol") or op.get("symbol", "?"),
            "side": (op.get("side") or cl.get("side") or "?").upper(),
            "score": int(op.get("score") or cl.get("score") or 0),
            "pnl_usd": float(cl.get("pnl_usd") or 0.0),
            "pnl_pct": float(cl.get("pnl_pct") or 0.0),
            "reason": cl.get("reason") or "?",
            "mfe_pct": cl.get("mfe_pct"),
            "mae_pct": cl.get("mae_pct"),
            "duration_s": float(cl.get("duration_s") or 0),
        }
    )

trades.sort(key=lambda x: x["score"])


def pf(pnls: list[float]) -> str:
    wins = sum(p for p in pnls if p > 0)
    losses = abs(sum(p for p in pnls if p < 0))
    return f"{wins/losses:.2f}" if losses else ("inf" if wins > 0 else "n/a")


def wr(pnls: list[float]) -> str:
    return f"{sum(1 for p in pnls if p > 0)/len(pnls)*100:.0f}%" if pnls else "n/a"


W = 60
print(f"\n{'='*W}")
print(f"  BEAR_TREND AUDIT — {len(trades)} trades")
print(f"{'='*W}")

# ── 1. BUY vs SELL ────────────────────────────────────────────
print(f"\n  1. Sens des positions")
print(f"  {'Side':<6} {'N':>4} {'WR':>6} {'PF':>7} {'PnL':>10}")
print(f"  {'-'*38}")
sides: dict[str, list[float]] = defaultdict(list)
for t in trades:
    sides[t["side"]].append(t["pnl_usd"])
for side in sorted(sides):
    pnls = sides[side]
    print(f"  {side:<6} {len(pnls):>4} {wr(pnls):>6} {pf(pnls):>7} {sum(pnls):>+9.2f}$")

# ── 2. Score buckets ──────────────────────────────────────────
print(f"\n  2. PF par bucket de score")
print(f"  {'Bucket':<8} {'N':>4} {'WR':>6} {'PF':>7} {'PnL':>10}")
print(f"  {'-'*40}")
buckets: dict[str, list[float]] = defaultdict(list)
for t in trades:
    s = t["score"]
    b = (
        "65-69"
        if 65 <= s < 70
        else "70-74" if 70 <= s < 75 else "75+" if s >= 75 else "<65"
    )
    buckets[b].append(t["pnl_usd"])
for bkt in ["<65", "65-69", "70-74", "75+"]:
    pnls = buckets.get(bkt, [])
    if not pnls:
        continue
    print(f"  {bkt:<8} {len(pnls):>4} {wr(pnls):>6} {pf(pnls):>7} {sum(pnls):>+9.2f}$")

# ── 3. MFE / MAE ─────────────────────────────────────────────
print(f"\n  3. MFE / MAE (direction réelle du prix)")
mfe_vals = [t["mfe_pct"] for t in trades if t["mfe_pct"] is not None]
mae_vals = [t["mae_pct"] for t in trades if t["mae_pct"] is not None]
if mfe_vals:
    avg_mfe = sum(mfe_vals) / len(mfe_vals)
    mfe_zero = sum(1 for v in mfe_vals if v < 0.1)
    print(f"  MFE moy={avg_mfe:.2f}%  max={max(mfe_vals):.2f}%  N={len(mfe_vals)}")
    print(
        f"  MFE<0.1% (prix n'a jamais bougé dans le bon sens) : "
        f"{mfe_zero}/{len(mfe_vals)} = {mfe_zero/len(mfe_vals)*100:.0f}%"
    )
    # Séparer par side
    for side in ["BUY", "SELL"]:
        mfe_s = [
            t["mfe_pct"]
            for t in trades
            if t["side"] == side and t["mfe_pct"] is not None
        ]
        if mfe_s:
            z = sum(1 for v in mfe_s if v < 0.1)
            mfe_avg = sum(mfe_s) / len(mfe_s)
            print(f"    {side}: moy_MFE={mfe_avg:.2f}%  MFE<0.1%={z}/{len(mfe_s)}")
else:
    print("  (MFE non disponible dans ce jeu de données)")
if mae_vals:
    print(f"  MAE moy={sum(mae_vals)/len(mae_vals):.2f}%  max={max(mae_vals):.2f}%")

# ── 4. Mode de sortie ─────────────────────────────────────────
print(f"\n  4. Mode de sortie")
print(f"  {'Raison':<14} {'N':>4} {'WR':>6} {'PnL':>10}")
print(f"  {'-'*38}")
reasons: dict[str, list[float]] = defaultdict(list)
for t in trades:
    r = t["reason"].lower()
    cat = (
        "SL"
        if any(k in r for k in ("sl", "stop", "loss", "stoploss"))
        else (
            "TP"
            if any(k in r for k in ("tp", "profit", "target"))
            else (
                "TIMEOUT"
                if any(k in r for k in ("timeout", "time", "expire", "duration"))
                else t["reason"][:12]
            )
        )
    )
    reasons[cat].append(t["pnl_usd"])
for cat, pnls in sorted(reasons.items(), key=lambda x: -len(x[1])):
    print(f"  {cat:<14} {len(pnls):>4} {wr(pnls):>6} {sum(pnls):>+9.2f}$")

# ── 5. Détail par trade ───────────────────────────────────────
print(f"\n  5. Détail individuel (trié par PnL)")
print(
    f"  {'Symbol':<18} {'Sc':>3} {'Side':<5} {'PnL':>8}  {'MFE':>6} {'MAE':>6}  Sortie"
)
print(f"  {'-'*70}")
for t in sorted(trades, key=lambda x: x["pnl_usd"]):
    mfe = f"{t['mfe_pct']:.1f}%" if t["mfe_pct"] is not None else "  ?"
    mae = f"{t['mae_pct']:.1f}%" if t["mae_pct"] is not None else "  ?"
    print(
        f"  {t['symbol']:<18} {t['score']:>3} {t['side']:<5} {t['pnl_usd']:>+7.2f}$  "
        f"{mfe:>6} {mae:>6}  {t['reason'][:20]}"
    )

# ── Verdict ───────────────────────────────────────────────────
print(f"\n{'='*W}")
buy_pnls = sides.get("BUY", [])
sell_pnls = sides.get("SELL", [])
all_pnls = [t["pnl_usd"] for t in trades]
print(f"  VERDICT PRÉLIMINAIRE")
if buy_pnls and pf(buy_pnls) == "n/a":
    buy_pf_str = "n/a"
elif buy_pnls:
    buy_wins = sum(p for p in buy_pnls if p > 0)
    buy_losses = abs(sum(p for p in buy_pnls if p < 0))
    buy_pf_str = f"{buy_wins/buy_losses:.2f}" if buy_losses else "inf"
else:
    buy_pf_str = "n/a"

if buy_pnls:
    buy_verdict = (
        "CONTRE-TENDANCE"
        if float(buy_pf_str.replace("n/a", "0") or 0) < 0.5
        else "ambigu"
    )
    print(f"  BUY en bear_trend : PF={buy_pf_str} → {buy_verdict}")
if sell_pnls:
    sell_wins = sum(p for p in sell_pnls if p > 0)
    sell_losses = abs(sum(p for p in sell_pnls if p < 0))
    sell_pf_v = sell_wins / sell_losses if sell_losses else float("inf")
    print(f"  SELL en bear_trend : PF={sell_pf_v:.2f}")
print(f"{'='*W}\n")
