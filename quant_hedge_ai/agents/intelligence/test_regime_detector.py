"""Tests AdvancedRegimeDetector — classification de régime de marché."""

from __future__ import annotations
import pytest
from quant_hedge_ai.agents.intelligence.regime_detector import AdvancedRegimeDetector


@pytest.fixture
def det():
    return AdvancedRegimeDetector()


class TestClassify:
    def test_flash_crash_extreme_vol(self, det):
        assert det.classify({"momentum": 0.0, "realized_volatility": 0.25, "trend_strength": 0.5}) == "flash_crash"

    def test_high_volatility_regime(self, det):
        assert det.classify({"momentum": 0.0, "realized_volatility": 0.16, "trend_strength": 0.5}) == "high_volatility_regime"

    def test_bull_trend(self, det):
        assert det.classify({"momentum": 0.05, "realized_volatility": 0.02, "trend_strength": 0.8}) == "bull_trend"

    def test_bear_trend(self, det):
        assert det.classify({"momentum": -0.05, "realized_volatility": 0.02, "trend_strength": 0.2}) == "bear_trend"

    def test_sideways_low_momentum_low_vol(self, det):
        assert det.classify({"momentum": 0.005, "realized_volatility": 0.01, "trend_strength": 0.5}) == "sideways"

    def test_default_sideways_fallback(self, det):
        # medium momentum, medium vol — no specific regime matched
        result = det.classify({"momentum": 0.02, "realized_volatility": 0.07, "trend_strength": 0.5})
        assert result == "sideways"

    def test_empty_features_defaults_to_sideways(self, det):
        assert det.classify({}) == "sideways"

    def test_regimes_list_populated(self, det):
        assert len(det.regimes) == 5


class TestSuggestStrategyType:
    def test_bull_trend_momentum(self, det):
        assert det.suggest_strategy_type("bull_trend") == "momentum_following"

    def test_bear_trend_short(self, det):
        assert det.suggest_strategy_type("bear_trend") == "short_strategies"

    def test_sideways_mean_reversion(self, det):
        assert det.suggest_strategy_type("sideways") == "mean_reversion"

    def test_high_vol_harvesting(self, det):
        assert det.suggest_strategy_type("high_volatility_regime") == "volatility_harvesting"

    def test_flash_crash_harvesting(self, det):
        assert det.suggest_strategy_type("flash_crash") == "volatility_harvesting"

    def test_unknown_regime_neutral(self, det):
        assert det.suggest_strategy_type("unknown_regime") == "neutral"
