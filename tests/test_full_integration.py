#!/usr/bin/env python3
"""
FULL INTEGRATION TEST
Binance API + Backtest Engine + Autonomous Decisions + Safe Mode
"""

import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.exchange.binance_client import create_binance_client
from tracker_system.backtest.backtest_engine import BacktestEngine, BacktestConfig
from tracker_system.autonomous.auto_decision_engine import AutoDecisionOrchestrator
from tracker_system.safety.safe_execution_framework import SafeExecutionFramework, SafetyConstraints


def _run_backtest_engine_report():
    config = BacktestConfig(
        initial_capital=10000.0,
        symbol="BTCUSDT",
        use_auto_decisions=True,
        use_safe_mode=True
    )

    binance = create_binance_client(mode="paper")
    auto_orchestrator = AutoDecisionOrchestrator({
        "tp": 0.025,
        "sl": 0.010,
        "position_size": 0.1,
        "trading_enabled": True
    })

    safety_constraints = SafetyConstraints()
    safe_framework = SafeExecutionFramework(safety_constraints)

    engine = BacktestEngine(
        config=config,
        binance_client=binance,
        auto_orchestrator=auto_orchestrator,
        safe_framework=safe_framework
    )
    return config, engine.run()


def _run_complete_orchestration_report():
    binance = create_binance_client(mode="paper")
    klines = binance.get_klines("BTCUSDT", interval="1h", limit=200)

    auto = AutoDecisionOrchestrator({
        "tp": 0.025,
        "sl": 0.010,
        "position_size": 0.1,
        "trading_enabled": True
    })

    safety = SafeExecutionFramework()

    config = BacktestConfig(
        initial_capital=10000.0,
        symbol="BTCUSDT",
        use_auto_decisions=True,
        use_safe_mode=True
    )

    engine = BacktestEngine(config, binance, auto, safety)
    report = engine.run()
    return config, klines, auto, safety, report


def test_binance_client():
    """Test Binance data fetching"""
    print("\n" + "="*70)
    print("[INTEGRATION-1] BINANCE CLIENT")
    print("="*70)

    # Create paper trading client (testnet mode)
    client = create_binance_client(mode="paper")
    print(f"[OK] Created Binance client in paper mode")

    # Fetch historical data
    klines = client.get_klines("BTCUSDT", interval="1h", limit=100)
    print(f"[OK] Fetched {len(klines)} candles")
    print(f"  First candle close: ${klines[0]['close']:,.2f}")
    print(f"  Last candle close: ${klines[-1]['close']:,.2f}")

    # Get account balance
    balance = client.get_account_balance()
    print(f"[OK] Account balance: {balance}")

    # Verify data structure
    assert len(klines) == 100
    assert "open" in klines[0]
    assert "close" in klines[0]
    assert "volume" in klines[0]
    print("[OK] Data structure validated")


def test_backtest_engine():
    """Test backtest engine with autonomous decisions"""
    print("\n" + "="*70)
    print("[INTEGRATION-2] BACKTEST ENGINE")
    print("="*70)

    config, report = _run_backtest_engine_report()

    print("[OK] Backtest engine initialized")
    print(f"  Initial capital: ${config.initial_capital:,.2f}")
    print(f"  Auto decisions: {config.use_auto_decisions}")
    print(f"  Safe mode: {config.use_safe_mode}")

    print("\n[OK] Backtest completed!")
    print(f"  Total trades: {report.get('num_trades', 0)}")
    print(f"  Wins: {report.get('wins', 0)} ({report.get('winrate', 0):.1f}%)")
    print(f"  Final capital: ${report.get('final_capital', 0):,.2f}")
    print(f"  Total PnL: ${report.get('total_pnl', 0):,.2f} ({report.get('total_pnl_pct', 0):.2f}%)")
    print(f"  Max drawdown: {report.get('max_dd', 0):.2f}%")

    # Validate results
    assert "final_capital" in report
    assert report["num_trades"] >= 0
    assert report["final_capital"] > 0

    # Log trades
    print("\n[OK] Last 5 trades:")
    for i, trade in enumerate(report.get("trades", [])[-5:], 1):
        pnl_str = f"+{trade['pnl_usd']:.2f}" if trade['pnl_usd'] > 0 else f"{trade['pnl_usd']:.2f}"
        print(f"  {i}. Entry: ${trade['entry']:,.0f} Exit: ${trade['exit']:,.0f} "
              f"Qty: {trade['qty']:.6f} PnL: {pnl_str}")


