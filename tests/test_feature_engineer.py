"""Tests for intelligence FeatureEngineer."""

from __future__ import annotations

import pytest

from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer


@pytest.fixture
def engineer() -> FeatureEngineer:
    return FeatureEngineer()


class TestExtractFeatures:
    def test_empty_candles_returns_neutral_features(self, engineer):
        features = engineer.extract_features([])
        assert features["momentum"] == 0.0
        assert features["realized_volatility"] == 0.0
        assert features["trend_strength"] == 0.5
        assert features["avg_volume"] == 0.0
        assert features["volume_ratio"] == 1.0
        assert features["rsi"] == 50.0
        assert features["macd_hist"] == 0.0
        assert features["bb_pct"] == 0.5

    def test_single_candle_returns_volume_without_returns(self, engineer):
        features = engineer.extract_features([{"close": 100, "volume": 2500}])

        assert features["momentum"] == 0.0
        assert features["realized_volatility"] == 0.0
        assert features["trend_strength"] == 0.5
        assert features["avg_volume"] == 2500.0
        assert features["volume_ratio"] == 1.0

    def test_uptrend_computes_momentum_and_aligned_trend(self, engineer):
        candles = [
            {"close": 100, "volume": 100},
            {"close": 110, "volume": 120},
            {"close": 121, "volume": 140},
        ]

        features = engineer.extract_features(candles)

        assert features["momentum"] == pytest.approx(0.21)
        assert features["trend_strength"] == 1.0
        assert features["avg_volume"] == 120.0
        assert features["volume_ratio"] == pytest.approx(1.1667)

    def test_downtrend_counts_negative_returns_as_aligned(self, engineer):
        candles = [
            {"close": 100, "volume": 100},
            {"close": 90, "volume": 100},
            {"close": 81, "volume": 100},
        ]

        features = engineer.extract_features(candles)

        assert features["momentum"] == pytest.approx(-0.19)
        assert features["trend_strength"] == 1.0

    def test_zero_previous_close_skips_invalid_return(self, engineer):
        candles = [
            {"close": 0, "volume": 0},
            {"close": 100, "volume": 0},
            {"close": 110, "volume": 0},
        ]

        features = engineer.extract_features(candles)

        assert features["momentum"] == 0.0
        assert features["realized_volatility"] == pytest.approx(0.1)
        assert features["volume_ratio"] == 1.0

    def test_multiple_zero_closes_keep_neutral_trend(self, engineer):
        features = engineer.extract_features(
            [
                {"close": 0, "volume": 10},
                {"close": 0, "volume": 20},
            ]
        )

        assert features["momentum"] == 0.0
        assert features["realized_volatility"] == 0.0
        assert features["trend_strength"] == 0.5
        assert features["avg_volume"] == 15.0
        assert features["volume_ratio"] == pytest.approx(1.3333)


class TestDetectAnomalies:
    def test_detects_high_volatility_volume_spike_and_up_momentum(self, engineer):
        anomalies = engineer.detect_anomalies(
            {
                "realized_volatility": 0.0612,
                "volume_ratio": 3.4,
                "momentum": 0.125,
            }
        )

        assert anomalies == [
            "high_volatility:0.0612",
            "volume_spike:3.4x",
            "extreme_momentum_up:0.1250",
        ]

    def test_detects_extreme_down_momentum(self, engineer):
        anomalies = engineer.detect_anomalies(
            {
                "realized_volatility": 0.01,
                "volume_ratio": 1.0,
                "momentum": -0.151,
            }
        )

        assert anomalies == ["extreme_momentum_down:-0.1510"]

    def test_neutral_features_have_no_anomalies(self, engineer):
        assert engineer.detect_anomalies(engineer.extract_features([])) == []
