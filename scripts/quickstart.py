#!/usr/bin/env python3
"""
Quick Start — How to use the tracker system
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.core.trade_tracker import open_position, update_positions
from tracker_system.analytics.metrics import compute_all_metrics
from tracker_system.backtesting.auto_backtester import run_backtest
from meta_learning.learner import MetaLearner
from meta_learning.decision_engine import DecisionEngine


# ============================================================================
# EXAMPLE 1: Trade Entry
# ============================================================================
print("\n=== EXAMPLE 1: Opening a Trade ===\n")

pos = open_position(
    symbol="BTCUSDT",
    side="BUY",
    price=50000.0,
    size=0.1,
    regime="bull_trend",
    confidence=0.85
)
print(f"Opened: {pos['symbol']} at ${pos['entry_price']}")
print(f"Position ID: {pos['id']}")


# ============================================================================
# EXAMPLE 2: Price Update and Exit
# ============================================================================
print("\n=== EXAMPLE 2: Updating Price & Exit ===\n")

closed = update_positions(
    current_prices={"BTCUSDT": 51000.0}  # Price went up 2%
)
print(f"Positions closed: {len(closed)}")

if closed:
    for trade in closed:
        print(f"  {trade['symbol']}: PnL = {trade['pnl_pct']:.2%} (${trade['pnl_usd']:.2f})")


# ============================================================================
# EXAMPLE 3: Check Metrics
# ============================================================================
print("\n=== EXAMPLE 3: View Performance Metrics ===\n")

metrics = compute_all_metrics()
print(f"Trades: {metrics.get('trades', 0)}")
print(f"Winrate: {metrics.get('winrate', 0.0):.2%}")
print(f"Expectancy: {metrics.get('expectancy', 0.0):.6f}")
print(f"Total PnL: ${metrics.get('pnl_total', 0.0):.2f}")


# ============================================================================
# EXAMPLE 4: Optimize Exit Parameters
# ============================================================================
print("\n=== EXAMPLE 4: Optimize Exit Parameters ===\n")

optimizer = run_backtest(min_trades=5)
for regime, config in optimizer.items():
    if regime == "_meta":
        continue
    print(f"{regime}:")
    print(f"  Best TP: {config['tp']:.4f}")
    print(f"  Best SL: {config['sl']:.4f}")
    print(f"  Score: {config['score']:.6f}")


# ============================================================================
# EXAMPLE 5: Meta Learning & Smart Decisions
# ============================================================================
print("\n=== EXAMPLE 5: Use Meta Learning ===\n")

learner = MetaLearner()
engine = DecisionEngine(meta_learner=learner)

# Get smart decision for current market context
context = {
    "regime": "bull_trend",
    "volatility": 0.018,
    "confidence": 0.8
}

decision = engine.get_exit_decision(context)
print(f"Smart decision for {context['regime']}:")
print(f"  TP: {decision['tp']:.4f}")
print(f"  SL: {decision['sl']:.4f}")
print(f"  Trailing: {decision['trailing']:.4f}")
print(f"  Source: {decision['source']}")


# ============================================================================
# WORKFLOW
# ============================================================================
print("\n" + "="*60)
print("TYPICAL WORKFLOW")
print("="*60 + "\n")

print("1. BOT DETECTS SIGNAL")
print("   > Call open_position(symbol, side, price, size, regime)")
print()

print("2. EVERY TICK")
print("   > Call update_positions({symbol: price, ...})")
print("   > System checks exit rules automatically")
print()

print("3. AFTER EACH TRADE")
print("   > Logs saved to logs/trades.jsonl")
print("   > Metrics available via compute_all_metrics()")
print()

print("4. PERIODICALLY (hourly/daily)")
print("   > Run run_backtest() to optimize")
print("   > Update optimizer.json")
print()

print("5. LEARNING")
print("   > System learns from wins/losses")
print("   > Next similar context uses best past decision")
print()

print("="*60 + "\n")
