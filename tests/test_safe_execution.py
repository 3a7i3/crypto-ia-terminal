#!/usr/bin/env python3
"""
TEST ULTRA SAFE FUND MODE
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.safety.safe_execution_framework import (
    SafetyConstraints,
    ConfidenceCalculator,
    DecisionThrottler,
    ShadowSimulator,
    PerformanceMonitor,
    SafeExecutionFramework
)


def test_confidence_calculator():
    print("\n" + "="*70)
    print("[SAFE-1] TEST CONFIDENCE CALCULATOR")
    print("="*70)

    calc = ConfidenceCalculator()

    cases = [
        ("Insufficient data", {"num_trades": 5, "consistency": 0.6, "expectancy": 0.2}),
        ("Good data", {"num_trades": 50, "consistency": 0.7, "expectancy": 0.3}),
        ("Excellent", {"num_trades": 100, "consistency": 0.8, "expectancy": 0.5}),
    ]

    for name, metrics in cases:
        conf = calc.calculate(metrics)
        print(f"\n{name}:")
        print(f"  Metrics: {metrics}")
        print(f"  Confidence: {conf:.1%}")
        print(f"  Decision: {'APPROVE' if conf > 0.6 else 'REJECT'}")


def test_decision_throttler():
    print("\n" + "="*70)
    print("[SAFE-2] TEST DECISION THROTTLER")
    print("="*70)

    constraints = SafetyConstraints(min_trades_before_decision=20)
    throttler = DecisionThrottler(constraints)

    print("\nTest 1: Too soon (only 5 trades)")
    throttler.trades_since_decision = 5
    can_decide, reason = throttler.can_make_decision()
    print(f"  Can decide: {can_decide}")
    print(f"  Reason: {reason}")

    print("\nTest 2: After 20 trades")
    throttler.trades_since_decision = 20
    can_decide, reason = throttler.can_make_decision()
    print(f"  Can decide: {can_decide}")
    print(f"  Reason: {reason}")

    print("\nTest 3: Active change lock")
    throttler.active_change = True
    from datetime import datetime
    throttler.change_applied_time = datetime.utcnow()
    can_decide, reason = throttler.can_make_decision()
    print(f"  Can decide: {can_decide}")
    print(f"  Reason: {reason}")


def test_shadow_simulator():
    print("\n" + "="*70)
    print("[SAFE-3] TEST SHADOW SIMULATOR")
    print("="*70)

    sim = ShadowSimulator(SafetyConstraints())

    historical = [{"pnl_pct": 0.02} for _ in range(20)]

    print("\nSimulate TP +15%:")
    sim_exp, reason = sim.simulate_decision({"tp_factor": 1.15}, historical)
    print(f"  Simulated expectancy: {sim_exp:.3%}")
    print(f"  Reason: {reason}")

    print("\nSimulate TP -50% (rejected):")
    sim_exp, reason = sim.simulate_decision({"tp_factor": 0.5}, historical)
    print(f"  Rejected: {sim.should_reject(sim_exp, 0.02)}")


def test_full_safe_framework():
    print("\n" + "="*70)
    print("[SAFE-4] TEST FULL SAFE EXECUTION FRAMEWORK")
    print("="*70)

    framework = SafeExecutionFramework()

    # Scenario 1: Low confidence
    print("\nScenario 1: Low confidence (insufficient data)")
    decision = {"action": "ADJUST_TP", "params": {"tp_factor": 1.15}}
    metrics = {"num_trades": 5, "consistency": 0.5, "expectancy": 0.1}
    historical = [{"pnl_pct": 0.01} for _ in range(5)]
    config = {"tp": 0.025, "sl": 0.010}

    new_config, executed, reason = framework.execute_decision(
        decision, metrics, historical, config
    )
    print(f"  Executed: {executed}")
    print(f"  Reason: {reason}")

    # Scenario 2: Good confidence
    print("\nScenario 2: High confidence (plenty of data)")
    metrics = {"num_trades": 50, "consistency": 0.75, "expectancy": 0.3}
    historical = [{"pnl_pct": 0.015} for _ in range(20)]
    framework.throttler.trades_since_decision = 20

    new_config, executed, reason = framework.execute_decision(
        decision, metrics, historical, config
    )
    print(f"  Executed: {executed}")
    print(f"  Reason: {reason}")
    if executed:
        print(f"  New TP: {new_config['tp']:.4f}")

    # Scenario 3: Throttle check
    print("\nScenario 3: Throttled (active change)")
    framework.throttler.active_change = True
    from datetime import datetime
    framework.throttler.change_applied_time = datetime.utcnow()

    new_config, executed, reason = framework.execute_decision(
        decision, metrics, historical, config
    )
    print(f"  Executed: {executed}")
    print(f"  Reason: {reason}")

    # Final status
    print("\n" + "-"*70)
    print("FRAMEWORK STATUS:")
    status = framework.get_status()
    print(f"  Decisions executed: {status['decisions_executed']}")
    print(f"  Rollbacks triggered: {status['rollbacks_triggered']}")
    print(f"  Active throttle: {status['active_throttle']}")


if __name__ == "__main__":
    test_confidence_calculator()
    test_decision_throttler()
    test_shadow_simulator()
    test_full_safe_framework()

    print("\n" + "="*70)
    print("[OK] ULTRA SAFE FUND MODE TESTS COMPLETE")
    print("="*70 + "\n")
