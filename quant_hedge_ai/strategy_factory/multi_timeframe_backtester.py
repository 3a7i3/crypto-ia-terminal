"""
MultiTimeframeBacktester — MVP minimaliste
Backteste sur plusieurs timeframes, calcule score de robustesse.
"""
from __future__ import annotations

from typing import Any


class SimpleMultiTimeframeBacktester:
    """Évalue stratégie sur plusieurs timeframes, évite overfit."""

    def __init__(self, timeframes: list[str] | None = None):
        self.timeframes = timeframes or ["5m", "15m", "1h"]

    def run(
        self,
        strategy: dict,
        data_by_tf: dict[str, list[dict]],
        backtester_func: Any = None,
    ) -> dict:
        """
        Backteste une stratégie sur plusieurs timeframes.

        Args:
            strategy: dict avec params de la stratégie
            data_by_tf: {"5m": [...candles], "15m": [...candles], ...}
            backtester_func: fonction qui backteste (défault: dummy)

        Returns:
            {
                "strategy": strategy,
                "results_by_tf": {tf: pnl, ...},
                "avg_pnl": float,
                "consistency_score": 0-1,
                "is_robust": bool
            }
        """
        if backtester_func is None:
            backtester_func = self._dummy_backtest

        results_by_tf = {}
        pnls = []

        for tf in self.timeframes:
            if tf not in data_by_tf:
                continue

            candles = data_by_tf[tf]
            pnl = backtester_func(strategy, candles)
            results_by_tf[tf] = pnl
            pnls.append(pnl)

        # Calcule score de robustesse
        if not pnls:
            return {
                "strategy": strategy,
                "results_by_tf": results_by_tf,
                "avg_pnl": 0.0,
                "consistency_score": 0.0,
                "is_robust": False,
            }

        avg_pnl = sum(pnls) / len(pnls)
        consistency = self._compute_consistency(pnls)

        return {
            "strategy": strategy,
            "results_by_tf": results_by_tf,
            "avg_pnl": avg_pnl,
            "consistency_score": consistency,
            "is_robust": consistency > 0.7,  # Threshold: 70%
        }

    def run_batch(
        self,
        strategies: list[dict],
        data_by_tf: dict[str, list[dict]],
        backtester_func: Any = None,
    ) -> list[dict]:
        """Backteste plusieurs stratégies."""
        results = []
        for strategy in strategies:
            result = self.run(strategy, data_by_tf, backtester_func)
            results.append(result)
        return results

    @staticmethod
    def _compute_consistency(pnls: list[float]) -> float:
        """
        Mesure la cohérence: 1.0 = tous positifs, 0.0 = tous négatifs.
        Entre les deux = mesure proportionnelle.
        """
        if not pnls:
            return 0.0

        positive = sum(1 for p in pnls if p > 0)
        return positive / len(pnls)

    @staticmethod
    def _dummy_backtest(strategy: dict, candles: list[dict]) -> float:
        """Dummy backtest pour tests — retourne PnL aléatoire."""
        if not candles:
            return 0.0

        # Très simple: si threshold bas = plus de trades = plus de gain (en dummy)
        threshold = strategy.get("threshold", 0.5)
        return 1000.0 * (1 - threshold) * 0.01  # Scaling simplifié
