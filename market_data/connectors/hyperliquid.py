"""
market_data/connectors/hyperliquid.py — Connecteur Hyperliquid Perps.

API REST  : https://api.hyperliquid.xyz/info  (POST JSON)
WebSocket : wss://api.hyperliquid.xyz/ws

Particularites Hyperliquid :
  - Pas de symbole au format "BTCUSDT", utilise "BTC" (perpetuals USDC-settled)
  - REST = POST avec JSON body (pas de query params)
  - Orderbook = L2 snapshot avec levels agrege
  - Trades = "allMids" + "recentTrades" via POST
  - WebSocket souscription par message JSON
"""

from __future__ import annotations

import json
import time
from typing import AsyncGenerator, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from market_data.connectors.base import BaseConnector
from market_data.models import NormalizedCandle, NormalizedOrderBook, NormalizedTrade

_BASE = "https://api.hyperliquid.xyz/info"
_WS = "wss://api.hyperliquid.xyz/ws"

# Map timeframe unifie -> interval Hyperliquid
_TF_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


class HyperliquidConnector(BaseConnector):

    exchange_name = "hyperliquid"
    base_url = _BASE
    ws_url = _WS

    def _post(self, body: dict) -> dict | list:
        """POST JSON a l'API Hyperliquid (format specifique)."""
        payload = json.dumps(body).encode()
        req = Request(
            _BASE,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode())
        except URLError as exc:
            self._log.error("Hyperliquid API error: %s", exc)
            raise

    def _hl_symbol(self, symbol: str) -> str:
        """Convertit "BTCUSDT" -> "BTC" pour Hyperliquid."""
        s = symbol.upper()
        for suffix in ("USDT", "USDC", "USD", "PERP"):
            if s.endswith(suffix):
                return s[: -len(suffix)]
        return s

    # ------------------------------------------------------------------
    # REST
    # ------------------------------------------------------------------

    def fetch_trades(self, symbol: str, limit: int = 100) -> list[NormalizedTrade]:
        coin = self._hl_symbol(symbol)
        data = self._post({"type": "recentTrades", "coin": coin})
        trades = []
        for t in data[:limit]:
            # Hyperliquid: {"time": ms, "px": "price", "sz": "size", "side": "B"/"A"}
            side = "buy" if t.get("side") in ("B", "buy") else "sell"
            trades.append(
                NormalizedTrade(
                    exchange=self.exchange_name,
                    symbol=self.normalize_symbol(symbol),
                    timestamp_ms=int(t.get("time", time.time() * 1000)),
                    price=float(t.get("px", 0)),
                    size=float(t.get("sz", 0)),
                    side=side,
                    trade_id=str(t.get("tid", "")),
                    raw=t,
                )
            )
        return trades

    def fetch_orderbook(self, symbol: str, depth: int = 20) -> NormalizedOrderBook:
        coin = self._hl_symbol(symbol)
        data = self._post({"type": "l2Book", "coin": coin})
        # Hyperliquid: {"levels": [[bid_list], [ask_list]]}
        # Each level: {"px": "price", "sz": "size", "n": num_orders}
        levels = data.get("levels", [[], []])
        bids_raw = levels[0] if len(levels) > 0 else []
        asks_raw = levels[1] if len(levels) > 1 else []

        bids = [(float(b["px"]), float(b["sz"])) for b in bids_raw[:depth]]
        asks = [(float(a["px"]), float(a["sz"])) for a in asks_raw[:depth]]
        # Hyperliquid fournit bids en ordre croissant -> renverser
        bids = sorted(bids, key=lambda x: x[0], reverse=True)
        asks = sorted(asks, key=lambda x: x[0])

        return NormalizedOrderBook(
            exchange=self.exchange_name,
            symbol=self.normalize_symbol(symbol),
            timestamp_ms=int(data.get("time", time.time() * 1000)),
            bids=bids,
            asks=asks,
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
        coin = self._hl_symbol(symbol)
        tf = _TF_MAP.get(timeframe, "1m")
        now_ms = int(time.time() * 1000)

        # Hyperliquid necessite startTime et endTime
        end = end_ms or now_ms
        # Estimer startTime selon le timeframe et la limite
        tf_ms = {
            "1m": 60_000,
            "5m": 300_000,
            "15m": 900_000,
            "30m": 1_800_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
            "1d": 86_400_000,
        }
        start = start_ms or (end - tf_ms.get(timeframe, 60_000) * limit)

        data = self._post(
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": coin,
                    "interval": tf,
                    "startTime": start,
                    "endTime": end,
                },
            }
        )
        candles = []
        for k in data:
            volume = float(k.get("v", 0))
            buy_vol = float(
                k.get("vb", 0)
            )  # Hyperliquid: "vb" = buy volume si disponible
            candles.append(
                NormalizedCandle(
                    exchange=self.exchange_name,
                    symbol=self.normalize_symbol(symbol),
                    timestamp_ms=int(k.get("t", 0)),
                    timeframe=timeframe,
                    open=float(k.get("o", 0)),
                    high=float(k.get("h", 0)),
                    low=float(k.get("l", 0)),
                    close=float(k.get("c", 0)),
                    volume=volume,
                    buy_volume=buy_vol,
                    sell_volume=volume - buy_vol,
                    trade_count=int(k.get("n", 0)),
                    is_closed=True,
                )
            )
        return candles[-limit:]

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    async def stream_trades(self, symbol: str) -> AsyncGenerator[NormalizedTrade, None]:
        """Stream trades Hyperliquid. Necessite `pip install websockets`."""
        import websockets  # type: ignore

        coin = self._hl_symbol(symbol)
        sub = json.dumps(
            {"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}
        )

        async with websockets.connect(_WS) as ws:
            await ws.send(sub)
            async for msg in ws:
                payload = json.loads(msg)
                if payload.get("channel") != "trades":
                    continue
                for t in payload.get("data", []):
                    side = "buy" if t.get("side") in ("B", "buy") else "sell"
                    yield NormalizedTrade(
                        exchange=self.exchange_name,
                        symbol=self.normalize_symbol(symbol),
                        timestamp_ms=int(t.get("time", time.time() * 1000)),
                        price=float(t.get("px", 0)),
                        size=float(t.get("sz", 0)),
                        side=side,
                        trade_id=str(t.get("tid", "")),
                        raw=t,
                    )

    async def stream_orderbook(
        self, symbol: str, depth: int = 20
    ) -> AsyncGenerator[NormalizedOrderBook, None]:
        """Stream L2 book updates Hyperliquid. Necessite `pip install websockets`."""
        import websockets  # type: ignore

        coin = self._hl_symbol(symbol)
        sub = json.dumps(
            {"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}}
        )

        async with websockets.connect(_WS) as ws:
            await ws.send(sub)
            async for msg in ws:
                payload = json.loads(msg)
                if payload.get("channel") != "l2Book":
                    continue
                book = payload.get("data", {})
                levels = book.get("levels", [[], []])
                bids_raw = levels[0][:depth] if levels else []
                asks_raw = levels[1][:depth] if len(levels) > 1 else []
                bids = sorted(
                    [(float(b["px"]), float(b["sz"])) for b in bids_raw], reverse=True
                )
                asks = sorted([(float(a["px"]), float(a["sz"])) for a in asks_raw])
                yield NormalizedOrderBook(
                    exchange=self.exchange_name,
                    symbol=self.normalize_symbol(symbol),
                    timestamp_ms=int(book.get("time", time.time() * 1000)),
                    bids=bids,
                    asks=asks,
                    is_snapshot=book.get("isSnapshot", False),
                )
