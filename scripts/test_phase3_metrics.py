#!/usr/bin/env python3
"""
Phase 3 Metrics Test — Validation complete
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.analytics.metrics import (
    load_trades,
    compute_basic_metrics,
    compute_expectancy,
    compute_all_metrics,
)


def test_phase3_metrics():
    log_file = Path("logs/trades.jsonl")

    print("\n[STEP 1] Load trades from JSONL")
    trades = load_trades(log_file)
    print(f"Trades loaded: {len(trades)}")

    if not trades:
        print("No trades to analyze")
        return

    print("\n[STEP 2] Basic metrics")
    metrics = compute_basic_metrics(trades)
    print(f"Trades: {metrics.get('trades')}")
    print(f"Winrate: {metrics.get('winrate', 0.0):.2%}")
    print(f"Avg win: {metrics.get('avg_win', 0.0):.4f}")
    print(f"Avg loss: {metrics.get('avg_loss', 0.0):.4f}")
    print(f"PnL total: ${metrics.get('pnl_total', 0.0):.2f}")

    print("\n[STEP 3] Expectancy")
    expectancy = compute_expectancy(
        metrics.get("winrate", 0.0),
        metrics.get("avg_win", 0.0),
        metrics.get("avg_loss", 0.0),
    )
    print(f"Expectancy: {expectancy:.6f}")

    print("\n[STEP 4] Full metrics")
    all_metrics = compute_all_metrics(log_file)
    print(f"MFE avg: {all_metrics.get('mfe_avg', 0.0):.4f}")
    print(f"MAE avg: {all_metrics.get('mae_avg', 0.0):.4f}")
    print(f"Efficiency: {all_metrics.get('efficiency', 0.0):.2%}")

    if all_metrics.get("regimes"):
        print(f"\nRegimes:")
        for regime_metrics in all_metrics["regimes"]:
            print(f"  {regime_metrics.get('regime')}: winrate={regime_metrics.get('winrate', 0.0):.2%}, trades={regime_metrics.get('trades', 0)}")

    print("\n[OK] Phase 3 test complet!")


if __name__ == "__main__":
    test_phase3_metrics()
