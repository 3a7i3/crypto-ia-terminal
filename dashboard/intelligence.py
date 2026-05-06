"""
Dashboard Intelligence — Analyse intelligente pour trading
Génère insights, détecte patterns, donne recommendations
"""

from typing import Any
from dashboard.metrics_aggregator import MetricsAggregator


class DashboardIntelligence:
    def __init__(self, aggregator: MetricsAggregator):
        self.aggregator = aggregator

    def get_key_metrics(self) -> dict[str, Any]:
        """Métriques principales."""
        all_data = self.aggregator.aggregate_all()
        trades = all_data.get("trades", {})

        return {
            "total_trades": trades.get("trades", 0),
            "winrate": trades.get("winrate", 0.0),
            "expectancy": trades.get("expectancy", 0.0),
            "pnl_total": trades.get("pnl_total", 0.0),
            "efficiency": trades.get("efficiency", 0.0),
        }

    def get_regime_intelligence(self) -> list[dict[str, Any]]:
        """Intelligence par regime."""
        regimes = self.aggregator.get_regime_performance()
        learning = self.aggregator.get_learning_stats().get("by_regime", {})

        intelligence = []
        for regime_data in regimes:
            regime = regime_data.get("regime")
            learning_data = learning.get(regime, {})

            insight = {
                "regime": regime,
                "trades": regime_data.get("trades", 0),
                "winrate": regime_data.get("winrate", 0.0),
                "avg_pnl": regime_data.get("avg_pnl_pct", 0.0),
                "memories": learning_data.get("memories", 0),
                "learning_winrate": learning_data.get("winrate", 0.0),
                "status": self._regime_status(regime_data, learning_data),
            }
            intelligence.append(insight)

        return intelligence

    def _regime_status(self, trade_data: dict, learn_data: dict) -> str:
        wr = trade_data.get("winrate", 0.0)
        if wr >= 0.60:
            return "STRONG"
        elif wr >= 0.50:
            return "GOOD"
        elif wr >= 0.40:
            return "WEAK"
        else:
            return "AVOID"

    def get_learning_evolution(self) -> dict[str, Any]:
        """Comment apprend le système."""
        learning = self.aggregator.get_learning_stats()
        return {
            "total_memories": learning.get("total_memories", 0),
            "learning_winrate": learning.get("winrate", 0.0),
            "learning_avg_pnl": learning.get("avg_pnl_pct", 0.0),
            "best_learned": learning.get("max_pnl_pct", 0.0),
            "worst_learned": learning.get("min_pnl_pct", 0.0),
        }

    def get_optimizer_insights(self) -> dict[str, Any]:
        """Insights sur optimization."""
        opt = self.aggregator.get_optimizer_stats()
        regimes = opt.get("regimes", {})

        insights = {}
        for regime, config in regimes.items():
            insights[regime] = {
                "tp": config.get("tp"),
                "sl": config.get("sl"),
                "tp_sl_ratio": config.get("tp", 0.0) / max(config.get("sl", 0.001), 0.001),
                "score": config.get("score"),
                "winrate": config.get("winrate"),
            }

        return insights

    def get_recommendations(self) -> list[str]:
        """Recommandations basées sur données."""
        recommendations = []
        key_metrics = self.get_key_metrics()
        regimes = self.get_regime_intelligence()
        learning = self.get_learning_evolution()

        if key_metrics.get("expectancy", 0.0) > 0.01:
            recommendations.append("EDGE: System has positive expectancy (E > 0.01)")

        if key_metrics.get("winrate", 0.0) < 0.45:
            recommendations.append("WARNING: Winrate below 45% - review exit strategy")

        if learning.get("total_memories", 0) < 10:
            recommendations.append("INFO: Not enough historical data to leverage meta learning")

        for regime in regimes:
            if regime["status"] == "STRONG":
                recommendations.append(f"OPPORTUNITY: {regime['regime']} is strong ({regime['winrate']:.0%})")
            elif regime["status"] == "AVOID":
                recommendations.append(f"CAUTION: {regime['regime']} has poor winrate ({regime['winrate']:.0%})")

        if learning.get("learning_winrate", 0.0) > key_metrics.get("winrate", 0.0):
            recommendations.append("SUCCESS: Meta learning outperforming base strategy")

        return recommendations

    def generate_report(self) -> dict[str, Any]:
        """Rapport complet."""
        return {
            "key_metrics": self.get_key_metrics(),
            "regime_intelligence": self.get_regime_intelligence(),
            "learning_evolution": self.get_learning_evolution(),
            "optimizer_insights": self.get_optimizer_insights(),
            "recommendations": self.get_recommendations(),
        }
