#!/usr/bin/env python3
"""
TEST P2 — Multi-Asset Portfolio Management
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.portfolio.multi_asset import (
    AssetAllocationEngine,
    MultiAssetOptimizer,
    PortfolioPerformanceTracker
)


def test_allocation_engine():
    print("\n" + "="*70)
    print("[P2-MA-1] TEST ASSET ALLOCATION ENGINE")
    print("="*70)

    engine = AssetAllocationEngine(total_capital=10000.0)

    # Portfolio sample
    assets = [
        {
            "symbol": "BTCUSDT",
            "sharpe_ratio": 0.85,
            "volatility": 0.03,
            "category": "crypto"
        },
        {
            "symbol": "ETHUSDT",
            "sharpe_ratio": 0.72,
            "volatility": 0.035,
            "category": "crypto"
        },
        {
            "symbol": "BNBUSDT",
            "sharpe_ratio": 0.68,
            "volatility": 0.04,
            "category": "crypto"
        },
        {
            "symbol": "LINKUSDT",
            "sharpe_ratio": 0.55,
            "volatility": 0.045,
            "category": "crypto"
        },
    ]

    allocation = engine.calculate_optimal_allocation(assets)

    print("\nOptimal Allocation:")
    total = 0
    for symbol, amount in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
        if amount > 0:
            pct = (amount / 10000) * 100
            print(f"  {symbol:12s}: ${amount:8.2f} ({pct:5.1f}%)")
            total += amount

    print(f"\n  TOTAL: ${total:8.2f}")


def test_rebalancing():
    print("\n" + "="*70)
    print("[P2-MA-2] TEST PORTFOLIO REBALANCING")
    print("="*70)

    engine = AssetAllocationEngine(total_capital=10000.0)

    current_holdings = {
        "BTCUSDT": 6000,
        "ETHUSDT": 3000,
        "BNBUSDT": 1000,
    }

    target_allocation = {
        "BTCUSDT": 0.40,
        "ETHUSDT": 0.35,
        "BNBUSDT": 0.15,
        "LINKUSDT": 0.10,
    }

    print("\nCurrent Holdings:")
    for symbol, amount in current_holdings.items():
        pct = (amount / 10000) * 100
        print(f"  {symbol:12s}: ${amount:6.0f} ({pct:5.1f}%)")

    print("\nTarget Allocation:")
    for symbol, pct in target_allocation.items():
        amount = pct * 10000
        print(f"  {symbol:12s}: ${amount:6.0f} ({pct*100:5.1f}%)")

    trades = engine.rebalance_portfolio(current_holdings, target_allocation)

    print("\nRebalancing Trades:")
    for symbol, trade_size in sorted(trades.items(), key=lambda x: abs(x[1]), reverse=True):
        if trade_size != 0:
            action = "BUY" if trade_size > 0 else "SELL"
            print(f"  {action:5s} {symbol:12s}: ${abs(trade_size):6.0f}")


def test_performance_tracking():
    print("\n" + "="*70)
    print("[P2-MA-3] TEST PERFORMANCE TRACKING")
    print("="*70)

    tracker = PortfolioPerformanceTracker()

    # Simulate trades
    trades_data = [
        ("BTCUSDT", "BUY", 50000, 0.1, 150),
        ("ETHUSDT", "BUY", 2500, 1.0, 50),
        ("BNBUSDT", "BUY", 600, 5.0, 75),
        ("BTCUSDT", "SELL", 50500, 0.1, 50),
        ("ETHUSDT", "SELL", 2550, 1.0, 100),
    ]

    for symbol, side, price, qty, pnl in trades_data:
        tracker.add_trade(symbol, side, price, qty, pnl)

    breakdown = tracker.get_asset_breakdown()

    print("\nAsset Performance Breakdown:")
    total_pnl = sum(b["pnl"] for b in breakdown.values())

    for symbol, data in sorted(breakdown.items(), key=lambda x: x[1]["pnl"], reverse=True):
        print(f"  {symbol:12s}: ${data['pnl']:6.0f} ({data['pct']*100:5.1f}%) - {data['num_trades']} trades")

    print(f"\n  TOTAL PnL: ${total_pnl:6.0f}")


def test_multi_asset_optimizer():
    print("\n" + "="*70)
    print("[P2-MA-4] TEST MULTI-ASSET OPTIMIZER")
    print("="*70)

    optimizer = MultiAssetOptimizer(capital=10000.0)

    assets = [
        {
            "symbol": "BTCUSDT",
            "sharpe_ratio": 0.95,
            "volatility": 0.028,
            "category": "crypto",
            "sector": "crypto"
        },
        {
            "symbol": "ETHUSDT",
            "sharpe_ratio": 0.82,
            "volatility": 0.032,
            "category": "crypto",
            "sector": "crypto"
        },
        {
            "symbol": "BNBUSDT",
            "sharpe_ratio": 0.70,
            "volatility": 0.038,
            "category": "crypto",
            "sector": "crypto"
        },
        {
            "symbol": "SPY",
            "sharpe_ratio": 0.65,
            "volatility": 0.018,
            "category": "stock",
            "sector": "stocks"
        },
        {
            "symbol": "GLD",
            "sharpe_ratio": 0.45,
            "volatility": 0.015,
            "category": "commodity",
            "sector": "commodities"
        },
    ]

    result = optimizer.optimize_for_maximum_sharpe(assets)

    print("\nOptimization Result:")
    print(f"  Expected Sharpe Ratio: {result['expected_sharpe']:.2f}")
    print(f"  Expected Volatility: {result['expected_volatility']:.3f}")

    print("\n  Recommended Allocation:")
    for symbol, pct in sorted(result['allocation'].items(), key=lambda x: x[1], reverse=True):
        if pct > 0.01:
            print(f"    {symbol:12s}: {pct*100:5.1f}%")

    print(f"\n  Recommendation: {result['recommendation']}")

    # Sector limits
    sector_limits = optimizer.calculate_sector_limits(assets)
    print("\n  Sector Limits:")
    for sector, limit in sector_limits.items():
        print(f"    {sector:15s}: {limit*100:5.1f}%")


if __name__ == "__main__":
    test_allocation_engine()
    test_rebalancing()
    test_performance_tracking()
    test_multi_asset_optimizer()

    print("\n" + "="*70)
    print("[OK] TOUS LES TESTS P2 MULTI-ASSET REUSSIS")
    print("="*70 + "\n")
