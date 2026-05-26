"""
market_data/stream.py — Stream unifie multi-exchange.

MultiExchangeStream :
  - Agregation de tous les connecteurs dans une seule file d'evenements
  - Normalisation des timestamps (UTC ms)
  - Routing par type d'evenement (trades, orderbook, candles, liquidations)
  - Interface synchrone (fetch snapshots) et asynchrone (streaming live)

Usage snapshot (sync) :
    stream = MultiExchangeStream()
    stream.add_connector(BinanceFuturesConnector())
    stream.add_connector(HyperliquidConnector())
    events = stream.fetch_all("BTCUSDT", event_types=["trade", "orderbook"])

Usage live (async) :
    async for event in stream.stream_live("BTCUSDT"):
        process(event)
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Callable, Optional

from market_data.connectors.base import BaseConnector
from market_data.models import (
    MarketEvent,
    NormalizedCandle,
    NormalizedOrderBook,
    NormalizedTrade,
)
from observability.json_logger import get_logger

_log = get_logger("market_data.stream")


class MultiExchangeStream:
    """
    Agregateur de flux multi-exchange.

    Tous les connecteurs enregistres sont interroges en parallele.
    Les evenements sont emis tries par timestamp (pour le replay).
    """

    def __init__(self) -> None:
        self._connectors: list[BaseConnector] = []
        self._handlers: dict[str, list[Callable]] = {
            "trade": [],
            "orderbook": [],
            "candle": [],
            "liquidity": [],
        }

    def add_connector(self, connector: BaseConnector) -> "MultiExchangeStream":
        self._connectors.append(connector)
        _log.info("MultiExchangeStream: added connector %s", connector.exchange_name)
        return self

    def on(self, event_type: str) -> Callable:
        """Decorateur pour enregistrer un handler d'evenement."""

        def decorator(fn: Callable) -> Callable:
            self._handlers.setdefault(event_type, []).append(fn)
            return fn

        return decorator

    # ------------------------------------------------------------------
    # Snapshot synchrone (REST)
    # ------------------------------------------------------------------

    def fetch_trades(self, symbol: str, limit: int = 100) -> list[MarketEvent]:
        """Fetch trades depuis tous les connecteurs et retourne trie par timestamp."""
        events = []
        for conn in self._connectors:
            try:
                trades = conn.fetch_trades(symbol, limit)
                events.extend(MarketEvent.from_trade(t) for t in trades)
            except Exception as exc:
                _log.warning("[%s] fetch_trades failed: %s", conn.exchange_name, exc)
        return sorted(events, key=lambda e: e.timestamp_ms)

    def fetch_orderbooks(self, symbol: str, depth: int = 20) -> list[MarketEvent]:
        """Fetch orderbooks depuis tous les connecteurs."""
        events = []
        for conn in self._connectors:
            try:
                book = conn.fetch_orderbook(symbol, depth)
                events.append(MarketEvent.from_orderbook(book))
            except Exception as exc:
                _log.warning("[%s] fetch_orderbook failed: %s", conn.exchange_name, exc)
        return events

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 100,
    ) -> list[MarketEvent]:
        """Fetch candles depuis tous les connecteurs, merge et trie."""
        events = []
        for conn in self._connectors:
            try:
                candles = conn.fetch_candles(symbol, timeframe, limit)
                events.extend(MarketEvent.from_candle(c) for c in candles)
            except Exception as exc:
                _log.warning("[%s] fetch_candles failed: %s", conn.exchange_name, exc)
        return sorted(events, key=lambda e: e.timestamp_ms)

    def fetch_all(
        self,
        symbol: str,
        event_types: Optional[list[str]] = None,
        limit: int = 100,
    ) -> list[MarketEvent]:
        """Fetch tous les types d'evenements et retourne tri par timestamp."""
        types = set(event_types or ["trade", "orderbook", "candle"])
        events = []
        if "trade" in types:
            events.extend(self.fetch_trades(symbol, limit))
        if "orderbook" in types:
            events.extend(self.fetch_orderbooks(symbol))
        if "candle" in types:
            events.extend(self.fetch_candles(symbol, limit=limit))
        return sorted(events, key=lambda e: e.timestamp_ms)

    # ------------------------------------------------------------------
    # Streaming asynchrone (WebSocket)
    # ------------------------------------------------------------------

    async def stream_live(
        self,
        symbol: str,
        event_types: Optional[list[str]] = None,
    ) -> AsyncGenerator[MarketEvent, None]:
        """
        Stream unifie de tous les connecteurs.
        Merge plusieurs streams asyncio en un seul via asyncio.Queue.
        """
        types = set(event_types or ["trade", "orderbook"])
        queue: asyncio.Queue[MarketEvent] = asyncio.Queue()

        async def _feed_trades(conn: BaseConnector) -> None:
            try:
                async for trade in conn.stream_trades(symbol):
                    await queue.put(MarketEvent.from_trade(trade))
            except Exception as exc:
                _log.warning("[%s] stream_trades error: %s", conn.exchange_name, exc)

        async def _feed_orderbook(conn: BaseConnector) -> None:
            try:
                async for book in conn.stream_orderbook(symbol):
                    await queue.put(MarketEvent.from_orderbook(book))
            except Exception as exc:
                _log.warning("[%s] stream_orderbook error: %s", conn.exchange_name, exc)

        tasks = []
        for conn in self._connectors:
            if "trade" in types:
                tasks.append(asyncio.create_task(_feed_trades(conn)))
            if "orderbook" in types:
                tasks.append(asyncio.create_task(_feed_orderbook(conn)))

        try:
            while True:
                event = await queue.get()
                # Dispatcher les handlers enregistres
                for handler in self._handlers.get(event.event_type, []):
                    try:
                        handler(event)
                    except Exception as exc:
                        _log.warning("Handler error for %s: %s", event.event_type, exc)
                yield event
        finally:
            for t in tasks:
                t.cancel()
