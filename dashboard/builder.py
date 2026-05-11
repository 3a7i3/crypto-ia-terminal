"""
Dashboard Builder — Affiche les données de manière lisible
Texte formaté, tableaux, charts ASCII
"""

from typing import Any
from dashboard.intelligence import DashboardIntelligence


class DashboardBuilder:
    def __init__(self, intelligence: DashboardIntelligence):
        self.intelligence = intelligence

    def print_header(self, title: str) -> None:
        """Print section header."""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)

    def print_key_metrics(self) -> None:
        """Print main metrics."""
        self.print_header("KEY METRICS")
        metrics = self.intelligence.get_key_metrics()

        print(f"\n  Total Trades:   {metrics['total_trades']:>6}")
        print(f"  Winrate:        {metrics['winrate']:>5.1%}")
        print(f"  Expectancy:     {metrics['expectancy']:>6.6f}")
        print(f"  Total PnL:      ${metrics['pnl_total']:>8.2f}")
        print(f"  Efficiency:     {metrics['efficiency']:>5.1%}")

    def print_regime_table(self) -> None:
        """Print regime performance table."""
        self.print_header("REGIME PERFORMANCE")
        regimes = self.intelligence.get_regime_intelligence()

        print(f"\n  {'Regime':<15} {'Trades':>6} {'WR':>6} {'AvgPnL':>8} {'Memories':>8} {'Status':>8}")
        print("  " + "-" * 66)

        for regime in regimes:
            print(
                f"  {regime['regime']:<15} "
                f"{regime['trades']:>6} "
                f"{regime['winrate']:>5.1%} "
                f"{regime['avg_pnl']:>7.2%} "
                f"{regime['memories']:>8} "
                f"{regime['status']:>8}"
            )

    def print_learning_stats(self) -> None:
        """Print learning evolution."""
        self.print_header("LEARNING EVOLUTION")
        learning = self.intelligence.get_learning_evolution()

        print(f"\n  Total Memories:     {learning['total_memories']:>6}")
        print(f"  Learning Winrate:   {learning['learning_winrate']:>5.1%}")
        print(f"  Learning Avg PnL:   {learning['learning_avg_pnl']:>6.4f}")
        print(f"  Best Learned:       {learning['best_learned']:>6.4f}")
        print(f"  Worst Learned:      {learning['worst_learned']:>6.4f}")

    def print_optimizer_heatmap(self) -> None:
        """Print optimizer insights."""
        self.print_header("OPTIMIZER INSIGHTS")
        insights = self.intelligence.get_optimizer_insights()

        print(f"\n  {'Regime':<15} {'TP':>8} {'SL':>8} {'TP/SL':>8} {'Score':>8} {'WR':>6}")
        print("  " + "-" * 60)

        for regime, config in insights.items():
            print(
                f"  {regime:<15} "
                f"{config['tp']:>7.4f} "
                f"{config['sl']:>7.4f} "
                f"{config['tp_sl_ratio']:>7.2f} "
                f"{config['score']:>8.6f} "
                f"{config['winrate']:>5.1%}"
            )

    def print_recommendations(self) -> None:
        """Print recommendations."""
        self.print_header("INTELLIGENCE RECOMMENDATIONS")
        recommendations = self.intelligence.get_recommendations()

        if not recommendations:
            print("\n  No recommendations at this time")
            return

        for i, rec in enumerate(recommendations, 1):
            status = rec.split(":")[0]
            msg = rec[len(status) + 1:].strip()

            symbol = {
                "EDGE": "[+]",
                "OPPORTUNITY": "[*]",
                "SUCCESS": "[!]",
                "WARNING": "[!]",
                "CAUTION": "[?]",
                "INFO": "[i]",
            }.get(status, "[-]")

            print(f"\n  {symbol} {msg}")

    def print_full_dashboard(self) -> None:
        """Print complete dashboard."""
        self.print_key_metrics()
        self.print_regime_table()
        self.print_learning_stats()
        self.print_optimizer_heatmap()
        self.print_recommendations()
        print("\n" + "=" * 70 + "\n")

    def export_json(self) -> dict[str, Any]:
        """Export as JSON."""
        return self.intelligence.generate_report()

    def export_csv(self, output_file: str = "dashboard_export.csv") -> None:
        """Export as CSV."""
        import csv

        report = self.intelligence.generate_report()

        with open(output_file, "w", newline="") as f:
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

        print(f"Exported to {output_file}")
