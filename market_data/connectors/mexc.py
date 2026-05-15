"""
market_data/connectors/mexc.py — Connecteur MEXC Futures (USDT-M).

REST  : https://contract.mexc.com/api/v1/contract/
WS    : wss://contract.mexc.com/ws

Particularites MEXC :
  - API Futures differente du Spot (contract.mexc.com vs api.mexc.com)
  - Timestamp en secondes (pas ms) pour certains endpoints -> normaliser * 1000
  - Symboles format "BTC_USDT" -> normaliser vers "BTCUSDT"
  - Volume en contrats (pas en base asset) -> convertir selon contract_value
"""

from __future__ import annotations

import json
import time
from typing import AsyncGenerator, Optional

from market_data.connectors.base import BaseConnector
from market_data.models import NormalizedCandle, NormalizedOrderBook, NormalizedTrade

_BASE = "https://contract.mexc.com/api/v1/contract"
_WS = "wss://contract.mexc.com/ws"

_TF_MAP = {
    "1m": "Min1",
    "5m": "Min5",
    "15m": "Min15",
    "30m": "Min30",
    "1h": "Min60",
    "4h": "Hour4",
    "1d": "Day1",
}

# Taille d'un contrat par symbole (USDT) — utile pour convertir volume contrats -> base asset
_CONTRACT_VALUE: dict[str, float] = {
    "BTC_USDT": 1.0,
    "ETH_USDT": 1.0,
    "SOL_USDT": 1.0,
    "BNB_USDT": 1.0,
    "XRP_USDT": 10.0,  # 10 XRP par contrat
    "DOGE_USDT": 1000.0,  # 1000 DOGE par contrat
}


