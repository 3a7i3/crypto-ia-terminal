"""
Tests LiveExchangeReader — vérifie le comportement sans appel réseau réel.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from infra.live_exchange_reader import LiveExchangeReader, OrderBook, Ticker

# ── Ticker.from_ccxt ──────────────────────────────────────────────────────────


def test_ticker_from_ccxt_basic():
    raw = {"bid": 100.0, "ask": 100.1, "last": 100.05, "quoteVolume": 50_000_000.0}
    t = Ticker.from_ccxt("BTC/USDT", raw)
    assert t.symbol == "BTC/USDT"
    assert t.bid == 100.0
    assert t.ask == 100.1
    assert t.last == 100.05
    assert t.volume_24h == 50_000_000.0
    assert 0 < t.spread_pct < 1.0


def test_ticker_spread_zero_when_ask_zero():
    t = Ticker.from_ccxt("X/USDT", {"bid": 1.0, "ask": 0.0, "last": 1.0})
    assert t.spread_pct == 0.0


def test_ticker_missing_fields_defaults_to_zero():
    t = Ticker.from_ccxt("X/USDT", {})
    assert t.bid == 0.0
    assert t.ask == 0.0
    assert t.volume_24h == 0.0


# ── OrderBook ─────────────────────────────────────────────────────────────────


def test_orderbook_mid_price():
    ob = OrderBook("BTC/USDT", bids=[[100.0, 1.0]], asks=[[101.0, 1.0]])
    assert ob.mid_price == 100.5


def test_orderbook_spread_pct():
    ob = OrderBook("BTC/USDT", bids=[[99.0, 1.0]], asks=[[100.0, 1.0]])
    assert abs(ob.spread_pct - 1.0) < 0.01


def test_orderbook_empty_returns_zero():
    ob = OrderBook("BTC/USDT", bids=[], asks=[])
    assert ob.mid_price == 0.0
    assert ob.spread_pct == 0.0
    assert ob.depth_bid_usd == 0.0


def test_orderbook_depth_usd():
    bids = [[100.0, 5.0], [99.0, 3.0]]
    ob = OrderBook("X/USDT", bids=bids, asks=[])
    assert ob.depth_bid_usd == 100.0 * 5.0 + 99.0 * 3.0


# ── LiveExchangeReader — sans réseau ─────────────────────────────────────────


def _mock_reader(exchange_id: str = "binance") -> LiveExchangeReader:
    with patch("ccxt.binance") as mock_cls:
        mock_exchange = MagicMock()
        mock_cls.return_value = mock_exchange
        reader = LiveExchangeReader.__new__(LiveExchangeReader)
        reader._exchange_id = exchange_id
        reader._api_key = ""
        reader._api_secret = ""
        reader._exchange = mock_exchange
        reader._markets_loaded = True
        return reader


def test_reader_exchange_id():
    reader = _mock_reader("binance")
    assert reader.exchange_id == "binance"


def test_fetch_ticker_calls_ccxt():
    reader = _mock_reader()
    reader._exchange.fetch_ticker.return_value = {
        "bid": 50000.0,
        "ask": 50001.0,
        "last": 50000.5,
        "quoteVolume": 1_000_000_000.0,
    }
    t = reader.fetch_ticker("BTC/USDT")
    assert t.symbol == "BTC/USDT"
    assert t.last == 50000.5
    reader._exchange.fetch_ticker.assert_called_once_with("BTC/USDT")


def test_fetch_ohlcv_returns_dicts():
    reader = _mock_reader()
    reader._exchange.fetch_ohlcv.return_value = [
        [1_000_000, 100.0, 105.0, 98.0, 102.0, 5000.0],
        [1_000_060, 102.0, 107.0, 101.0, 104.0, 4000.0],
    ]
    candles = reader.fetch_ohlcv("SOL/USDT", "1h", limit=2)
    assert len(candles) == 2
    assert candles[0]["open"] == 100.0
    assert candles[0]["close"] == 102.0
    assert "ts" in candles[0]


def test_fetch_order_book_returns_orderbook():
    reader = _mock_reader()
    reader._exchange.fetch_order_book.return_value = {
        "bids": [[1.32, 1000.0], [1.31, 500.0]],
        "asks": [[1.33, 800.0], [1.34, 600.0]],
    }
    ob = reader.fetch_order_book("XRP/USDT", depth=10)
    assert ob.symbol == "XRP/USDT"
    assert ob.bids[0][0] == 1.32
    assert ob.mid_price == (1.32 + 1.33) / 2.0


def test_fetch_balance_empty_without_key():
    reader = _mock_reader()
    reader._api_key = ""
    result = reader.fetch_balance()
    assert result == {}


def test_ping_ok():
    reader = _mock_reader()
    reader._exchange.fetch_time.return_value = 1_000_000
    result = reader.ping()
    assert result["status"] == "OK"
    assert result["exchange"] == "binance"
    assert "latency_ms" in result


def test_ping_error():
    reader = _mock_reader()
    reader._exchange.fetch_time.side_effect = Exception("timeout")
    result = reader.ping()
    assert result["status"] == "ERROR"
    assert "timeout" in result["error"]


# ── Sécurité : aucune méthode d'ordre exposée ─────────────────────────────────


def test_no_create_order_method():
    reader = _mock_reader()
    assert not hasattr(reader, "create_order")
    assert not hasattr(reader, "place_order")
    assert not hasattr(reader, "cancel_order")
    assert not hasattr(reader, "create_limit_order")
