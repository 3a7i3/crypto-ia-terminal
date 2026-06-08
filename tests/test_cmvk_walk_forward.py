import pytest

from src.backtest.data_feed import HistoricalDataFeed
from src.backtest.market_generator import trend_up
from src.backtest.walk_forward import sliding_windows


def _candles(n):
    return [
        {
            "close": 100.0 + i * 0.1,
            "high": 101.0,
            "low": 99.0,
            "symbol": "BTC",
            "timestamp": i,
            "volume": 1000.0,
        }
        for i in range(n)
    ]


def test_correct_number_of_windows():
    feeds = sliding_windows(_candles(200), window=120, step=15)
    assert len(feeds) == 6  # (200-120)//15 + 1


def test_each_feed_has_correct_window_size():
    for f in sliding_windows(_candles(300), window=120, step=15):
        assert len(f.candles) == 120


def test_feeds_are_historical_data_feeds():
    for f in sliding_windows(_candles(200), window=120, step=15):
        assert isinstance(f, HistoricalDataFeed)


def test_window_starts_are_sequential():
    feeds = sliding_windows(_candles(300), window=120, step=15)
    starts = [f.candles[0]["timestamp"] for f in feeds]
    assert starts == sorted(set(starts))


def test_too_few_candles_returns_empty():
    assert sliding_windows(_candles(50), window=120, step=15) == []


def test_exactly_one_window():
    assert len(sliding_windows(_candles(120), window=120, step=15)) == 1


def test_reset_works_after_partial_read():
    feeds = sliding_windows(_candles(150), window=120, step=15)
    f = feeds[0]
    [f.next() for _ in range(10)]
    f.reset()
    assert f.index == 0


def test_trend_windows_all_detected_as_trend():
    from src.analytics.regime_detector import RegimeDetector

    candles = trend_up(n=300, seed=42)
    feeds = sliding_windows(candles, window=120, step=20)
    detector = RegimeDetector()
    regimes = [detector.classify(f.candles) for f in feeds]
    assert all(r == "trending" for r in regimes), f"Régimes inattendus : {set(regimes)}"
