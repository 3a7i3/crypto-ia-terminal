#!/usr/bin/env python3
"""
TEST P2 — ML Exit Prediction
"""

import sys
from pathlib import Path
import math

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.ml.exit_predictor import (
    ExitFeatureEngineer,
    SimpleNeuralNetwork,
    MLExitPredictor
)


def generate_trending_candles(base_price: float, trend: str, periods: int = 50) -> list:
    """Génère des bougies synthétiques"""
    candles = []
    price = base_price

    for i in range(periods):
        if trend == "bull":
            price *= 1.008  # +0.8% per candle
            noise = 0.005
        elif trend == "bear":
            price *= 0.992  # -0.8% per candle
            noise = 0.005
        elif trend == "volatile":
            price *= (1 + (0.02 if i % 2 == 0 else -0.02))
            noise = 0.01
        else:  # range
            price *= (1 + (0.001 if i % 2 == 0 else -0.001))
            noise = 0.002

        high = price * (1 + abs(noise))
        low = price * (1 - abs(noise))
        close = price
        open_price = price * 0.998

        candles.append({
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000 + i * 10
        })

    return candles


def test_feature_engineering():
    print("\n" + "="*70)
    print("[P2-1] TEST FEATURE ENGINEERING")
    print("="*70)

    engineer = ExitFeatureEngineer()

    # Generate candles
    candles = generate_trending_candles(50000.0, "bull", 50)
    entry_price = candles[5]['close']
    entry_idx = 5

    # Extract features
    features = engineer.extract_features(candles, entry_price, entry_idx)

    print("\nExtracted Features:")
    for key, value in sorted(features.items()):
        print(f"  {key:20s}: {value:8.4f}")

    print("\nFeature Interpretation:")
    print(f"  RSI: {features.get('rsi', 0):.1f} {'(Overbought)' if features.get('rsi', 0) > 70 else '(Normal)' if features.get('rsi', 0) > 30 else '(Oversold)'}")
    print(f"  Trend Strength: {features.get('trend_strength', 0):.2f} {'(Strong)' if features.get('trend_strength', 0) > 0.6 else '(Weak)'}")
    print(f"  Volatility: {features.get('volatility', 0):.4f} {'(High)' if features.get('volatility', 0) > 0.02 else '(Low)'}")


def test_neural_network():
    print("\n" + "="*70)
    print("[P2-2] TEST SIMPLE NEURAL NETWORK")
    print("="*70)

    nn = SimpleNeuralNetwork(input_size=10, hidden_size=16)

    # Test inputs
    test_cases = [
        ("Good buy signals", [0.2, 0.1, 0.8, 0.3, 0.05, 0.08, -0.02, 0.3, 0.05, 0.5]),
        ("Overbought", [0.8, 0.5, 0.9, 0.4, 0.03, 0.10, 0.0, 0.9, 0.02, 0.6]),
        ("Oversold", [-0.8, -0.5, -0.9, 0.5, -0.05, -0.10, -0.15, 0.1, -0.05, 0.7]),
        ("Neutral", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 0.5]),
    ]

    print("\nNeural Network Predictions:")
    for name, inputs in test_cases:
        prob = nn.forward(inputs)
        quality, confidence = nn.predict_exit_quality(inputs)

        print(f"\n  {name}:")
        print(f"    Raw probability: {prob:.2%}")
        print(f"    Prediction: {quality}")
        print(f"    Confidence: {confidence:.2%}")


def test_ml_exit_predictor():
    print("\n" + "="*70)
    print("[P2-3] TEST ML EXIT PREDICTOR")
    print("="*70)

    predictor = MLExitPredictor()

    scenarios = [
        ("Strong bull trend", "bull", 10),
        ("Strong bear trend", "bear", 10),
        ("Volatile market", "volatile", 15),
        ("Range bound", "range", 20),
    ]

    for scenario_name, trend, entry_bars in scenarios:
        print(f"\n{scenario_name}:")

        candles = generate_trending_candles(50000.0, trend, 50)
        entry_price = candles[entry_bars]['close']
        entry_idx = entry_bars

        prediction = predictor.predict_exit(candles, entry_price, entry_idx)

        print(f"  Entry price: ${entry_price:.2f}")
        print(f"  Current price: ${candles[-1]['close']:.2f}")
        print(f"  Distance: {(candles[-1]['close']/entry_price - 1):.2%}")

        print(f"\n  ML Prediction:")
        print(f"    Quality: {prediction['quality']}")
        print(f"    Confidence: {prediction['confidence']:.1%}")
        print(f"    Should exit: {prediction['should_exit']}")
        print(f"    Reason: {prediction['reason']}")

        features = prediction['features']
        print(f"\n  Key Metrics:")
        print(f"    RSI: {features.get('rsi', 0):.1f}")
        print(f"    MFE: {features.get('mfe_pct', 0):.2%}")
        print(f"    MAE: {features.get('mae_pct', 0):.2%}")


def test_exit_timing_comparison():
    print("\n" + "="*70)
    print("[P2-4] TEST EXIT TIMING COMPARISON")
    print("="*70)

    print("\nSimulating trade with ML exit prediction:\n")

    candles = generate_trending_candles(50000.0, "bull", 80)
    entry_price = candles[10]['close']
    entry_idx = 10

    predictor = MLExitPredictor()

    print(f"Entry at bar 10: ${entry_price:.2f}\n")

    # Check prediction at different points
    check_points = [20, 30, 40, 50, 60, 70]

    for bar in check_points:
        current_price = candles[bar]['close']
        prediction = predictor.predict_exit(candles, entry_price, entry_idx)

        print(f"Bar {bar}: Price=${current_price:.2f}, Gain={((current_price/entry_price)-1):.2%}")
        print(f"  -> ML says: {prediction['quality']} ({prediction['confidence']:.0%})")
        print(f"  -> Reason: {prediction['reason']}")
        print()


def test_feature_sensitivity():
    print("\n" + "="*70)
    print("[P2-5] TEST FEATURE SENSITIVITY")
    print("="*70)

    engineer = ExitFeatureEngineer()

    # Cas de base
    base_candles = generate_trending_candles(50000.0, "range", 50)
    entry_price = base_candles[5]['close']
    entry_idx = 5

    base_features = engineer.extract_features(base_candles, entry_price, entry_idx)

    print("\nBase case (range market):")
    print(f"  RSI: {base_features.get('rsi', 0):.1f}")
    print(f"  Trend: {base_features.get('trend_strength', 0):.2f}")
    print(f"  Volatility: {base_features.get('volatility', 0):.4f}")

    # Bull case
    bull_candles = generate_trending_candles(50000.0, "bull", 50)
    bull_features = engineer.extract_features(bull_candles, entry_price, entry_idx)

    print("\nBull market (CHANGE):")
    print(f"  RSI: {base_features.get('rsi', 0):.1f} -> {bull_features.get('rsi', 0):.1f}")
    print(f"  Trend: {base_features.get('trend_strength', 0):.2f} -> {bull_features.get('trend_strength', 0):.2f}")


if __name__ == "__main__":
    test_feature_engineering()
    test_neural_network()
    test_ml_exit_predictor()
    test_exit_timing_comparison()
    test_feature_sensitivity()

    print("\n" + "="*70)
    print("[OK] TOUS LES TESTS P2 ML EXIT REUSSIS")
    print("="*70 + "\n")
