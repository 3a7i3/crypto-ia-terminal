#!/usr/bin/env python3
"""
Phase 4 Backtester Test — Validation optimizer.json
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.backtesting.auto_backtester import run_backtest
from tracker_system.config.settings import OPTIMIZER_FILE


def test_phase4_backtester():
    print("\n[STEP 1] Run optimizer backtest")
    results = run_backtest(min_trades=0)  # min_trades=0 pour test
    print(f"Optimizer results: {len(results)} regimes")

    print("\n[STEP 2] Check optimizer.json output")
    if OPTIMIZER_FILE.exists():
        with open(OPTIMIZER_FILE, "r") as f:
            optimizer = json.load(f)
        print(f"optimizer.json size: {len(optimizer)} keys")

        if "_meta" in optimizer:
            print(f"Total trades analyzed: {optimizer['_meta'].get('total_trades', 0)}")

        for regime, params in optimizer.items():
            if regime == "_meta":
                continue
            print(f"\n{regime}:")
            print(f"  tp: {params.get('tp'):.4f}")
            print(f"  sl: {params.get('sl'):.4f}")
            print(f"  trailing: {params.get('trailing'):.4f}")
            print(f"  score: {params.get('score'):.6f}")
            print(f"  winrate: {params.get('winrate', 0.0):.2%}")
    else:
        print("WARNING: optimizer.json not created")

    print("\n[OK] Phase 4 test complet!")


if __name__ == "__main__":
    test_phase4_backtester()
