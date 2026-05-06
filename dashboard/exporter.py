"""
Dashboard Exporter — Sauvegarde rapports en différents formats
JSON, CSV, HTML
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dashboard.intelligence import DashboardIntelligence


class DashboardExporter:
    def __init__(self, intelligence: DashboardIntelligence, output_dir: str = "logs/dashboard"):
        self.intelligence = intelligence
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_json(self, filename: str | None = None) -> Path:
        """Export report as JSON."""
        report = self.intelligence.generate_report()
        report["exported_at"] = datetime.now(timezone.utc).isoformat()

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dashboard_{timestamp}.json"

        filepath = self.output_dir / filename
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, default=str)

        return filepath

    def export_csv(self, filename: str | None = None) -> Path:
        """Export metrics as CSV."""
        import csv

        report = self.intelligence.generate_report()
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dashboard_{timestamp}.csv"

        filepath = self.output_dir / filename

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)

            metrics = report.get("key_metrics", {})
            writer.writerow(["Metric", "Value"])
            for k, v in metrics.items():
                writer.writerow([k, v])

            writer.writerow([])
            writer.writerow(["Regime", "Trades", "Winrate", "AvgPnL", "Status"])
            for regime in report.get("regime_intelligence", []):
                writer.writerow([
                    regime["regime"],
                    regime["trades"],
                    regime["winrate"],
                    regime["avg_pnl"],
                    regime["status"],
                ])

        return filepath

    def export_html(self, filename: str | None = None) -> Path:
        """Export as HTML report."""
        report = self.intelligence.generate_report()
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dashboard_{timestamp}.html"

        filepath = self.output_dir / filename

        html = self._build_html(report)
        with open(filepath, "w") as f:
            f.write(html)

        return filepath

    def _build_html(self, report: dict[str, Any]) -> str:
        """Build HTML report."""
        metrics = report.get("key_metrics", {})
        regimes = report.get("regime_intelligence", [])
        learning = report.get("learning_evolution", {})
        recommendations = report.get("recommendations", [])

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Trading Dashboard</title>
    <style>
        body {{ font-family: monospace; background: #1e1e1e; color: #d4d4d4; margin: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #4ec9b0; border-bottom: 2px solid #4ec9b0; padding-bottom: 10px; }}
        h2 {{ color: #569cd6; margin-top: 30px; }}
        .metrics {{ background: #252526; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .metric-row {{ display: flex; justify-content: space-between; padding: 5px 0; }}
        .metric-label {{ color: #9cdcfe; }}
        .metric-value {{ color: #4ec9b0; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; background: #252526; margin: 10px 0; }}
        th {{ background: #2d2d30; color: #569cd6; padding: 8px; text-align: left; border-bottom: 2px solid #569cd6; }}
        td {{ padding: 8px; border-bottom: 1px solid #3e3e42; }}
        tr:hover {{ background: #2d2d30; }}
        .status-strong {{ color: #4ec9b0; }}
        .status-good {{ color: #6a9955; }}
        .status-weak {{ color: #d7ba7d; }}
        .status-avoid {{ color: #f48771; }}
        .recommendation {{ background: #252526; padding: 10px; margin: 8px 0; border-left: 4px solid #569cd6; }}
        .rec-edge {{ border-left-color: #4ec9b0; }}
        .rec-warning {{ border-left-color: #f48771; }}
        .rec-opportunity {{ border-left-color: #d7ba7d; }}
        footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #3e3e42; color: #858585; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading Dashboard</h1>
        <p>Generated: {datetime.now(timezone.utc).isoformat()}</p>

        <h2>Key Metrics</h2>
        <div class="metrics">
            <div class="metric-row">
                <span class="metric-label">Total Trades:</span>
                <span class="metric-value">{metrics.get('total_trades', 0)}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Winrate:</span>
                <span class="metric-value">{metrics.get('winrate', 0.0):.1%}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Expectancy:</span>
                <span class="metric-value">{metrics.get('expectancy', 0.0):.6f}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Total PnL:</span>
                <span class="metric-value">${metrics.get('pnl_total', 0.0):.2f}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Efficiency:</span>
                <span class="metric-value">{metrics.get('efficiency', 0.0):.1%}</span>
            </div>
        </div>

        <h2>Regime Performance</h2>
        <table>
            <tr>
                <th>Regime</th>
                <th>Trades</th>
                <th>Winrate</th>
                <th>Avg PnL</th>
                <th>Status</th>
            </tr>
"""
        for regime in regimes:
            status_class = f"status-{regime['status'].lower()}"
            html += f"""
            <tr>
                <td>{regime['regime']}</td>
                <td>{regime['trades']}</td>
                <td>{regime['winrate']:.1%}</td>
                <td>{regime['avg_pnl']:.2%}</td>
                <td><span class="{status_class}">{regime['status']}</span></td>
            </tr>
"""
        html += """
        </table>

        <h2>Learning Evolution</h2>
        <div class="metrics">
"""
        html += f"""
            <div class="metric-row">
                <span class="metric-label">Total Memories:</span>
                <span class="metric-value">{learning.get('total_memories', 0)}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Learning Winrate:</span>
                <span class="metric-value">{learning.get('learning_winrate', 0.0):.1%}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Learning Avg PnL:</span>
                <span class="metric-value">{learning.get('learning_avg_pnl', 0.0):.4f}</span>
            </div>
        </div>

        <h2>Recommendations</h2>
"""
        for rec in recommendations:
            rec_class = "rec-edge" if "EDGE" in rec else "rec-warning" if "WARNING" in rec else "rec-opportunity" if "OPPORTUNITY" in rec else ""
            html += f'        <div class="recommendation {rec_class}">{rec}</div>\n'

        html += """
        <footer>
            <p>Dashboard powered by Phase 8 Intelligence Engine</p>
        </footer>
    </div>
</body>
</html>
"""
        return html
