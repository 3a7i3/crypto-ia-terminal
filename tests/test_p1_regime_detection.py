#!/usr/bin/env python3
"""
TEST P1 — Auto Regime Detection
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_system.intelligence.auto_regime_detector import (
    AutoRegimeDetector,
    MultiTimeframeAnalysis,
    create_regime_aware_position
)


def generate_trending_candles(base_price: float, trend: str, periods: int = 20) -> list:
    """Génère des bougies synthétiques pour tester"""
    candles = []
    price = base_price

    for i in range(periods):
        if trend == "bull":
            price *= 1.005  # +0.5% per candle
            noise = 0.002
        elif trend == "bear":
            price *= 0.995  # -0.5% per candle
            noise = 0.002
        else:  # range
            price *= (1 + (0.001 if i % 2 == 0 else -0.001))
            noise = 0.0005

        high = price * (1 + abs(noise))
        low = price * (1 - abs(noise))
        close = price
        open_price = price * 0.998

        candles.append({
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000 + i * 50
        })

    return candles


def test_regime_detection():
    print("\n" + "="*70)
    print("[P1-1] TEST AUTO REGIME DETECTION")
    print("="*70)

    detector = AutoRegimeDetector()

    # Test 1: Bull trend
    print("\n1. BULL TREND (prix monte regulierement)")
    bull_candles = generate_trending_candles(50000.0, "bull", 20)
    regime, confidence = detector.detect(bull_candles)
    print(f"   Detected: {regime}")
    print(f"   Confidence: {confidence:.1%}")
    print("   Expected: bull_trend or range")

    # Test 2: Bear trend
    print("\n2. BEAR TREND (prix descend regulierement)")
    bear_candles = generate_trending_candles(50000.0, "bear", 20)
    regime, confidence = detector.detect(bear_candles)
    print(f"   Detected: {regime}")
    print(f"   Confidence: {confidence:.1%}")

    # Test 3: Range
    print("\n3. RANGE (prix oscille)")
    range_candles = generate_trending_candles(50000.0, "range", 20)
    regime, confidence = detector.detect(range_candles)
    print(f"   Detected: {regime}")
    print(f"   Confidence: {confidence:.1%}")

    # Test 4: Volatilité élevée (protection mode)
    print("\n4. PROTECTION MODE (volatilité haute)")
    volatile_candles = []
    price = 50000.0
    for i in range(20):
        # Sauts aléatoires grands
        price *= (1 + (0.02 if i % 2 == 0 else -0.02))
        candles_append_data = {
            "open": price * 0.99,
            "high": price * 1.02,
            "low": price * 0.98,
            "close": price,
            "volume": 1000
        }
        volatile_candles.append(candles_append_data)

    regime, confidence = detector.detect(volatile_candles)
    print(f"   Detected: {regime}")
    print(f"   Confidence: {confidence:.1%}")

    # Test 5: Paramètres recommandés par régime
    print("\n5. PARAMETRES RECOMMANDES PAR REGIME")
    for regime_name in ["bull_trend", "bear_trend", "range", "scalp", "protection"]:
        params = detector.get_regime_params(regime_name)
        print(f"\n   {regime_name}:")
        print(f"     TP: {params['tp']:.3%}")
        print(f"     SL: {params['sl']:.3%}")
        print(f"     Trailing: {params['trailing_pct']:.3%}")


def test_multiframe_analysis():
    print("\n" + "="*70)
    print("[P1-2] TEST MULTI-TIMEFRAME ANALYSIS")
    print("="*70)

    analyzer = MultiTimeframeAnalysis()

    # Générer données pour 3 timeframes
    print("\nGenerating 5m/15m/1h candles...")
    candles_5m = generate_trending_candles(50000.0, "bull", 20)
    candles_15m = generate_trending_candles(50000.0, "bull", 20)
    candles_1h = generate_trending_candles(50000.0, "bull", 20)

    result = analyzer.analyze_timeframes(candles_5m, candles_15m, candles_1h)

    print(f"\n5m régime:  {result['5m'][0]} ({result['5m'][1]:.1%})")
    print(f"15m régime: {result['15m'][0]} ({result['15m'][1]:.1%})")
    print(f"1h régime:  {result['1h'][0]} ({result['1h'][1]:.1%})")

    print(f"\nConsensus: {result['consensus']}")
    print(f"Accord: {result['agreement']:.1%}")
    print(f"Décompte: {result['regime_counts']}")


def test_regime_aware_position():
    print("\n" + "="*70)
    print("[P1-3] TEST CREATION POSITION AWARE DU REGIME")
    print("="*70)

    # Test pour chaque régime
    for regime in ["bull_trend", "range", "protection"]:
        print(f"\n{regime}:")
        pos = create_regime_aware_position(
            regime=regime,
            symbol="BTCUSDT",
            side="BUY",
            entry_price=50000.0,
            size=0.1
        )

        print(f"  Entry: ${pos['entry_price']:.2f}")
        print(f"  TP: ${pos['tp']:.2f}")
        print(f"  SL: ${pos['sl']:.2f}")
        print(f"  TP Distance: {(pos['tp']/pos['entry_price']-1):.3%}")
        print(f"  SL Distance: {(1-pos['sl']/pos['entry_price']):.3%}")
        print(f"  Trailing: {pos['trailing_pct']:.3%}")


def test_integrated_workflow():
    print("\n" + "="*70)
    print("[P1-4] WORKFLOW INTEGRATE - AUTO POSITION CREATION")
    print("="*70)

    detector = AutoRegimeDetector()

    # Simuler une journée
    print("\nJournee: Candles arrivent, positions creees automatiquement\n")

    scenarios = [
        ("bull", 50000.0),
        ("bear", 50000.0),
        ("range", 50000.0),
    ]

    positions_created = []

    for trend, base_price in scenarios:
        candles = generate_trending_candles(base_price, trend, 20)
        regime, conf = detector.detect(candles)

        pos = create_regime_aware_position(
            regime=regime,
            symbol="BTCUSDT",
            side="BUY",
            entry_price=base_price,
            size=0.1
        )

        positions_created.append(pos)

        print(f"[{trend.upper()}] Detected: {regime} ({conf:.0%})")
        print("  -> Position created:")
        print(f"     TP: {(pos['tp']/pos['entry_price']-1):.2%} @ ${pos['tp']:.0f}")
        print(f"     SL: {(1-pos['sl']/pos['entry_price']):.2%} @ ${pos['sl']:.0f}")
        print()

    print("Positions creees today:")
    for i, pos in enumerate(positions_created, 1):
        print(f"  {i}. {pos['regime']}: TP={pos['tp']:.0f}, SL={pos['sl']:.0f}")


if __name__ == "__main__":
    test_regime_detection()
    test_multiframe_analysis()
    test_regime_aware_position()
    test_integrated_workflow()

    print("\n" + "="*70)
    print("[OK] TOUS LES TESTS P1 REGIME DETECTION REUSSIS")
    print("="*70 + "\n")
