#!/usr/bin/env python3
"""
Phase 8-9 Full Integration Test
Dashboard Intelligence + Audit Engine
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.config.settings import TRADES_LOG_FILE, OPTIMIZER_FILE
from dashboard.metrics_aggregator import MetricsAggregator
from dashboard.intelligence import DashboardIntelligence
from dashboard.builder import DashboardBuilder
from dashboard.exporter import DashboardExporter
from audit.trade_audit import audit_all_trades
from audit.replay_engine import ReplayEngine
from audit.decision_trace import DecisionTraceLog


def test_phase8_9_integration():
    print("\n" + "=" * 70)
    print("PHASE 8-9 FULL INTEGRATION TEST")
    print("=" * 70)

    print("\n===== PHASE 8: DASHBOARD INTELLIGENCE =====\n")

    print("[Dashboard] Create aggregator")
    aggregator = MetricsAggregator(
        trades_log=TRADES_LOG_FILE,
        optimizer_file=OPTIMIZER_FILE,
    )

    print("[Dashboard] Create intelligence")
    intelligence = DashboardIntelligence(aggregator)

    print("[Dashboard] Display dashboard")
    builder = DashboardBuilder(intelligence)
    builder.print_full_dashboard()

    print("[Dashboard] Export reports")
    exporter = DashboardExporter(intelligence)
    json_file = exporter.export_json()
    print(f"  JSON: {json_file.name}")
    html_file = exporter.export_html()
    print(f"  HTML: {html_file.name}")

    print("\n===== PHASE 9: AUDIT ENGINE =====\n")

    print("[Audit] Load and audit trades")
    audits = audit_all_trades(TRADES_LOG_FILE)
    print(f"Audits: {len(audits)} trades analyzed")

    if audits:
        print("\n[Audit] Trade quality analysis")
        qualities = {}
        for audit in audits:
            quality = audit.get_quality_label()
            qualities[quality] = qualities.get(quality, 0) + 1

        for quality, count in qualities.items():
            pct = (count / len(audits)) * 100 if audits else 0
            print(f"  {quality}: {count} ({pct:.1f}%)")

    print("\n[Audit] Replay engine")
    replay_engine = ReplayEngine(audits)
    quality_report = replay_engine.get_decision_quality_report()
    print(f"  Skilled ratio: {quality_report['skilled_ratio']:.1%}")

    if audits:
        print(f"\n[Audit] First trade analysis")
        first = audits[0]
        print(first.generate_narrative())

    print("\n[Audit] Decision trace logging")
    trace_log = DecisionTraceLog()
    print(f"  Trace file: {trace_log.log_file}")

    print("\n" + "=" * 70)
    print("PHASE 8-9 INTEGRATION COMPLETE!")
    print("=" * 70)

    print("\nCapabilities Summary:")
    print("  [Dashboard]")
    print("    - Real-time metrics aggregation")
    print("    - Regime performance breakdown")
    print("    - Learning evolution tracking")
    print("    - Export JSON/CSV/HTML")
    print()
    print("  [Audit]")
    print("    - Trade quality assessment (SKILLED/LUCKY/MISTAKE/UNLUCKY)")
    print("    - Price action analysis (MFE/MAE)")
    print("    - Replay with full decision trace")
    print("    - Alternative exit testing")
    print("    - Improvement trending")
    print()


if __name__ == "__main__":
    test_phase8_9_integration()