class MEXCFuturesConnector(BaseConnector):

    exchange_name = "mexc"
    base_url = _BASE
    ws_url = _WS

    def _mexc_symbol(self, symbol: str) -> str:
        """Convertit "BTCUSDT" -> "BTC_USDT" pour MEXC Futures."""
        s = symbol.upper()
        # Insere le _ avant USDT/USDC si absent
        for quote in ("USDT", "USDC", "BTC", "ETH"):
            if s.endswith(quote) and "_" not in s:
                return s[: -len(quote)] + "_" + quote
        return s

    def _normalize_symbol(self, mexc_sym: str) -> str:
        """Inverse : "BTC_USDT" -> "BTCUSDT"."""
        return mexc_sym.replace("_", "").upper()

    def _contract_to_base(
        self, symbol_mexc: str, contracts: float, price: float
    ) -> float:
        """Convertit un volume en contrats -> base asset."""
        cval = _CONTRACT_VALUE.get(symbol_mexc, 1.0)
        if cval == 1.0:
            return contracts
        # Pour les contrats DOGE (1000 DOGE/contrat) : volume = contracts * 1000 DOGE
        return contracts * cval

    # ------------------------------------------------------------------
    # REST
    # ------------------------------------------------------------------

    def fetch_trades(self, symbol: str, limit: int = 100) -> list[NormalizedTrade]:
        sym = self._mexc_symbol(symbol)
        data = self._get_json(f"{_BASE}/deals/{sym}", {"limit": min(limit, 100)})
        trades = []
        result_data = data.get("data", {})
        deals = (
            result_data.get("resultList", result_data)
            if isinstance(result_data, dict)
            else result_data
        )
        for t in deals[:limit]:
            # MEXC: {"p": price, "v": volume, "T": side (1=buy,2=sell), "O": timestamp_s}
            side_raw = int(t.get("T", t.get("takerSide", 1)))
            side = "buy" if side_raw == 1 else "sell"
            ts = int(t.get("t", t.get("O", time.time())))
            ts_ms = ts if ts > 1e12 else ts * 1000  # normaliser vers ms
            price = float(t.get("p", 0))
            size_raw = float(t.get("v", 0))
            trades.append(
                NormalizedTrade(
                    exchange=self.exchange_name,
                    symbol=self._normalize_symbol(sym),
                    timestamp_ms=ts_ms,
                    price=price,
                    size=self._contract_to_base(sym, size_raw, price),
                    side=side,
                    trade_id=str(t.get("id", "")),
                    raw=t,
                )
            )
        return trades

    def fetch_orderbook(self, symbol: str, depth: int = 20) -> NormalizedOrderBook:
        sym = self._mexc_symbol(symbol)
        data = self._get_json(f"{_BASE}/depth/{sym}", {"limit": min(depth, 150)})
        book_data = data.get("data", data)
        bids = [
            (float(p), float(s))
            for p, s in zip(book_data.get("bids", []), book_data.get("bidVols", []))
        ]
        asks = [
            (float(p), float(s))
            for p, s in zip(book_data.get("asks", []), book_data.get("askVols", []))
        ]
        # Assurer le tri correct
        bids = sorted(bids, key=lambda x: x[0], reverse=True)
        asks = sorted(asks, key=lambda x: x[0])
        ts = int(book_data.get("timestamp", time.time() * 1000))
        return NormalizedOrderBook(
            exchange=self.exchange_name,
            symbol=self._normalize_symbol(sym),
            timestamp_ms=ts if ts > 1e12 else ts * 1000,
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
        sym = self._mexc_symbol(symbol)
        tf = _TF_MAP.get(timeframe, "Min1")
        params: dict = {"interval": tf}
        if start_ms:
            params["start"] = start_ms // 1000  # MEXC attend des secondes
        if end_ms:
            params["end"] = end_ms // 1000

        data = self._get_json(f"{_BASE}/kline/{sym}", params)
        klines = data.get("data", {})
        opens = klines.get("open", [])
        highs = klines.get("high", [])
        lows = klines.get("low", [])
        closes = klines.get("close", [])
        vols = klines.get("vol", [])
        times = klines.get("time", [])
        buy_vols = klines.get("buyVol", [0] * len(opens))

        candles = []
        for i in range(min(len(opens), limit)):
            ts = int(times[i]) if i < len(times) else 0
            ts_ms = ts if ts > 1e12 else ts * 1000
            volume = float(vols[i]) if i < len(vols) else 0.0
            buy_vol = float(buy_vols[i]) if i < len(buy_vols) else 0.0
            candles.append(
                NormalizedCandle(
                    exchange=self.exchange_name,
                    symbol=self._normalize_symbol(sym),
                    timestamp_ms=ts_ms,
                    timeframe=timeframe,
                    open=float(opens[i]),
                    high=float(highs[i]) if i < len(highs) else 0.0,
                    low=float(lows[i]) if i < len(lows) else 0.0,
                    close=float(closes[i]) if i < len(closes) else 0.0,
                    volume=volume,
                    buy_volume=buy_vol,
                    sell_volume=volume - buy_vol,
                    is_closed=True,
                )
            )
        return candles

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    async def stream_trades(self, symbol: str) -> AsyncGenerator[NormalizedTrade, None]:
        """Stream trades MEXC Futures. Necessite `pip install websockets`."""
        import websockets  # type: ignore

        sym = self._mexc_symbol(symbol)
        sub = json.dumps({"method": "sub.deal", "param": {"symbol": sym}})

        async with websockets.connect(_WS) as ws:
            await ws.send(sub)
            async for msg in ws:
                payload = json.loads(msg)
                if payload.get("channel") != "push.deal":
                    continue
                for t in payload.get("data", {}).get("deals", []):
                    side_raw = int(t.get("T", 1))
                    ts = int(t.get("t", time.time() * 1000))
                    price = float(t.get("p", 0))
                    size_raw = float(t.get("v", 0))
                    yield NormalizedTrade(
                        exchange=self.exchange_name,
                        symbol=self._normalize_symbol(sym),
                        timestamp_ms=ts if ts > 1e12 else ts * 1000,
                        price=price,
                        size=self._contract_to_base(sym, size_raw, price),
                        side="buy" if side_raw == 1 else "sell",
                        raw=t,
                    )

    async def stream_orderbook(
        self, symbol: str, depth: int = 20
    ) -> AsyncGenerator[NormalizedOrderBook, None]:
        """Stream depth MEXC Futures. Necessite `pip install websockets`."""
        import websockets  # type: ignore

        sym = self._mexc_symbol(symbol)
        sub = json.dumps({"method": "sub.depth", "param": {"symbol": sym}})

        async with websockets.connect(_WS) as ws:
            await ws.send(sub)
            async for msg in ws:
                payload = json.loads(msg)
                if payload.get("channel") != "push.depth":
                    continue
                d = payload.get("data", {})
                bids = sorted(
                    [
                        (float(p), float(s))
                        for p, s in zip(d.get("bids", []), d.get("bidVols", []))
                    ],
                    reverse=True,
                )[:depth]
                asks = sorted(
                    [
                        (float(p), float(s))
                        for p, s in zip(d.get("asks", []), d.get("askVols", []))
                    ]
                )[:depth]
                ts = int(d.get("timestamp", time.time() * 1000))
                yield NormalizedOrderBook(
                    exchange=self.exchange_name,
                    symbol=self._normalize_symbol(sym),
                    timestamp_ms=ts if ts > 1e12 else ts * 1000,
                    bids=bids,
                    asks=asks,
                    is_snapshot=False,
                )
