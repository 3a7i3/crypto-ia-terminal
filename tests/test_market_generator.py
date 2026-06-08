import pytest

from src.analytics.regime_detector import RegimeDetector
from src.backtest.market_generator import (
    for_stress,
    high_volatility,
    mixed,
    range_bound,
    trend_down,
    trend_up,
)

detector = RegimeDetector()


# ------------------------------------------------------------------ #
# Structure des candles                                                 #
# ------------------------------------------------------------------ #


def test_candle_has_required_keys():
    c = trend_up(n=5)[0]
    for k in ("timestamp", "symbol", "open", "high", "low", "close", "volume"):
        assert k in c


def test_candle_high_gte_close(n=30):
    for c in trend_up(n=30):
        assert c["high"] >= c["close"]


def test_candle_low_lte_close():
    for c in range_bound(n=30):
        assert c["low"] <= c["close"]


def test_reproducible_by_seed():
    a = trend_up(n=50, seed=7)
    b = trend_up(n=50, seed=7)
    assert [c["close"] for c in a] == [c["close"] for c in b]


def test_different_seeds_differ():
    a = trend_up(n=50, seed=1)
    b = trend_up(n=50, seed=2)
    assert [c["close"] for c in a] != [c["close"] for c in b]


# ------------------------------------------------------------------ #
# Régimes détectés correctement                                         #
# ------------------------------------------------------------------ #


def test_trend_up_detected_as_trend():
    candles = trend_up(n=120, seed=0)
    assert detector.classify(candles) == "trending"


def test_trend_down_detected_as_trend():
    candles = trend_down(n=120, seed=0)
    assert detector.classify(candles) == "trending"


def test_range_detected_as_range():
    candles = range_bound(n=120, seed=0)
    assert detector.classify(candles) == "sideways"


def test_volatile_detected_as_volatile():
    candles = high_volatility(n=120, seed=0)
    assert detector.classify(candles) == "volatile"


def test_trend_up_slope_positive():
    m = detector.metrics(trend_up(n=120, seed=0))
    assert m["slope"] > 0.04


def test_trend_down_slope_negative():
    m = detector.metrics(trend_down(n=120, seed=0))
    assert m["slope"] < -0.04


def test_range_low_atr():
    m = detector.metrics(range_bound(n=120, seed=0))
    assert m["atr_pct"] < 0.018


def test_volatile_high_atr():
    m = detector.metrics(high_volatility(n=120, seed=0))
    assert m["atr_pct"] > 0.018


# ------------------------------------------------------------------ #
# for_stress : distribution des régimes                                 #
# ------------------------------------------------------------------ #


def test_for_stress_returns_candles_and_label():
    candles, label = for_stress(seed=0)
    assert isinstance(candles, list)
    assert label in ("trending", "sideways", "volatile")


def test_for_stress_label_matches_detector():
    mismatches = 0
    for seed in range(50):
        candles, expected = for_stress(seed)
        detected = detector.classify(candles)
        if detected != expected:
            mismatches += 1
    # On tolère max 2 cas limites sur 50
    assert mismatches <= 2, f"{mismatches} mismatches sur 50"


def test_stress_distribution_covers_all_regimes():
    regimes = set()
    for seed in range(20):
        _, label = for_stress(seed)
        regimes.add(label)
    assert regimes == {"trending", "sideways", "volatile"}


# ------------------------------------------------------------------ #
# Mixed                                                                 #
# ------------------------------------------------------------------ #


def test_mixed_length():
    candles = mixed(n_per_regime=30)
    assert len(candles) == 120


def test_mixed_timestamps_sequential():
    candles = mixed(n_per_regime=10)
    ts = [c["timestamp"] for c in candles]
    assert ts == list(range(40))
