"""
Fetche des candles OHLCV depuis l'API publique MEXC Spot (aucune clé requise).
Retourne un HistoricalDataFeed directement utilisable par BacktestEngine.
"""

import json
import urllib.parse
import urllib.request

from src.backtest.data_feed import HistoricalDataFeed

_BASE = "https://api.mexc.com/api/v3/klines"

_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "4h": "4h",
    "1d": "1d",
}


def fetch_mexc_candles(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    limit: int = 200,
) -> list[dict]:
    """
    Retourne une liste de dicts CMVK :
      {timestamp, symbol, open, high, low, close, volume}

    symbol   : ex. "BTCUSDT", "ETHUSDT"
    interval : "1m","5m","15m","30m","1h","4h","1d"
    limit    : 1–1000 (MEXC max 1000)
    """
    mexc_interval = _INTERVAL_MAP.get(interval, "60m")
    params = urllib.parse.urlencode(
        {
            "symbol": symbol.upper(),
            "interval": mexc_interval,
            "limit": min(limit, 1000),
        }
    )
    url = f"{_BASE}?{params}"

    req = urllib.request.Request(url, headers={"User-Agent": "cmvk/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = json.loads(resp.read())

    # MEXC klines format:
    # [open_time_ms, open, high, low, close, volume, close_time_ms,
    #  quote_volume, trades, taker_buy_base, taker_buy_quote, ignore]
    candles = []
    sym = symbol.upper()
    for row in raw:
        candles.append(
            {
                "timestamp": int(row[0]),
                "symbol": sym,
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
        )
    return candles


def mexc_feed(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    limit: int = 200,
) -> HistoricalDataFeed:
    """Raccourci : fetch + wrap dans HistoricalDataFeed."""
    candles = fetch_mexc_candles(symbol, interval, limit)
    return HistoricalDataFeed(candles)
