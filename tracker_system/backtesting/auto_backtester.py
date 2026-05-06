from __future__ import annotations

import json
from itertools import product
from pathlib import Path
from typing import Any

from tracker_system.config.settings import OPTIMIZER_FILE, TRADES_LOG_FILE
from tracker_system.engine.exit_engine import ExitEngine
from tracker_system.engine.rules.tp_sl import TPSLRule
from tracker_system.engine.rules.trailing import TrailingStopRule
from tracker_system.backtesting.simulator import simulate_trade
from tracker_system.storage.loader import load_jsonl
from tracker_system.storage.saver import save_json

TP_VALUES = [0.012, 0.015, 0.020, 0.025, 0.030]
SL_VALUES = [0.008, 0.010, 0.012, 0.015]
TRAIL_VALUES = [0.004, 0.005, 0.007]


def load_exit_trades(log_file: Path = TRADES_LOG_FILE) -> list[dict]:
    return [
        event
        for event in load_jsonl(log_file)
        if event.get("type") == "exit" and event.get("price_path")
    ]


def _evaluate(trades: list[dict], engine: ExitEngine) -> dict[str, float | int]:
    simulations = [simulate_trade(trade, engine) for trade in trades]
    pnls = [float(result["pnl_pct"]) for result in simulations]
    wins = [pnl for pnl in pnls if pnl > 0]
    total = len(pnls)
    if total == 0:
        return {"score": 0.0, "winrate": 0.0, "avg_pnl_pct": 0.0, "samples": 0}
    avg_pnl_pct = sum(pnls) / total
    winrate = len(wins) / total
    return {
        "score": avg_pnl_pct * winrate,
        "winrate": winrate,
        "avg_pnl_pct": avg_pnl_pct,
        "samples": total,
    }


def _group_by_regime(trades: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for trade in trades:
        regime = str(trade.get("regime", "unknown"))
        grouped.setdefault(regime, []).append(trade)
    return grouped


def run_backtest(
    min_trades: int = 20,
    log_file: Path = TRADES_LOG_FILE,
    out_file: Path = OPTIMIZER_FILE,
) -> dict[str, Any]:
    trades = load_exit_trades(log_file)
    grouped = _group_by_regime(trades)
    results: dict[str, Any] = {"_meta": {"total_trades": len(trades), "min_trades": min_trades, "skipped_regimes": {}}}

    for regime, regime_trades in sorted(grouped.items()):
        if len(regime_trades) < min_trades:
            results["_meta"]["skipped_regimes"][regime] = len(regime_trades)
            continue

        best_params: dict[str, Any] | None = None
        best_score = float("-inf")
        for tp, sl, trailing in product(TP_VALUES, SL_VALUES, TRAIL_VALUES):
            engine = ExitEngine([TPSLRule(tp=tp, sl=sl), TrailingStopRule(trail_pct=trailing)])
            stats = _evaluate(regime_trades, engine)
            if float(stats["score"]) > best_score:
                best_score = float(stats["score"])
                best_params = {
                    "tp": tp,
                    "sl": sl,
                    "trailing": trailing,
                    **stats,
                }

        if best_params:
            results[regime] = best_params

    save_json(out_file, results)
    return results


if __name__ == "__main__":
    print(json.dumps(run_backtest(), indent=2))