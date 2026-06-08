import json
from unittest.mock import MagicMock, patch

import pytest

from src.backtest.data_feed import HistoricalDataFeed
from src.backtest.mexc_feed import fetch_mexc_candles, mexc_feed

# Format réel de l'API MEXC klines
_SAMPLE_KLINES = [
    [
        1717459200000,
        "67000.0",
        "67500.0",
        "66800.0",
        "67200.0",
        "120.5",
        1717462799999,
        "8080200.0",
        3200,
        "60.2",
        "4040100.0",
        "0",
    ],
    [
        1717462800000,
        "67200.0",
        "67800.0",
        "67100.0",
        "67600.0",
        "98.3",
        1717466399999,
        "6645080.0",
        2800,
        "49.1",
        "3320540.0",
        "0",
    ],
    [
        1717466400000,
        "67600.0",
        "68100.0",
        "67400.0",
        "67900.0",
        "145.7",
        1717469999999,
        "9883230.0",
        4100,
        "72.8",
        "4941615.0",
        "0",
    ],
]


def _mock_urlopen(data):
    ctx = MagicMock()
    ctx.__enter__ = lambda s: s
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.read.return_value = json.dumps(data).encode()
    return ctx


@patch("src.backtest.mexc_feed.urllib.request.urlopen")
def test_fetch_returns_correct_count(mock_open):
    mock_open.return_value = _mock_urlopen(_SAMPLE_KLINES)
    candles = fetch_mexc_candles("BTCUSDT", "1h", 3)
    assert len(candles) == 3


@patch("src.backtest.mexc_feed.urllib.request.urlopen")
def test_candle_structure(mock_open):
    mock_open.return_value = _mock_urlopen(_SAMPLE_KLINES)
    candles = fetch_mexc_candles("BTCUSDT")
    c = candles[0]
    assert "timestamp" in c
    assert "symbol" in c
    assert "open" in c and "high" in c and "low" in c
    assert "close" in c and "volume" in c


@patch("src.backtest.mexc_feed.urllib.request.urlopen")
def test_symbol_normalized_to_upper(mock_open):
    mock_open.return_value = _mock_urlopen(_SAMPLE_KLINES)
    candles = fetch_mexc_candles("btcusdt")
    assert candles[0]["symbol"] == "BTCUSDT"


@patch("src.backtest.mexc_feed.urllib.request.urlopen")
def test_ohlcv_parsed_as_float(mock_open):
    mock_open.return_value = _mock_urlopen(_SAMPLE_KLINES)
    candles = fetch_mexc_candles("BTCUSDT")
    c = candles[0]
    assert c["open"] == 67000.0
    assert c["high"] == 67500.0
    assert c["low"] == 66800.0
    assert c["close"] == 67200.0
    assert c["volume"] == 120.5


@patch("src.backtest.mexc_feed.urllib.request.urlopen")
def test_timestamp_is_int(mock_open):
    mock_open.return_value = _mock_urlopen(_SAMPLE_KLINES)
    candles = fetch_mexc_candles("BTCUSDT")
    assert isinstance(candles[0]["timestamp"], int)


@patch("src.backtest.mexc_feed.urllib.request.urlopen")
def test_mexc_feed_returns_historical_data_feed(mock_open):
    mock_open.return_value = _mock_urlopen(_SAMPLE_KLINES)
    feed = mexc_feed("BTCUSDT", "1h", 3)
    assert isinstance(feed, HistoricalDataFeed)
    assert len(feed.candles) == 3


@patch("src.backtest.mexc_feed.urllib.request.urlopen")
def test_feed_iterable_via_next(mock_open):
    mock_open.return_value = _mock_urlopen(_SAMPLE_KLINES)
    feed = mexc_feed("ETHUSDT", "1h", 3)
    c1 = feed.next()
    c2 = feed.next()
    assert c1 is not None
    assert c2 is not None
    assert c1["timestamp"] != c2["timestamp"]


@patch("src.backtest.mexc_feed.urllib.request.urlopen")
def test_empty_response_returns_empty_feed(mock_open):
    mock_open.return_value = _mock_urlopen([])
    feed = mexc_feed("BTCUSDT")
    assert feed.next() is None
