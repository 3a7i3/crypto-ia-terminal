"""Advanced regime detection — classifies current market regime from features."""

from __future__ import annotations


class AdvancedRegimeDetector:
    def __init__(self) -> None:
        self.regimes = [
            "bull_trend",
            "bear_trend",
            "sideways",
            "high_volatility_regime",
            "flash_crash",
        ]

    def classify(self, features: dict, recent_prices: list[float] | None = None) -> str:
        momentum = float(features.get("momentum", 0.0))
        vol = float(features.get("realized_volatility", 0.0))
        # trend_strength = fraction of return-periods aligned with momentum direction
        # (high = consistent trend, low = choppy/mixed)
        trend = float(features.get("trend_strength", 0.5))

        # Vol thresholds calibrated to 5-min candle realized_vol (stdev of returns)
        if vol > 0.08:
            return "flash_crash"
        if vol > 0.04:
            return "high_volatility_regime"

        # Strong directional: >3% move with >70% of periods aligned
        if momentum > 0.03 and trend > 0.7:
            return "bull_trend"
        if momentum < -0.03 and trend > 0.7:  # was trend < 0.3 (inverted — bug)
            return "bear_trend"

        # Moderate directional: >2% move with >55% of periods aligned
        if momentum > 0.02 and trend > 0.55:
            return "bull_trend"
        if momentum < -0.02 and trend > 0.55:
            return "bear_trend"

        return "sideways"

    def suggest_strategy_type(self, regime: str) -> str:
        mapping = {
            "bull_trend": "momentum_following",
            "bear_trend": "short_strategies",
            "sideways": "mean_reversion",
            "high_volatility_regime": "volatility_harvesting",
            "flash_crash": "volatility_harvesting",
        }
        return mapping.get(regime, "neutral")
