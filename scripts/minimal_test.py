#!/usr/bin/env python3
"""
Minimal Test — Prouve que tout fonctionne en 3 lignes
"""

import sys
sys.path.insert(0, ".")

from tracker_system.core.trade_tracker import open_position, finalize_position
from tracker_system.analytics.metrics import compute_all_metrics

# Open
pos = open_position("TEST", "BUY", 100, 1, regime="bull_trend")
print(f"Trade opened: {pos['id']}")

# Close
finalized = finalize_position(pos["id"], 105, "TEST_EXIT")
print(f"Trade closed: PnL={finalized['pnl_pct']:.2%} (${finalized['pnl_usd']:.2f})")

# Metrics
m = compute_all_metrics()
print(f"Metrics: {m['trades']} trades, {m['winrate']:.0%} WR, E={m['expectancy']:.4f}")
