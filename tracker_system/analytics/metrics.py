from __future__ import annotations

from pathlib import Path

from tracker_system.analytics.mfe_mae import compute_average_mfe_mae, compute_efficiency
from tracker_system.analytics.regime_analysis import summarize_regimes
from tracker_system.config.settings import TRADES_LOG_FILE
from tracker_system.storage.loader import load_jsonl


def load_trades(log_file: Path = TRADES_LOG_FILE) -> list[dict]:
    return [event for event in load_jsonl(log_file) if event.get("type") == "exit"]


def compute_basic_metrics(trades: list[dict]) -> dict[str, float | int]:
    if not trades:
        return {}

    total = len(trades)
    wins = [trade for trade in trades if float(trade.get("pnl_usd", 0.0)) > 0]
    losses = [trade for trade in trades if float(trade.get("pnl_usd", 0.0)) <= 0]
    winrate = len(wins) / total if total else 0.0
    avg_win = sum(float(trade.get("pnl_pct", 0.0)) for trade in wins) / len(wins) if wins else 0.0
    avg_loss = sum(float(trade.get("pnl_pct", 0.0)) for trade in losses) / len(losses) if losses else 0.0
    pnl_total = sum(float(trade.get("pnl_usd", 0.0)) for trade in trades)
    return {
        "trades": total,
        "winrate": winrate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "pnl_total": pnl_total,
    }


def compute_expectancy(winrate: float, avg_win: float, avg_loss: float) -> float:
    lossrate = 1.0 - winrate
    return (winrate * avg_win) + (lossrate * avg_loss)


def compute_all_metrics(log_file: Path = TRADES_LOG_FILE) -> dict:
    trades = load_trades(log_file)
    basic = compute_basic_metrics(trades)
    if not basic:
        return {}

    mfe_mae = compute_average_mfe_mae(trades)
    expectancy = compute_expectancy(
        float(basic.get("winrate", 0.0)),
        float(basic.get("avg_win", 0.0)),
        float(basic.get("avg_loss", 0.0)),
    )
    return {
        **basic,
        "expectancy": expectancy,
        **mfe_mae,
        "efficiency": compute_efficiency(trades),
        "regimes": summarize_regimes(trades),
    }


if __name__ == "__main__":
    print(compute_all_metrics())
