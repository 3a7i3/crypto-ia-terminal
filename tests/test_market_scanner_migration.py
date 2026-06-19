"""Migration tests replacing legacy market_radar orphan coverage."""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from quant_hedge_ai.agents.market import market_scanner as market_scanner_module
from quant_hedge_ai.agents.market.market_scanner import MarketScanner


def test_market_scanner_synthetic_scan_returns_snapshot_and_history(monkeypatch):
    monkeypatch.setenv("MARKET_SCANNER_SYNTHETIC", "true")

    scanner = MarketScanner(symbols=["BTCUSDT", "ETHUSDT"], limit=5)
    result = scanner.scan()

    assert {"candles", "history", "stability"}.issubset(set(result))
    assert [c["symbol"] for c in result["candles"]] == ["BTCUSDT", "ETHUSDT"]
    assert set(result["history"]) == {"BTCUSDT", "ETHUSDT"}
    assert all(len(series) == 5 for series in result["history"].values())
    assert all(candle["source"] == "synthetic" for candle in result["candles"])
    assert set(result["stability"]) == {"BTCUSDT", "ETHUSDT"}


def test_market_scanner_uses_fresh_cache_before_refetch(monkeypatch):
    monkeypatch.setenv("MARKET_SCANNER_SYNTHETIC", "true")
    monkeypatch.setattr(market_scanner_module, "_CACHE_TTL_SECONDS", 60.0)

    scanner = MarketScanner(symbols=["SOLUSDT"], limit=3)
    cached_series = [
        {
            "symbol": "SOLUSDT",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 104.0,
            "volume": 10_000.0,
            "source": "synthetic",
        }
    ]
    scanner._history["SOLUSDT"] = cached_series
    scanner._fetch_ts["SOLUSDT"] = time.time()

    second = scanner.scan()

    assert second["candles"][0] == cached_series[0]
    quality = scanner.data_quality()
    assert quality["cached"] == 1
    assert quality["real"] == 0


def test_market_scanner_falls_back_to_synthetic_when_fetch_fails(monkeypatch):
    monkeypatch.setenv("MARKET_SCANNER_SYNTHETIC", "false")

    scanner = MarketScanner(symbols=["BNBUSDT"], limit=4)
    monkeypatch.setattr(scanner, "_fetch_series", lambda symbol: None)

    result = scanner.scan()

    assert len(result["history"]["BNBUSDT"]) == 4
    assert result["candles"][0]["symbol"] == "BNBUSDT"
    assert result["candles"][0]["source"] == "synthetic"


def test_market_scanners_share_exchange_instance(monkeypatch):
    monkeypatch.setenv("MARKET_SCANNER_SYNTHETIC", "false")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")

    MarketScanner._exchange_pool.clear()
    MarketScanner._exchange_call_semaphores.clear()
    MarketScanner._exchange_markets_ready.clear()
    MarketScanner._exchange_market_preload_started.clear()

    created = []

    class _FakeExchange:
        def __init__(self, config):
            self.config = config
            created.append(self)

        def fetch_ohlcv(self, symbol, timeframe, limit):
            return [[1_700_000_000_000, 1.0, 2.0, 0.5, 1.5, 10.0] for _ in range(limit)]

    fake_ccxt = SimpleNamespace(mexc=lambda config: _FakeExchange(config))
    monkeypatch.setitem(sys.modules, "ccxt", fake_ccxt)

    scanner_4h = MarketScanner(symbols=["BTC/USDT"], timeframe="4h", limit=2)
    scanner_1d = MarketScanner(symbols=["BTC/USDT"], timeframe="1d", limit=2)

    scanner_4h.scan()
    scanner_1d.scan()

    assert len(created) == 1
    assert scanner_4h._exchange is scanner_1d._exchange


