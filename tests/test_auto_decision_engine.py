#!/usr/bin/env python3
"""
TEST AUTO DECISION ENGINE
Système autonome avec garde-fou
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.autonomous.auto_decision_engine import (
    Decision,
    AutoDecisionEngine,
    RiskGuard,
    ActionExecutor,
    DecisionLogger,
    AutoDecisionOrchestrator
)


def test_decision_engine():
    print("\n" + "="*70)
    print("[AUTO-1] TEST DECISION ENGINE")
    print("="*70)

    config = {
        "tp": 0.025,
        "sl": 0.010,
        "position_size": 0.1,
        "trading_enabled": True
    }

    engine = AutoDecisionEngine(config)

    # Scénario 1: Système stable
    print("\nScenario 1: Système stable")
    metrics = {"efficiency": 0.60, "mae_pct": -0.012}
    risk = {"drawdown": 0.02, "loss_streak": 1}

    decision = engine.decide(metrics, None, risk)
    print(f"  Action: {decision.action}")
    print(f"  Reason: {decision.reason}")
    print(f"  Confidence: {decision.confidence:.0%}")

    # Scénario 2: Drawdown critique
    print("\nScenario 2: Drawdown critique (6%)")
    risk = {"drawdown": 0.06, "loss_streak": 1}
    decision = engine.decide({}, None, risk)
    print(f"  Action: {decision.action}")
    print(f"  Confidence: {decision.confidence:.0%}")

    # Scénario 3: Loss streak
    print("\nScenario 3: Loss streak (4 pertes)")
    risk = {"drawdown": 0.03, "loss_streak": 4}
    decision = engine.decide({}, None, risk)
    print(f"  Action: {decision.action}")

    # Scénario 4: Efficiency faible
    print("\nScenario 4: Efficiency faible (40%)")
    metrics = {"efficiency": 0.40, "mae_pct": -0.012}
    risk = {"drawdown": 0.02, "loss_streak": 1}
    decision = engine.decide(metrics, None, risk)
    print(f"  Action: {decision.action}")
    print(f"  Params: {decision.params}")

    # Scénario 5: MAE élevé
    print("\nScenario 5: MAE élevé (-3%)")
    metrics = {"efficiency": 0.60, "mae_pct": -0.03}
    decision = engine.decide(metrics, None, risk)
    print(f"  Action: {decision.action}")
    print(f"  Params: {decision.params}")


def test_risk_guard():
    print("\n" + "="*70)
    print("[AUTO-2] TEST RISK GUARD")
    print("="*70)

    guard = RiskGuard({})

    # Test 1: TP augmentation normale
    print("\nTest 1: TP +15%")
    decision = Decision("ADJUST_TP", {"tp_factor": 1.15}, "test")
    valid, reason = guard.validate(decision)
    print(f"  Valid: {valid} ({reason})")

    # Test 2: TP augmentation excessive
    print("\nTest 2: TP +50% (trop agressif)")
    decision = Decision("ADJUST_TP", {"tp_factor": 1.50}, "test")
    valid, reason = guard.validate(decision)
    print(f"  Valid: {valid} ({reason})")

    # Test 3: SL réduction normal
    print("\nTest 3: SL -15%")
    decision = Decision("ADJUST_SL", {"sl_factor": 0.85}, "test")
    valid, reason = guard.validate(decision)
    print(f"  Valid: {valid} ({reason})")

    # Test 4: Position size reduction
    print("\nTest 4: Position size -50%")
    decision = Decision("REDUCE_RISK", {"position_size_factor": 0.5}, "test")
    valid, reason = guard.validate(decision)
    print(f"  Valid: {valid} ({reason})")

    # Test 5: Forbidden action
    print("\nTest 5: Forbidden action (INCREASE_RISK)")
    decision = Decision("INCREASE_RISK", {}, "test")
    valid, reason = guard.validate(decision)
    print(f"  Valid: {valid} ({reason})")


def test_action_executor():
    print("\n" + "="*70)
    print("[AUTO-3] TEST ACTION EXECUTOR")
    print("="*70)

    config = {
        "tp": 0.025,
        "sl": 0.010,
        "position_size": 0.1,
        "trading_enabled": True
    }

    executor = ActionExecutor(config)

    # Test 1: Adjust TP
    print("\nTest 1: Adjust TP")
    decision = Decision("ADJUST_TP", {"tp_factor": 1.20}, "increase TP")
    new_config, success, msg = executor.execute(decision)
    print(f"  Success: {success}")
    print(f"  Message: {msg}")
    print(f"  New TP: {new_config['tp']:.4f}")

    # Test 2: Adjust SL
    print("\nTest 2: Adjust SL")
    decision = Decision("ADJUST_SL", {"sl_factor": 0.80}, "tighten SL")
    new_config, success, msg = executor.execute(decision)
    print(f"  New SL: {new_config['sl']:.4f}")

    # Test 3: Reduce risk
    print("\nTest 3: Reduce position size")
    decision = Decision("REDUCE_RISK", {"position_size_factor": 0.5}, "loss streak")
    new_config, success, msg = executor.execute(decision)
    print(f"  New position size: {new_config['position_size']:.3f}")

    # Test 4: Stop trading
    print("\nTest 4: Stop trading")
    decision = Decision("STOP_TRADING", {}, "high risk")
    new_config, success, msg = executor.execute(decision)
    print(f"  Trading enabled: {new_config['trading_enabled']}")

    print(f"\nExecution history:")
    for entry in executor.execution_history[-3:]:
        print(f"  - {entry['action']}: {entry['message']}")


def test_full_orchestration():
    print("\n" + "="*70)
    print("[AUTO-4] TEST FULL ORCHESTRATION")
    print("="*70)

    config = {
        "tp": 0.025,
        "sl": 0.010,
        "position_size": 0.1,
        "trading_enabled": True
    }

    orchestrator = AutoDecisionOrchestrator(config)

    scenarios = [
        {
            "name": "Normal market",
            "metrics": {"efficiency": 0.65, "mae_pct": -0.010},
            "risk": {"drawdown": 0.02, "loss_streak": 1}
        },
        {
            "name": "High loss streak",
            "metrics": {"efficiency": 0.60, "mae_pct": -0.015},
            "risk": {"drawdown": 0.03, "loss_streak": 4}
        },
        {
            "name": "Critical drawdown",
            "metrics": {"efficiency": 0.60, "mae_pct": -0.012},
            "risk": {"drawdown": 0.07, "loss_streak": 2}
        },
        {
            "name": "Poor efficiency",
            "metrics": {"efficiency": 0.35, "mae_pct": -0.012},
            "risk": {"drawdown": 0.02, "loss_streak": 1}
        },
    ]

    for scenario in scenarios:
        print(f"\nScenario: {scenario['name']}")

        config_after, decision, executed = orchestrator.run_decision_cycle(
            scenario["metrics"],
            scenario["risk"]
        )

        print(f"  Decision: {decision.action}")
        print(f"  Executed: {executed}")
        if decision.action != "NO_ACTION":
            print(f"  Params: {decision.params}")

    # Final status
    print("\n" + "-"*70)
    print("FINAL STATUS:")
    status = orchestrator.get_status()
    print(f"  Total decisions: {status['total_decisions']}")
    print(f"  Trading enabled: {status['trading_enabled']}")
    print(f"  Current config:")
    print(f"    TP: {status['current_config']['tp']:.4f}")
    print(f"    SL: {status['current_config']['sl']:.4f}")
    print(f"    Position size: {status['current_config']['position_size']:.3f}")
    print(f"  Action breakdown (last 5): {status['action_breakdown']}")


if __name__ == "__main__":
    test_decision_engine()
    test_risk_guard()
    test_action_executor()
    test_full_orchestration()

    print("\n" + "="*70)
    print("[OK] AUTO DECISION ENGINE TESTS COMPLETE")
    print("="*70 + "\n")
