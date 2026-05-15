"""
market_data/connectors/binance.py — Connecteur Binance USDT-M Futures.

REST  : fapi.binance.com/fapi/v1/
WS    : fstream.binance.com/stream

Endpoints utilises :
  GET /fapi/v1/aggTrades    -> trades
  GET /fapi/v1/depth        -> orderbook
  GET /fapi/v1/klines       -> candles
  GET /fapi/v1/forceOrders  -> liquidations recentes (snapshot)

WebSocket streams :
  <symbol>@aggTrade         -> trades temps reel
  <symbol>@depth<N>@100ms   -> orderbook updates
  <symbol>@kline_<tf>       -> candles temps reel
  <symbol>@forceOrder       -> liquidations temps reel
"""

from __future__ import annotations

import json
import time
from typing import AsyncGenerator, Optional

from market_data.connectors.base import BaseConnector
from market_data.models import (
    NormalizedCandle,
    NormalizedLiquidityEvent,
    NormalizedOrderBook,
    NormalizedTrade,
)

_TIMEFRAME_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1d",
    "3d": "3d",
    "1w": "1w",
}


class BinanceFuturesConnector(BaseConnector):

    exchange_name = "binance"
    base_url = "https://fapi.binance.com/fapi/v1"
    ws_url = "wss://fstream.binance.com/stream"

    # ------------------------------------------------------------------
    # REST
    # ------------------------------------------------------------------

    def fetch_trades(self, symbol: str, limit: int = 100) -> list[NormalizedTrade]:
        sym = self.normalize_symbol(symbol)
        data = self._get_json(
            f"{self.base_url}/aggTrades",
            {
                "symbol": sym,
                "limit": min(limit, 1000),
            },
        )
        trades = []
        for t in data:
            trades.append(
                NormalizedTrade(
                    exchange=self.exchange_name,
                    symbol=sym,
                    timestamp_ms=int(t["T"]),
                    price=float(t["p"]),
                    size=float(t["q"]),
                    side=(
                        "sell" if t["m"] else "buy"
                    ),  # m=True -> maker=buyer -> taker=seller
                    trade_id=str(t["a"]),
                    raw=t,
                )
            )
        return trades

    def fetch_orderbook(self, symbol: str, depth: int = 20) -> NormalizedOrderBook:
        sym = self.normalize_symbol(symbol)
        # depth valide Binance : 5, 10, 20, 50, 100, 500, 1000
        valid_depths = [5, 10, 20, 50, 100, 500, 1000]
        d = min((v for v in valid_depths if v >= depth), default=1000)
        data = self._get_json(f"{self.base_url}/depth", {"symbol": sym, "limit": d})
        return NormalizedOrderBook(
            exchange=self.exchange_name,
            symbol=sym,
            timestamp_ms=int(data.get("T", time.time() * 1000)),
            bids=[(float(p), float(s)) for p, s in data["bids"]],
            asks=[(float(p), float(s)) for p, s in data["asks"]],
            sequence=int(data.get("lastUpdateId", 0)),
            is_snapshot=True,
        )

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 100,
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
    ) -> list[NormalizedCandle]:
        sym = self.normalize_symbol(symbol)
        tf = _TIMEFRAME_MAP.get(timeframe, "1m")
        params: dict = {"symbol": sym, "interval": tf, "limit": min(limit, 1500)}
        if start_ms:
            params["startTime"] = start_ms
        if end_ms:
            params["endTime"] = end_ms

        data = self._get_json(f"{self.base_url}/klines", params)
        candles = []
        for k in data:
            volume = float(k[5])
            buy_vol = float(k[9])  # Binance fournit le taker buy volume
            candles.append(
                NormalizedCandle(
                    exchange=self.exchange_name,
                    symbol=sym,
                    timestamp_ms=int(k[0]),
                    timeframe=timeframe,
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=volume,
                    buy_volume=buy_vol,
                    sell_volume=volume - buy_vol,
                    trade_count=int(k[8]),
                    is_closed=True,
                )
            )
        return candles

    def fetch_liquidations(
        self, symbol: str, limit: int = 50
    ) -> list[NormalizedLiquidityEvent]:
        """Liquidations recentes (snapshot REST)."""
        sym = self.normalize_symbol(symbol)
        try:
            data = self._get_json(
                f"{self.base_url}/forceOrders",
                {
                    "symbol": sym,
                    "limit": min(limit, 100),
                },
            )
        except Exception:
            return []
        events = []
        for liq in data:
            size = float(liq.get("origQty", 0))
            price = float(liq.get("price", 0) or liq.get("averagePrice", 0))
            events.append(
                NormalizedLiquidityEvent(
                    exchange=self.exchange_name,
                    symbol=sym,
                    timestamp_ms=int(liq.get("time", time.time() * 1000)),
                    event_type="liquidation",
                    side="buy" if liq.get("side") == "BUY" else "sell",
                    price=price,
                    size=size,
                    raw=liq,
                )
            )
        return events

    # ------------------------------------------------------------------
    # WebSocket (asyncio)
    # ------------------------------------------------------------------

    async def stream_trades(self, symbol: str) -> AsyncGenerator[NormalizedTrade, None]:
        """Stream aggTrade temps reel. Necessite `pip install websockets`."""
        import websockets  # type: ignore

        sym = self.normalize_symbol(symbol).lower()
        url = f"wss://fstream.binance.com/ws/{sym}@aggTrade"

        async with websockets.connect(url) as ws:
            async for msg in ws:
                t = json.loads(msg)
                yield NormalizedTrade(
                    exchange=self.exchange_name,
                    symbol=symbol.upper(),
                    timestamp_ms=int(t["T"]),
                    price=float(t["p"]),
                    size=float(t["q"]),
                    side="sell" if t["m"] else "buy",
                    trade_id=str(t["a"]),
                    raw=t,
                )

    async def stream_orderbook(
        self, symbol: str, depth: int = 20
    ) -> AsyncGenerator[NormalizedOrderBook, None]:
        """Stream depth updates temps reel (100ms). Necessite `pip install websockets`."""
        import websockets  # type: ignore

        sym = self.normalize_symbol(symbol).lower()
        d = depth if depth in (5, 10, 20) else 20
        url = f"wss://fstream.binance.com/ws/{sym}@depth{d}@100ms"

        async with websockets.connect(url) as ws:
            async for msg in ws:
                ob = json.loads(msg)
                yield NormalizedOrderBook(
                    exchange=self.exchange_name,
                    symbol=symbol.upper(),
                    timestamp_ms=int(ob.get("T", time.time() * 1000)),
                    bids=[(float(p), float(s)) for p, s in ob["b"]],
                    asks=[(float(p), float(s)) for p, s in ob["a"]],
                    sequence=int(ob.get("u", 0)),
                    is_snapshot=False,
                )

    async def stream_liquidations(
        self, symbol: str
    ) -> AsyncGenerator[NormalizedLiquidityEvent, None]:
        """Stream liquidations temps reel. Necessite `pip install websockets`."""
        import websockets  # type: ignore

        sym = self.normalize_symbol(symbol).lower()
        url = f"wss://fstream.binance.com/ws/{sym}@forceOrder"

        async with websockets.connect(url) as ws:
            async for msg in ws:
                raw = json.loads(msg)
                o = raw.get("o", raw)
                size = float(o.get("q", 0))
                price = float(o.get("p", 0) or o.get("ap", 0))
                yield NormalizedLiquidityEvent(
                    exchange=self.exchange_name,
                    symbol=symbol.upper(),
                    timestamp_ms=int(o.get("T", time.time() * 1000)),
                    event_type="liquidation",
                    side="buy" if o.get("S") == "BUY" else "sell",
                    price=price,
                    size=size,
                    raw=raw,
                )
