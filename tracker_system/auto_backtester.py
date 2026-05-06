"""
auto_backtester.py — Backtester automatique avec price_path réel

Lit logs/trades.jsonl (exits avec price_path).
Teste une grille de configurations d'exit par régime.
Sauvegarde les meilleurs paramètres dans logs/optimizer.json.

Usage:
    python tracker_system/auto_backtester.py
    python tracker_system/auto_backtester.py --min-trades 20 --out logs/optimizer.json
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from itertools import product
from pathlib import Path
from typing import Any

from tracker_system.exit_engine.engine   import ExitEngine
from tracker_system.exit_engine.tp_sl    import TPSLRule
from tracker_system.exit_engine.trailing import TrailingStopRule
from tracker_system.exit_engine.breakeven import BreakEvenRule

LOG_FILE  = Path("logs/trades.jsonl")
OUT_FILE  = Path("logs/optimizer.json")

# ── Grille de paramètres à tester ─────────────────────────────────────────────

TP_RANGE      = [0.008, 0.012, 0.015, 0.020, 0.025, 0.030]
SL_RANGE      = [0.005, 0.008, 0.010, 0.012, 0.015]
TRAIL_RANGE   = [0.003, 0.005, 0.008]          # trail_pct pour TrailingStop
TRAIL_ACT     = [0.005, 0.010]                 # activation avant trailing


# ── Chargement ────────────────────────────────────────────────────────────────

def load_exits(log_file: Path = LOG_FILE) -> list[dict]:
    trades = []
    if not log_file.exists():
        print(f"[Backtester] Fichier introuvable: {log_file}")
        return trades
    with log_file.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line.strip())
                if ev.get("type") == "exit" and ev.get("price_path"):
                    trades.append(ev)
            except Exception:
                continue
    return trades


def group_by_regime(trades: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        grouped[t.get("regime", "unknown")].append(t)
    return grouped


# ── Simulation d'un trade avec un ExitEngine ──────────────────────────────────

def simulate_trade(trade: dict, engine: ExitEngine) -> float:
    """
    Rejoue le trade via son price_path.
    Retourne le pnl_pct résultant de la stratégie d'exit testée.
    """
    path  = trade.get("price_path", [])
    entry = trade["entry_price"]
    direction = trade["direction"]

    if not path:
        return trade.get("pnl_pct", 0.0)

    # Position simulée (copie légère sans price_path pour économiser mémoire)
    pos = {
        "entry_price": entry,
        "direction": direction,
        "stop_loss": trade.get("stop_loss", 0),
        "take_profit": trade.get("take_profit", float("inf")),
    }

    reason, exit_price = engine.check_path(pos, path)

    if exit_price and exit_price > 0:
        if direction == "long":
            return (exit_price - entry) / entry
        else:
            return (entry - exit_price) / entry

    # Fallback : résultat réel du trade
    return trade.get("pnl_pct", 0.0)


# ── Évaluation d'une stratégie sur un ensemble de trades ─────────────────────

def evaluate(trades: list[dict], engine: ExitEngine) -> dict[str, float]:
    pnls = [simulate_trade(t, engine) for t in trades]
    n    = len(pnls)
    if n == 0:
        return {"avg": 0.0, "win_rate": 0.0, "score": 0.0, "n": 0}

    wins     = sum(1 for p in pnls if p > 0)
    win_rate = wins / n
    avg      = sum(pnls) / n
    score    = avg * win_rate    # équilibre profit moyen × stabilité

    return {"avg": round(avg, 6), "win_rate": round(win_rate, 4),
            "score": round(score, 8), "n": n}


# ── Grid search ───────────────────────────────────────────────────────────────

def find_best_tpsl(trades: list[dict]) -> dict[str, Any]:
    """Optimise TP/SL fixe."""
    best_cfg  = None
    best_score = float("-inf")

    for tp, sl in product(TP_RANGE, SL_RANGE):
        engine = ExitEngine([TPSLRule(tp_override=tp, sl_override=sl)])
        res    = evaluate(trades, engine)
        if res["score"] > best_score:
            best_score = res["score"]
            best_cfg   = {"type": "tp_sl", "tp": tp, "sl": sl, **res}

    return best_cfg or {}


def find_best_trailing(trades: list[dict]) -> dict[str, Any]:
    """Optimise trailing stop seul."""
    best_cfg  = None
    best_score = float("-inf")

    for trail, act in product(TRAIL_RANGE, TRAIL_ACT):
        engine = ExitEngine([TrailingStopRule(trail_pct=trail, activation_pct=act)])
        res    = evaluate(trades, engine)
        if res["score"] > best_score:
            best_score = res["score"]
            best_cfg   = {"type": "trailing", "trail_pct": trail,
                          "activation_pct": act, **res}

    return best_cfg or {}


def find_best_hybrid(trades: list[dict]) -> dict[str, Any]:
    """Optimise combo TP/SL + trailing + breakeven."""
    best_cfg  = None
    best_score = float("-inf")

    # Espace réduit pour éviter explosion combinatoire
    for tp, sl, trail in product(
        [0.015, 0.020, 0.025],
        [0.008, 0.010, 0.012],
        [0.003, 0.005],
    ):
        engine = ExitEngine([
            TPSLRule(tp_override=tp, sl_override=sl),
            TrailingStopRule(trail_pct=trail, activation_pct=sl * 0.8),
            BreakEvenRule(trigger_pct=sl, buffer_pct=0.001),
        ])
        res = evaluate(trades, engine)
        if res["score"] > best_score:
            best_score = res["score"]
            best_cfg   = {"type": "hybrid", "tp": tp, "sl": sl,
                          "trail_pct": trail, **res}

    return best_cfg or {}


# ── Main ──────────────────────────────────────────────────────────────────────

def run_backtest(
    min_trades: int = 30,
    out_file: Path = OUT_FILE,
    log_file: Path = LOG_FILE,
) -> dict:
    trades  = load_exits(log_file)
    print(f"[Backtester] {len(trades)} trades avec price_path chargés")

    if not trades:
        print("[Backtester] Pas assez de données. Lance le MVP en paper mode d'abord.")
        return {}

    grouped = group_by_regime(trades)
    results: dict[str, Any] = {
        "_meta": {
            "total_trades": len(trades),
            "regimes": list(grouped.keys()),
        }
    }

    for regime, ts in sorted(grouped.items()):
        if len(ts) < min_trades:
            print(f"[Backtester] {regime}: {len(ts)} trades < {min_trades} min → ignoré")
            continue

        print(f"\n[Backtester] === {regime} ({len(ts)} trades) ===")

        best_tpsl     = find_best_tpsl(ts)
        best_trail    = find_best_trailing(ts)
        best_hybrid   = find_best_hybrid(ts)

        candidates = [c for c in [best_tpsl, best_trail, best_hybrid] if c]
        best_overall = max(candidates, key=lambda x: x.get("score", 0)) if candidates else {}

        print(f"  TP/SL    : tp={best_tpsl.get('tp')} sl={best_tpsl.get('sl')} "
              f"score={best_tpsl.get('score',0):.6f} wr={best_tpsl.get('win_rate',0):.1%}")
        print(f"  Trailing : trail={best_trail.get('trail_pct')} act={best_trail.get('activation_pct')} "
              f"score={best_trail.get('score',0):.6f} wr={best_trail.get('win_rate',0):.1%}")
        print(f"  Hybrid   : tp={best_hybrid.get('tp')} sl={best_hybrid.get('sl')} "
              f"trail={best_hybrid.get('trail_pct')} "
              f"score={best_hybrid.get('score',0):.6f} wr={best_hybrid.get('win_rate',0):.1%}")
        print(f"  >> BEST  : {best_overall.get('type')} score={best_overall.get('score',0):.6f}")

        results[regime] = {
            "best":    best_overall,
            "tp_sl":   best_tpsl,
            "trailing": best_trail,
            "hybrid":  best_hybrid,
            "n_trades": len(ts),
        }

    # Sauvegarde
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[Backtester] Résultats sauvegardés → {out_file}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-backtester exit engine")
    parser.add_argument("--min-trades", type=int, default=30,
                        help="Trades minimum par régime (défaut 30)")
    parser.add_argument("--out", default=str(OUT_FILE),
                        help="Fichier de sortie JSON")
    parser.add_argument("--log", default=str(LOG_FILE),
                        help="Fichier de trades JSONL")
    args = parser.parse_args()

    run_backtest(min_trades=args.min_trades, out_file=Path(args.out), log_file=Path(args.log))


if __name__ == "__main__":
    main()
