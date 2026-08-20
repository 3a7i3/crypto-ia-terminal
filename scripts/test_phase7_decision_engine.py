#!/usr/bin/env python3
"""
Phase 7 Decision Engine Test — Integration meta_learner + exit_engine
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from meta_learning.memory import MetaMemory
from meta_learning.learner import MetaLearner
from meta_learning.decision_engine import DecisionEngine


def test_phase7_decision_engine():
    print("\n[STEP 1] Setup learner avec decisions passees")
    memory = MetaMemory(Path("logs/test_decisions.jsonl"))
    learner = MetaLearner(memory=memory)

    decisions = [
        {"context": {"regime": "bull_trend", "volatility": 0.02}, "pnl_pct": 0.025},
        {"context": {"regime": "bull_trend", "volatility": 0.021}, "pnl_pct": 0.018},
        {"context": {"regime": "range", "volatility": 0.01}, "pnl_pct": 0.010},
    ]

    for d in decisions:
        learner.learn_from_trade(
            context=d["context"],
            decision={"tp": 0.03, "sl": 0.015},
            pnl_pct=d["pnl_pct"],
        )

    print("[STEP 2] Create DecisionEngine")
    engine = DecisionEngine(meta_learner=learner)
    print("DecisionEngine ready")

    print("\n[STEP 3] Get decisions for different contexts")
    test_contexts = [
        {"regime": "bull_trend", "volatility": 0.0195, "confidence": 0.8},
        {"regime": "range", "volatility": 0.011, "confidence": 0.5},
        {"regime": "unknown", "volatility": 0.015, "confidence": None},
    ]

    for ctx in test_contexts:
        decision = engine.get_exit_decision(ctx)
        print(f"\nContext: {ctx['regime']}")
        print(f"  Source: {decision['source']}")
        print(f"  TP: {decision['tp']:.4f}, SL: {decision['sl']:.4f}, Trail: {decision['trailing']:.4f}")

    print("\n[STEP 4] Build exit engine from decision")
    bull_ctx = {"regime": "bull_trend", "volatility": 0.02}
    exit_engine = engine.build_exit_engine(bull_ctx)
    print(f"Exit engine built with {len(exit_engine.rules)} rules")

    print("\n[STEP 5] Test exit logic with price")
    position = {
        "entry_price": 100.0,
        "side": "BUY",
        "max_price": 102.0,
        "min_price": 99.5,
    }
    prices = [100.5, 101.0, 101.5, 102.5, 102.0]
    for price in prices:
        reason = exit_engine.check_exit(position, price)
        print(f"  Price {price:.1f}: {reason or 'HOLD'}")
        if reason:
            break

    print("\n[OK] Phase 7 test complet!")


if __name__ == "__main__":
    test_phase7_decision_engine()
