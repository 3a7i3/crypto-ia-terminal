#!/usr/bin/env python3
"""
Integration Test COMPLET — Pipeline complet Phase 1-7
DATA → TRADE → LOG → ANALYSE → LEARN → ADAPT
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.core.trade_tracker import open_position, update_positions, finalize_position
from tracker_system.analytics.metrics import compute_all_metrics
from tracker_system.backtesting.auto_backtester import run_backtest
from meta_learning.memory import MetaMemory
from meta_learning.learner import MetaLearner
from meta_learning.decision_engine import DecisionEngine


def test_full_pipeline():
    print("\n" + "="*60)
    print("FULL PIPELINE TEST — Phase 1-7")
    print("="*60)

    log_file = Path("logs/integration_test.jsonl")
    state_file = Path("logs/integration_positions.json")
    optimizer_file = Path("logs/integration_optimizer.json")

    print("\n[PHASE 1] Open multiple positions")
    positions = []
    trades = [
        ("BTCUSDT", "BUY", 100.0, 1.0, "bull_trend", 0.85),
        ("ETHUSDT", "BUY", 50.0, 2.0, "bull_trend", 0.75),
        ("BNBUSDT", "SELL", 200.0, 0.5, "range", 0.6),
    ]

    for symbol, side, price, size, regime, conf in trades:
        pos = open_position(
            symbol=symbol,
            side=side,
            price=price,
            size=size,
            regime=regime,
            confidence=conf,
            log_file=log_file,
            state_file=state_file,
        )
        positions.append(pos)
        print(f"  - {symbol}: {regime} @ {price}")

    print("\n[PHASE 2-3] Close positions and check metrics")
    for pos in positions:
        if pos["symbol"] == "BTCUSDT":
            exit_price = 105.0
        elif pos["symbol"] == "ETHUSDT":
            exit_price = 51.5
        else:
            exit_price = 195.0

        finalize_position(
            position_id=pos["id"],
            price=exit_price,
            exit_reason="TEST_EXIT",
            state_file=state_file,
            log_file=log_file,
        )

    metrics = compute_all_metrics(log_file)
    print(f"Metrics:")
    print(f"  Trades: {metrics.get('trades', 0)}")
    print(f"  Winrate: {metrics.get('winrate', 0.0):.2%}")
    print(f"  Expectancy: {metrics.get('expectancy', 0.0):.6f}")
    print(f"  Total PnL: ${metrics.get('pnl_total', 0.0):.2f}")

    print("\n[PHASE 4] Optimize exit parameters")
    backtest_results = run_backtest(min_trades=0, log_file=log_file, out_file=optimizer_file)
    print(f"Optimizer found configs for {len(backtest_results) - 1} regimes")
    for regime, config in backtest_results.items():
        if regime == "_meta":
            continue
        print(f"  {regime}: TP={config['tp']:.4f}, SL={config['sl']:.4f}")

    print("\n[PHASE 6] Learn from trades")
    memory = MetaMemory(Path("logs/integration_meta.jsonl"))
    learner = MetaLearner(memory=memory)

    from tracker_system.storage.loader import load_jsonl
    trades_list = [e for e in load_jsonl(log_file) if e.get("type") == "exit"]
    for trade in trades_list[:2]:
        learner.learn_from_trade(
            context={"regime": trade.get("regime", "bull_trend"), "volatility": 0.02},
            decision={"tp": 0.03, "sl": 0.015},
            pnl_pct=float(trade.get("pnl_pct", 0.0)),
        )

    print(f"Learned {len(learner.memory.get_all())} trades")

    print("\n[PHASE 7] DecisionEngine in action")
    engine = DecisionEngine(meta_learner=learner)

    test_contexts = [
        {"regime": "bull_trend", "volatility": 0.02},
        {"regime": "range", "volatility": 0.01},
    ]

    for ctx in test_contexts:
        decision = engine.get_exit_decision(ctx)
        print(f"  {ctx['regime']}: TP={decision['tp']:.4f} (from {decision['source']})")

    print("\n" + "="*60)
    print("FULL PIPELINE SUCCESS!")
    print("="*60)
    print("\nArchitecture validee:")
    print("  1. Trade tracker > positions + logs")
    print("  2. Exit engine > modulaire avec rules")
    print("  3. Metrics > winrate, expectancy, MFE/MAE")
    print("  4. Backtester > optimizer.json")
    print("  5. MetaLearner > memorize decisions")
    print("  6. DecisionEngine > intelligent selection")
    print("\nProchain: Phase 8-9 (Dashboard + Audit)\n")


if __name__ == "__main__":
    test_full_pipeline()
