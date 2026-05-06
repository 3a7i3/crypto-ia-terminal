from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quant_hedge_ai.agents.market.market_scanner import MarketScanner


def _fresh_candle(symbol: str = "BTC/USDT") -> dict:
    return {
        "symbol": symbol,
        "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000.0,
        "source": "ccxt_live",
    }


def test_higher_timeframe_reuses_fresh_stale_cache(monkeypatch):
    scanner = MarketScanner(symbols=["BTC/USDT"], timeframe="4h", limit=10)
    scanner._history["BTC/USDT"] = [_fresh_candle()]
    scanner._fetch_ts["BTC/USDT"] = 0.0

    def fail_fetch(symbol: str):
        raise AssertionError(f"unexpected fetch for {symbol}")

    monkeypatch.setattr(scanner, "_fetch_series", fail_fetch)

    result = scanner.scan()

    assert result["history"]["BTC/USDT"][0]["source"] == "ccxt_live"
    assert scanner.data_quality()["cached"] == 1