def test_market_scanner_refreshes_one_hour_history_incrementally(monkeypatch):
    monkeypatch.setenv("MARKET_SCANNER_SYNTHETIC", "false")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")

    MarketScanner._exchange_pool.clear()
    MarketScanner._exchange_call_semaphores.clear()
    MarketScanner._exchange_markets_ready.clear()
    MarketScanner._exchange_market_preload_started.clear()

    calls: list[int] = []
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    class _FakeExchange:
        def __init__(self, config):
            self.config = config

        def fetch_ohlcv(self, symbol, timeframe, limit):
            calls.append(limit)
            assert timeframe == "1h"
            return [
                [int((now.timestamp() - 3600) * 1000), 100.0, 111.0, 99.0, 110.0, 10.0],
                [int(now.timestamp() * 1000), 110.0, 121.0, 109.0, 120.0, 12.0],
            ]

    fake_ccxt = SimpleNamespace(mexc=lambda config: _FakeExchange(config))
    monkeypatch.setitem(sys.modules, "ccxt", fake_ccxt)

    scanner = MarketScanner(symbols=["BTC/USDT"], timeframe="1h", limit=4)
    scanner._history["BTC/USDT"] = [
        {
            "symbol": "BTC/USDT",
            "timestamp": datetime.fromtimestamp(
                now.timestamp() - 3 * 3600, tz=timezone.utc
            ).isoformat(),
            "open": 90.0,
            "high": 95.0,
            "low": 89.0,
            "close": 94.0,
            "volume": 8.0,
            "source": "ccxt_live",
        },
        {
            "symbol": "BTC/USDT",
            "timestamp": datetime.fromtimestamp(
                now.timestamp() - 2 * 3600, tz=timezone.utc
            ).isoformat(),
            "open": 94.0,
            "high": 100.0,
            "low": 93.0,
            "close": 99.0,
            "volume": 9.0,
            "source": "ccxt_live",
        },
        {
            "symbol": "BTC/USDT",
            "timestamp": datetime.fromtimestamp(
                now.timestamp() - 3600, tz=timezone.utc
            ).isoformat(),
            "open": 99.0,
            "high": 104.0,
            "low": 98.0,
            "close": 103.0,
            "volume": 10.0,
            "source": "ccxt_live",
        },
        {
            "symbol": "BTC/USDT",
            "timestamp": now.isoformat(),
            "open": 103.0,
            "high": 108.0,
            "low": 102.0,
            "close": 107.0,
            "volume": 11.0,
            "source": "ccxt_live",
        },
    ]
    scanner._fetch_ts["BTC/USDT"] = 0.0

    result = scanner.scan()

    assert calls == [2]
    assert len(result["history"]["BTC/USDT"]) == 4
    assert result["history"]["BTC/USDT"][-1]["close"] == 120.0
    assert result["candles"][0]["close"] == 120.0


def test_market_scanner_preloads_markets_once_per_shared_exchange(monkeypatch):
    monkeypatch.setenv("MARKET_SCANNER_SYNTHETIC", "false")
    monkeypatch.setenv("MARKET_SCANNER_PRELOAD_MARKETS", "true")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")

    MarketScanner._exchange_pool.clear()
    MarketScanner._exchange_call_semaphores.clear()
    MarketScanner._exchange_markets_ready.clear()
    MarketScanner._exchange_market_preload_started.clear()

    created = []
    load_markets_calls: list[str] = []
    load_markets_ready = threading.Event()

    class _FakeExchange:
        def __init__(self, config):
            self.config = config
            created.append(self)

        def load_markets(self):
            load_markets_calls.append("load_markets")
            load_markets_ready.set()
            return {"BTC/USDT": {}}

        def fetch_ohlcv(self, symbol, timeframe, limit):
            return [[1_700_000_000_000, 1.0, 2.0, 0.5, 1.5, 10.0] for _ in range(limit)]

    fake_ccxt = SimpleNamespace(mexc=lambda config: _FakeExchange(config))
    monkeypatch.setitem(sys.modules, "ccxt", fake_ccxt)

    scanner_1h = MarketScanner(symbols=["BTC/USDT"], timeframe="1h", limit=2)
    scanner_4h = MarketScanner(symbols=["BTC/USDT"], timeframe="4h", limit=2)

    scanner_1h._get_exchange()
    scanner_4h._get_exchange()

    assert load_markets_ready.wait(1.0)
    assert len(created) == 1
    assert load_markets_calls == ["load_markets"]
