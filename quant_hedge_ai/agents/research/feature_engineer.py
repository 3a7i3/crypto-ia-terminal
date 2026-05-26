"""
DEPRECATED: Use quant_hedge_ai.agents.intelligence.feature_engineer instead.
Backward-compatible shim — adds legacy .build() alias over extract_features().
"""

from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer as _Base


class FeatureEngineer(_Base):
    """Compatibility wrapper. build() delegates to extract_features()."""

    def build(self, candles: list) -> dict:
        return self.extract_features(candles)


__all__ = ["FeatureEngineer"]
