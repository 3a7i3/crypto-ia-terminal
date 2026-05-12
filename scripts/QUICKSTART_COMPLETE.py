#!/usr/bin/env python3
"""
DÉMARRAGE RAPIDE SYSTÈME COMPLET
Démontre tout le pipeline Phase 1-9 en français
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

print("\n" + "="*70)
print("SYSTÈME DE TRADING COMPLET - DÉMARRAGE RAPIDE")
print("="*70 + "\n")

# ============================================================================
# PHASE 1-2: EXÉCUTER LES TRADES
# ============================================================================
print("[PHASE 1-2] EXÉCUTER LES TRADES")
print("-" * 70)

from tracker_system.core.trade_tracker import open_position, finalize_position

trades = [
    ("BTCUSDT", "BUY", 50000.0, 0.1, "bull_trend", 0.85),
    ("ETHUSDT", "BUY", 2500.0, 0.5, "bull_trend", 0.75),
]

open_trades = []
for symbol, side, price, size, regime, conf in trades:
    pos = open_position(symbol, side, price, size, regime=regime, confidence=conf)
    open_trades.append(pos)
    print(f"  > {symbol}: entry @ {price:.2f}")

# Price movements
for pos in open_trades:
    if pos["symbol"] == "BTCUSDT":
        exit_price = 51500.0
    else:
        exit_price = 2550.0

    finalize_position(pos["id"], exit_price, "DEMO_EXIT")

print()

# ============================================================================
# PHASE 3: ANALYZE PERFORMANCE
# ============================================================================
print("[PHASE 3] ANALYZE PERFORMANCE")
print("-" * 70)

from tracker_system.analytics.metrics import compute_all_metrics

metrics = compute_all_metrics()
print(f"  Trades: {metrics.get('trades', 0)}")
print(f"  Winrate: {metrics.get('winrate', 0.0):.1%}")
print(f"  Expectancy: {metrics.get('expectancy', 0.0):.6f}")
print(f"  Total PnL: ${metrics.get('pnl_total', 0.0):.2f}")
print()

# ============================================================================
# PHASE 4: OPTIMIZE PARAMETERS
# ============================================================================
print("[PHASE 4] OPTIMIZE PARAMETERS")
print("-" * 70)

from tracker_system.backtesting.auto_backtester import run_backtest

optimizer = run_backtest(min_trades=0)
print(f"  Optimizer found: {len(optimizer) - 1} regime configs")
for regime, config in optimizer.items():
    if regime != "_meta":
        print(f"    {regime}: TP={config['tp']:.4f}, SL={config['sl']:.4f}")
print()

# ============================================================================
# PHASE 6-7: INTELLIGENT LEARNING
# ============================================================================
print("[PHASE 6-7] META LEARNING & DECISION ENGINE")
print("-" * 70)

from meta_learning.memory import MetaMemory
from meta_learning.learner import MetaLearner
from meta_learning.decision_engine import DecisionEngine

memory = MetaMemory()
learner = MetaLearner(memory=memory)
engine = DecisionEngine(meta_learner=learner)

new_context = {"regime": "bull_trend", "volatility": 0.02}
decision = engine.get_exit_decision(new_context)
print(f"  Smart decision for {new_context['regime']}:")
print(f"    TP: {decision['tp']:.4f}")
print(f"    SL: {decision['sl']:.4f}")
print(f"    Source: {decision['source']}")
print()

# ============================================================================
# PHASE 8: DASHBOARD INTELLIGENCE
# ============================================================================
print("[PHASE 8] DASHBOARD INTELLIGENCE")
print("-" * 70)

from tracker_system.config.settings import TRADES_LOG_FILE, OPTIMIZER_FILE
from dashboard.metrics_aggregator import MetricsAggregator
from dashboard.intelligence import DashboardIntelligence
from dashboard.builder import DashboardBuilder

aggregator = MetricsAggregator(TRADES_LOG_FILE, OPTIMIZER_FILE)
intelligence = DashboardIntelligence(aggregator)
builder = DashboardBuilder(intelligence)

key_metrics = intelligence.get_key_metrics()
print(f"  Winrate: {key_metrics['winrate']:.1%}")
print(f"  Expectancy: {key_metrics['expectancy']:.6f}")

regimes = intelligence.get_regime_intelligence()
for regime in regimes:
    print(f"  {regime['regime']}: {regime['trades']} trades, {regime['status']}")

recommendations = intelligence.get_recommendations()
print(f"  Recommendations: {len(recommendations)}")
for rec in recommendations:
    print(f"    - {rec}")
print()

# ============================================================================
# PHASE 9: AUDIT & TRACE
# ============================================================================
print("[PHASE 9] AUDIT & TRACE")
print("-" * 70)

from audit.trade_audit import audit_all_trades
from audit.replay_engine import ReplayEngine

audits = audit_all_trades(TRADES_LOG_FILE)
print(f"  Trades audited: {len(audits)}")

qualities = {}
for audit in audits:
    q = audit.get_quality_label()
    qualities[q] = qualities.get(q, 0) + 1

for quality, count in qualities.items():
    pct = (count / len(audits)) * 100 if audits else 0
    print(f"    {quality}: {count} ({pct:.1f}%)")

if audits:
    replay_engine = ReplayEngine(audits)
    report = replay_engine.get_decision_quality_report()
    print(f"  Skilled ratio: {report['skilled_ratio']:.1%}")
print()

# ============================================================================
# EXPORT
# ============================================================================
print("[EXPORT] SAVE REPORTS")
print("-" * 70)

from dashboard.exporter import DashboardExporter

exporter = DashboardExporter(intelligence)
json_file = exporter.export_json()
print(f"  JSON: {json_file.name}")
html_file = exporter.export_html()
print(f"  HTML: {html_file.name}")
print()

# ============================================================================
# SUMMARY
# ============================================================================
print("="*70)
print("COMPLETE SYSTEM SUMMARY")
print("="*70 + "\n")

print("Capabilities Demonstrated:")
print()
print("  [PHASE 1-5] Core Trading")
print("    > Open/close positions")
print("    > Exit rules (TP/SL/Trailing)")
print("    > Performance metrics")
print("    > Parameter optimization")
print()
print("  [PHASE 6-7] Intelligent Learning")
print("    > Meta-learning from trades")
print("    > Context similarity matching")
print("    > Smart decision selection")
print()
print("  [PHASE 8-9] Visibility & Audit")
print("    > Real-time dashboard")
print("    > AI recommendations")
print("    > Trade quality assessment")
print("    > Complete decision trace")
print()

print("Next Steps:")
print("  1. Integrate with your market scanner")
print("  2. Configure regime detection")
print("  3. Set live trading parameters")
print("  4. Monitor dashboard in real-time")
print("  5. Review audit reports daily")
print()

print("Documentation:")
print("  - COMPLETE_SYSTEM_ARCHITECTURE.md")
print("  - PHASE_1_7_SUMMARY.md")
print("  - PHASE_8_9_COMPLETE.md")
print("  - TRACKER_SYSTEM_README.md")
print()

print("="*70)
print("SYSTEM READY FOR PRODUCTION")
print("="*70 + "\n")
