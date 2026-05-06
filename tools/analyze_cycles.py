"""
analyze_cycles.py — Analyse offline des cycles enregistrés dans databases/cycle_data.jsonl

Usage :
    python tools/analyze_cycles.py
    python tools/analyze_cycles.py --file databases/cycle_data.20260501.jsonl
    python tools/analyze_cycles.py --last 500
    python tools/analyze_cycles.py --symbol BTC/USDT
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_cycles(
    path: Path, last: int | None = None, symbol: str | None = None
) -> list[dict]:
    if not path.exists():
        print(f"[ERREUR] Fichier introuvable : {path}")
        sys.exit(1)

    cycles: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cycles.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if last:
        cycles = cycles[-last:]

    if symbol:
        # Filtre : ne garder que les entrées symbols qui matchent
        filtered = []
        for c in cycles:
            sym_entries = [s for s in c.get("symbols", []) if s.get("symbol") == symbol]
            if sym_entries:
                c = {**c, "symbols": sym_entries}
                filtered.append(c)
        cycles = filtered

    return cycles


def stats_global(cycles: list[dict]) -> None:
    print(f"\n{'='*60}")
    print(f"  GLOBAL — {len(cycles)} cycles analysés")
    print(f"{'='*60}")

    capitals = [c.get("capital", 0) for c in cycles if c.get("capital", 0) > 0]
    if capitals:
        print(f"  Capital moyen    : ${sum(capitals)/len(capitals):,.0f}")
        print(f"  Capital min/max  : ${min(capitals):,.0f} / ${max(capitals):,.0f}")

    safe_count = sum(1 for c in cycles if c.get("safe_mode"))
    print(f"  Cycles safe mode : {safe_count} ({safe_count/len(cycles)*100:.1f}%)")

    ex_failures = sum(
        1 for c in cycles if not c.get("exchange", {}).get("healthy", True)
    )
    print(
        f"  Exchange hors ligne : {ex_failures} cycles ({ex_failures/len(cycles)*100:.1f}%)"
    )

    latencies = [c.get("exchange", {}).get("last_latency_ms", 0) for c in cycles]
    latencies = [lat for lat in latencies if lat > 0]
    if latencies:
        print(f"  Latence exchange moy : {sum(latencies)/len(latencies):.0f}ms")


def stats_signals(cycles: list[dict]) -> None:
    print(f"\n{'='*60}")
    print("  SIGNAUX PAR SYMBOLE")
    print(f"{'='*60}")

    by_sym: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "buy": 0,
            "sell": 0,
            "hold": 0,
            "actionable": 0,
            "confirmed": 0,
            "gate_ok": 0,
            "trade_ok": 0,
            "scores": [],
            "conviction_scores": [],
            "regimes": defaultdict(int),
            "personalities": defaultdict(int),
            "futures_modes": defaultdict(int),
        }
    )

    for cycle in cycles:
        for s in cycle.get("symbols", []):
            sym = s.get("symbol", "?")
            d = by_sym[sym]
            d["total"] += 1
            sig = (s.get("signal") or "HOLD").upper()
            if sig == "BUY":
                d["buy"] += 1
            elif sig == "SELL":
                d["sell"] += 1
            else:
                d["hold"] += 1
            if s.get("actionable"):
                d["actionable"] += 1
            if s.get("confirmed"):
                d["confirmed"] += 1
            if s.get("gate_allowed"):
                d["gate_ok"] += 1
            if s.get("trade_allowed"):
                d["trade_ok"] += 1
            score = s.get("score")
            if score is not None:
                d["scores"].append(float(score))
            cscore = s.get("conviction_score")
            if cscore is not None:
                d["conviction_scores"].append(float(cscore))
            regime = s.get("regime") or "?"
            d["regimes"][regime] += 1
            perso = s.get("personality") or "?"
            d["personalities"][perso] += 1
            fmode = (s.get("futures_result") or {}).get("mode") or "none"
            d["futures_modes"][fmode] += 1

    for sym, d in sorted(by_sym.items()):
        n = d["total"]
        scores = d["scores"]
        avg_score = sum(scores) / len(scores) if scores else 0
        cscores = d["conviction_scores"]
        avg_conv = sum(cscores) / len(cscores) if cscores else 0
        top_regime = max(d["regimes"], key=d["regimes"].get) if d["regimes"] else "?"
        top_perso = (
            max(d["personalities"], key=d["personalities"].get)
            if d["personalities"]
            else "?"
        )

        print(f"\n  {sym}  ({n} cycles)")
        print(
            f"    Signaux  : BUY {d['buy']} ({d['buy']/n*100:.0f}%)  "
            f"SELL {d['sell']} ({d['sell']/n*100:.0f}%)  "
            f"HOLD {d['hold']} ({d['hold']/n*100:.0f}%)"
        )
        print(
            f"    Actionable : {d['actionable']}/{n} ({d['actionable']/n*100:.0f}%)  "
            f"| Gate OK : {d['gate_ok']}/{n}  | Trade OK : {d['trade_ok']}/{n}"
        )
        print(f"    Score moyen  : {avg_score:.1f}  | Conviction moy : {avg_conv:.1f}")
        print(
            f"    Régime dominant : {top_regime}  | Personnalité dominante : {top_perso}"
        )

        futures_exec = {
            k: v for k, v in d["futures_modes"].items() if k not in ("none", "rejected")
        }
        if futures_exec:
            total_exec = sum(futures_exec.values())
            print(f"    Ordres exécutés : {total_exec}  → {dict(futures_exec)}")


def stats_regimes(cycles: list[dict]) -> None:
    print(f"\n{'='*60}")
    print("  WIN-RATE PAR RÉGIME (trades futures_demo uniquement)")
    print(f"{'='*60}")

    regime_trades: dict[str, dict[str, int]] = defaultdict(lambda: {"ok": 0, "fail": 0})

    for cycle in cycles:
        for s in cycle.get("symbols", []):
            fut = s.get("futures_result")
            if not isinstance(fut, dict):
                continue
            mode = fut.get("mode", "")
            regime = s.get("regime") or "?"
            if "demo" in mode or mode == "live":
                regime_trades[regime]["ok"] += 1
            elif "fail" in mode:
                regime_trades[regime]["fail"] += 1

    if not regime_trades:
        print("  Aucun trade futures_demo trouvé dans cette période.")
        return

    for regime, counts in sorted(regime_trades.items()):
        total = counts["ok"] + counts["fail"]
        wr = counts["ok"] / total * 100 if total else 0
        print(f"  {regime:<25} {total:>4} trades  win-rate {wr:.0f}%")


def stats_scores_distribution(cycles: list[dict]) -> None:
    print(f"\n{'='*60}")
    print("  DISTRIBUTION DES SCORES (tous symboles)")
    print(f"{'='*60}")

    buckets = defaultdict(int)
    for cycle in cycles:
        for s in cycle.get("symbols", []):
            score = s.get("score")
            if score is None:
                continue
            bucket = int(float(score) // 10) * 10
            buckets[bucket] += 1

    total = sum(buckets.values())
    if total == 0:
        print("  Pas de données.")
        return

    for low in sorted(buckets):
        count = buckets[low]
        bar = "█" * (count * 40 // total)
        print(f"  {low:>3}-{low+9:<3}  {bar:<40}  {count:>5} ({count/total*100:.1f}%)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse offline des cycles cycle_data.jsonl"
    )
    parser.add_argument(
        "--file",
        default="databases/cycle_data.jsonl",
        help="Chemin vers le fichier JSONL",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=None,
        help="Nombre de cycles les plus récents à analyser",
    )
    parser.add_argument(
        "--symbol", default=None, help="Filtrer sur un symbole (ex: BTC/USDT)"
    )
    args = parser.parse_args()

    path = Path(args.file)
    cycles = load_cycles(path, last=args.last, symbol=args.symbol)

    if not cycles:
        print("[INFO] Aucun cycle chargé.")
        return

    stats_global(cycles)
    stats_signals(cycles)
    stats_regimes(cycles)
    stats_scores_distribution(cycles)
    print()


if __name__ == "__main__":
    main()
