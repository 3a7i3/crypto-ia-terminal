#!/usr/bin/env python3
"""
Phase 6 Meta Learning Test — Validation apprentissage
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from meta_learning.memory import MetaMemory
from meta_learning.similarity import SimilarityEngine
from meta_learning.learner import MetaLearner


def test_phase6_meta_learning():
    print("\n[STEP 1] Create Memory and Learner")
    memory = MetaMemory(Path("logs/test_meta_memory.jsonl"))
    learner = MetaLearner(memory=memory)
    print("MetaLearner initialized")

    # Apprentissage manuel
    print("\n[STEP 2] Learn from past trades")
    trades = [
        {
            "context": {"regime": "bull_trend", "volatility": 0.02},
            "decision": {"tp": 0.03, "sl": 0.015},
            "pnl_pct": 0.025,
        },
        {
            "context": {"regime": "bull_trend", "volatility": 0.021},
            "decision": {"tp": 0.03, "sl": 0.015},
            "pnl_pct": 0.018,
        },
        {
            "context": {"regime": "range", "volatility": 0.01},
            "decision": {"tp": 0.012, "sl": 0.008},
            "pnl_pct": 0.010,
        },
    ]

    for trade in trades:
        learner.learn_from_trade(
            context=trade["context"],
            decision=trade["decision"],
            pnl_pct=trade["pnl_pct"],
        )
    print(f"Learned {len(trades)} trades")

    # Test 1: Find best decision for similar context
    print("\n[STEP 3] Find best decision for new context")
    new_context = {"regime": "bull_trend", "volatility": 0.019}
    best = learner.find_best_decision(new_context)
    if best:
        print(f"Found similar context!")
        print(f"  Decision: tp={best['decision'].get('tp')}, sl={best['decision'].get('sl')}")
        print(f"  Performance: {best['performance']:.4f}")
        print(f"  Similarity score: {best['similarity_score']:.2f}")
    else:
        print("No similar context found")

    # Test 2: Get stats by regime
    print("\n[STEP 4] Stats by regime")
    bull_stats = learner.get_stats("bull_trend")
    print(f"bull_trend: {bull_stats}")

    range_stats = learner.get_stats("range")
    print(f"range: {range_stats}")

    # Test 3: Get top decisions
    print("\n[STEP 5] Top decisions by regime")
    top_bull = learner.get_best_by_regime("bull_trend", top_n=2)
    print(f"Top bull_trend decisions: {len(top_bull)}")
    for i, dec in enumerate(top_bull):
        print(f"  #{i+1}: pnl={dec['performance'].get('pnl_pct'):.4f}")

    print("\n[OK] Phase 6 test complet!")


if __name__ == "__main__":
    test_phase6_meta_learning()