def test_safe_execution():
    """Test safety framework"""
    print("\n" + "="*70)
    print("[INTEGRATION-3] SAFE EXECUTION FRAMEWORK")
    print("="*70)

    constraints = SafetyConstraints()
    framework = SafeExecutionFramework(constraints)

    print("[OK] Safety framework initialized")
    print(f"  Min confidence threshold: {constraints.min_confidence_for_action:.0%}")
    print(f"  Max TP change: {constraints.max_tp_change:.0%}")
    print(f"  Max SL change: {constraints.max_sl_change:.0%}")
    print(f"  Performance drop threshold: {constraints.max_performance_drop:.0%}")

    # Simulate decision cycle
    metrics = {
        "num_trades": 25,
        "equity": 10500.0,
        "capital": 10000.0,
        "winrate": 0.58,
        "expectancy": 0.015,
        "consistency": 0.68
    }

    historical_trades = [
        {"pnl_pct": 0.025, "pnl_usd": 50},
        {"pnl_pct": -0.010, "pnl_usd": -20},
        {"pnl_pct": 0.035, "pnl_usd": 70},
    ] * 7  # 21 trades

    current_config = {"tp": 0.025, "sl": 0.010, "position_size": 0.1}

    decision = {
        "action": "ADJUST_TP",
        "params": {"tp_factor": 1.15}
    }

    new_config, executed, reason = framework.execute_decision(
        decision,
        metrics,
        historical_trades,
        current_config
    )

    print(f"\n[Decision Execution]")
    print(f"  Action: {decision['action']}")
    print(f"  Executed: {executed}")
    print(f"  Reason: {reason}")
    if executed:
        print(f"  Original TP: {current_config['tp']:.4f}")
        print(f"  New TP: {new_config['tp']:.4f}")

    # Check status
    status = framework.get_status()
    print(f"\n[Framework Status]")
    print(f"  Decisions executed: {status['decisions_executed']}")
    print(f"  Rollbacks triggered: {status['rollbacks_triggered']}")
    print(f"  Active throttle: {status['active_throttle']}")


def test_orchestration():
    """Test complete orchestration"""
    print("\n" + "="*70)
    print("[INTEGRATION-4] COMPLETE ORCHESTRATION")
    print("="*70)

    print("[OK] Creating complete trading pipeline...")

    config, klines, auto, safety, report = _run_complete_orchestration_report()
    print(f"  Fetched {len(klines)} candles from market")
    print(f"  Created autonomous decision engine")
    print(f"  Created safety execution framework")
    print(f"  Created backtest engine")
    print("\n[OK] Running complete pipeline...")

    print(f"\n[Pipeline Results]")
    print(f"  Initial: ${config.initial_capital:,.2f}")
    print(f"  Final: ${report['final_capital']:,.2f}")
    print(f"  PnL: {report['total_pnl_pct']:.2f}%")
    print(f"  Trades: {report['num_trades']}")
    print(f"  Win rate: {report['winrate']:.1f}%")
    print(f"  Max DD: {report['max_dd']:.2f}%")

    # Get autonomous engine status
    auto_status = auto.get_status()
    print(f"\n[Autonomous Engine]")
    print(f"  Total decisions: {auto_status['total_decisions']}")
    print(f"  Actions taken: {auto_status['action_breakdown']}")

    # Get safety status
    safety_status = safety.get_status()
    print(f"\n[Safety Framework]")
    print(f"  Decisions executed: {safety_status['decisions_executed']}")
    print(f"  Rollbacks triggered: {safety_status['rollbacks_triggered']}")


if __name__ == "__main__":
    try:
        test_binance_client()
        test_backtest_engine()
        test_safe_execution()
        config, _, _, _, report = _run_complete_orchestration_report()
        print("\n" + "="*70)
        print("[INTEGRATION-4] COMPLETE ORCHESTRATION")
        print("="*70)
        print(f"\n[Pipeline Results]")
        print(f"  Initial: ${config.initial_capital:,.2f}")
        print(f"  Final: ${report['final_capital']:,.2f}")
        print(f"  PnL: {report['total_pnl_pct']:.2f}%")
        print(f"  Trades: {report['num_trades']}")
        print(f"  Win rate: {report['winrate']:.1f}%")
        print(f"  Max DD: {report['max_dd']:.2f}%")

        print("\n" + "="*70)
        print("[SUCCESS] FULL INTEGRATION TEST PASSED")
        print("="*70)
        print("\n[Summary]")
        print(f"  Market data: OK (BinanceClientStub)")
        print(f"  Backtest engine: OK ({report['num_trades']} trades)")
        print(f"  Autonomous decisions: OK")
        print(f"  Safe execution: OK")
        print(f"  Complete pipeline: OK")
        print("\n[Next Steps]")
        print(f"  1. Load dashboard: python -m uvicorn dashboard.operator_dashboard_pro:app")
        print(f"  2. Deploy with live API keys when ready")
        print(f"  3. Run paper trading on Binance testnet")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
