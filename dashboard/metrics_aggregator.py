"""
Metrics Aggregator — Collecte et agrège toutes les metrics
Combine: trades + optimizer + meta_learning + performance
"""

from pathlib import Path
from typing import Any

from tracker_system.analytics.metrics import compute_all_metrics
from meta_learning.memory import MetaMemory


class MetricsAggregator:
    def __init__(
        self,
        trades_log: Path,
        optimizer_file: Path,
        meta_memory_file: Path | None = None,
    ):
        self.trades_log = trades_log
        self.optimizer_file = optimizer_file
        self.meta_memory_file = meta_memory_file or Path("logs/meta_memory.jsonl")

    def get_trade_metrics(self) -> dict[str, Any]:
        """Metrics de tous les trades."""
        return compute_all_metrics(self.trades_log)

    def get_optimizer_stats(self) -> dict[str, Any]:
        """Stats du dernier optimizer."""
        try:
            import json
            with open(self.optimizer_file, "r") as f:
                opt = json.load(f)

            if not opt:
                return {}

            total_trades = opt.get("_meta", {}).get("total_trades", 0)
            regimes = {}
            for regime, config in opt.items():
                if regime != "_meta":
                    regimes[regime] = {
                        "tp": config.get("tp"),
                        "sl": config.get("sl"),
                        "trailing": config.get("trailing"),
                        "score": config.get("score"),
                        "winrate": config.get("winrate"),
                    }
            return {"total_trades": total_trades, "regimes": regimes}
        except Exception:
            return {}

    def get_learning_stats(self) -> dict[str, Any]:
        """Stats du meta learning."""
        try:
            memory = MetaMemory(self.meta_memory_file)
            entries = memory.get_all()
            if not entries:
                return {"total_memories": 0}

            pnls = [float(e.performance.get("pnl_pct", 0.0)) for e in entries]
            wins = sum(1 for p in pnls if p > 0)

            regimes = {}
            for regime in set(e.context.get("regime") for e in entries):
                regime_entries = [e for e in entries if e.context.get("regime") == regime]
                regime_pnls = [float(e.performance.get("pnl_pct", 0.0)) for e in regime_entries]
                regimes[regime] = {
                    "memories": len(regime_entries),
                    "winrate": sum(1 for p in regime_pnls if p > 0) / len(regime_pnls) if regime_pnls else 0.0,
                    "avg_pnl": sum(regime_pnls) / len(regime_pnls) if regime_pnls else 0.0,
                }

            return {
                "total_memories": len(entries),
                "winrate": wins / len(pnls) if pnls else 0.0,
                "avg_pnl_pct": sum(pnls) / len(pnls) if pnls else 0.0,
                "max_pnl_pct": max(pnls) if pnls else 0.0,
                "min_pnl_pct": min(pnls) if pnls else 0.0,
                "by_regime": regimes,
            }
        except Exception:
            return {}

    def get_regime_performance(self) -> dict[str, Any]:
        """Performance par regime."""
        metrics = self.get_trade_metrics()
        return metrics.get("regimes", [])

    def aggregate_all(self) -> dict[str, Any]:
        """Agrège TOUT."""
        return {
            "trades": self.get_trade_metrics(),
            "optimizer": self.get_optimizer_stats(),
            "learning": self.get_learning_stats(),
            "regimes": self.get_regime_performance(),
        }
