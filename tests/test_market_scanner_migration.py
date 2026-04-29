"""Migration tests replacing legacy market_radar orphan coverage."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from quant_hedge_ai.agents.market.market_scanner import MarketScanner


def test_market_scanner_synthetic_scan_returns_snapshot_and_history(monkeypatch):
    monkeypatch.setenv("MARKET_SCANNER_SYNTHETIC", "true")

    scanner = MarketScanner(symbols=["BTCUSDT", "ETHUSDT"], limit=5)
    result = scanner.scan()

    assert set(result) == {"candles", "history"}
    assert [c["symbol"] for c in result["candles"]] == ["BTCUSDT", "ETHUSDT"]
    assert set(result["history"]) == {"BTCUSDT", "ETHUSDT"}
    assert all(len(series) == 5 for series in result["history"].values())
    assert all(candle["source"] == "synthetic" for candle in result["candles"])


def test_market_scanner_uses_fresh_cache_before_refetch(monkeypatch):
    monkeypatch.setenv("MARKET_SCANNER_SYNTHETIC", "true")

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
    assert scanner.data_quality()["synthetic"] == 1
