#!/usr/bin/env python3
"""
Phase 8 Dashboard Test — Intelligence + Visualization
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.config.settings import TRADES_LOG_FILE, OPTIMIZER_FILE
from dashboard.metrics_aggregator import MetricsAggregator
from dashboard.intelligence import DashboardIntelligence
from dashboard.builder import DashboardBuilder
from dashboard.exporter import DashboardExporter


def test_phase8_dashboard():
    print("\n" + "=" * 70)
    print("PHASE 8 — DASHBOARD INTELLIGENCE TEST")
    print("=" * 70)

    print("\n[STEP 1] Create aggregator")
    aggregator = MetricsAggregator(
        trades_log=TRADES_LOG_FILE,
        optimizer_file=OPTIMIZER_FILE,
    )
    print("MetricsAggregator ready")

    print("\n[STEP 2] Create intelligence")
    intelligence = DashboardIntelligence(aggregator)
    print("DashboardIntelligence ready")

    print("\n[STEP 3] Display dashboard")
    builder = DashboardBuilder(intelligence)
    builder.print_full_dashboard()

    print("[STEP 4] Export reports")
    exporter = DashboardExporter(intelligence)

    json_file = exporter.export_json()
    print(f"JSON exported: {json_file}")

    csv_file = exporter.export_csv()
    print(f"CSV exported: {csv_file}")

    html_file = exporter.export_html()
    print(f"HTML exported: {html_file}")

    print("\n[OK] Phase 8 test complet!")


if __name__ == "__main__":
    test_phase8_dashboard()
