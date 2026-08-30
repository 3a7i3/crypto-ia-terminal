"""
market_data/stream.py — Stream unifie multi-exchange.

MultiExchangeStream :
  - Agregation de tous les connecteurs dans une seule file d'evenements
  - Normalisation des timestamps (UTC ms)
  - Routing par type d'evenement (trades, orderbook, candles, liquidations)
  - Interface synchrone (fetch snapshots) et asynchrone (streaming live)

Usage snapshot (sync) :
    stream = MultiExchangeStream()
    stream.add_connector(MEXCFuturesConnector())
    stream.add_connector(HyperliquidConnector())
    events = stream.fetch_all("BTCUSDT", event_types=["trade", "orderbook"])

Usage live (async) :
    async for event in stream.stream_live("BTCUSDT"):
        process(event)
"""

from __future__ import annotations

import asyncio
import os
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


class StreamPipelineError(RuntimeError):
    """Erreur de pipeline live quand tous les feeders requis sont morts."""


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
        self._last_stream_health: dict = {}

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
        health_check_interval_s: float = 5.0,
        stall_threshold_s: Optional[float] = None,
    ) -> AsyncGenerator[MarketEvent, None]:
        """
        Stream unifie de tous les connecteurs.
        Merge plusieurs streams asyncio en un seul via asyncio.Queue.
        """
        types = set(event_types or ["trade", "orderbook"])
        health_check_interval_s = max(0.2, float(health_check_interval_s))
        if stall_threshold_s is None:
            env_s = os.getenv("LMI_STREAM_STALL_S", "").strip()
            stall_threshold_s = float(env_s) if env_s else max(30.0, health_check_interval_s * 6)
        stall_threshold_s = max(health_check_interval_s, float(stall_threshold_s))

        queue: asyncio.Queue[MarketEvent] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        last_event_monotonic = loop.time()
        last_event_timestamp_ms = 0
        feeders: dict[str, dict] = {}
        tasks: dict[str, asyncio.Task] = {}

        def _key(conn: BaseConnector, stream_type: str) -> str:
            return f"{conn.exchange_name}:{stream_type}"

        def _reconnect_count(conn: BaseConnector, stream_type: str) -> int | None:
            for name in (f"{stream_type}_reconnect_count", "reconnect_count"):
                v = getattr(conn, name, None)
                if isinstance(v, int):
                    return v
            return None

        def _publish_health(state: str) -> None:
            now = loop.time()
            snapshot = {
                "pipeline_state": state,
                "symbol": symbol,
                "queue_idle_s": max(0.0, now - last_event_monotonic),
                "last_event_timestamp_ms": last_event_timestamp_ms,
                "health_check_interval_s": health_check_interval_s,
                "stall_threshold_s": stall_threshold_s,
                "feeders": {},
            }
            for k, feeder in feeders.items():
                task = tasks.get(k)
                task_done = bool(task.done()) if task else True
                task_cancelled = bool(task.cancelled()) if task else False
                exc_name = ""
                if task and task.done() and not task_cancelled:
                    try:
                        exc = task.exception()
                    except asyncio.CancelledError:
                        exc = None
                    if exc:
                        exc_name = type(exc).__name__
                        if not feeder.get("last_error"):
                            feeder["last_error"] = f"{type(exc).__name__}: {exc}"
                            feeder["error_count"] = int(feeder.get("error_count", 0)) + 1
                snapshot["feeders"][k] = {
                    "connector": feeder.get("connector"),
                    "stream_type": feeder.get("stream_type"),
                    "feeder_alive": bool(feeder.get("feeder_alive")) and not task_done,
                    "task_done": task_done,
                    "task_cancelled": task_cancelled,
                    "last_event_ms": feeder.get("last_event_ms"),
                    "last_event_monotonic": feeder.get("last_event_monotonic"),
                    "last_error": feeder.get("last_error"),
                    "error_count": int(feeder.get("error_count", 0)),
                    "reconnect_count": feeder.get("reconnect_count"),
                    "queue_idle_s": snapshot["queue_idle_s"],
                }
            self._last_stream_health = snapshot

        async def _feed_trades(conn: BaseConnector, feeder: dict) -> None:
            feeder["feeder_alive"] = True
            try:
                async for trade in conn.stream_trades(symbol):
                    feeder["last_event_monotonic"] = loop.time()
                    feeder["last_event_ms"] = trade.timestamp_ms
                    feeder["reconnect_count"] = _reconnect_count(conn, "trade")
                    await queue.put(MarketEvent.from_trade(trade))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                feeder["last_error"] = f"{type(exc).__name__}: {exc}"
                feeder["error_count"] = int(feeder.get("error_count", 0)) + 1
                _log.warning("[%s] stream_trades error: %s", conn.exchange_name, exc)
            finally:
                feeder["feeder_alive"] = False

        async def _feed_orderbook(conn: BaseConnector, feeder: dict) -> None:
            feeder["feeder_alive"] = True
            try:
                async for book in conn.stream_orderbook(symbol):
                    feeder["last_event_monotonic"] = loop.time()
                    feeder["last_event_ms"] = book.timestamp_ms
                    feeder["reconnect_count"] = _reconnect_count(conn, "orderbook")
                    await queue.put(MarketEvent.from_orderbook(book))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                feeder["last_error"] = f"{type(exc).__name__}: {exc}"
                feeder["error_count"] = int(feeder.get("error_count", 0)) + 1
                _log.warning("[%s] stream_orderbook error: %s", conn.exchange_name, exc)
            finally:
                feeder["feeder_alive"] = False

        for conn in self._connectors:
            if "trade" in types:
                k = _key(conn, "trade")
                feeders[k] = {
                    "connector": conn.exchange_name,
                    "stream_type": "trade",
                    "feeder_alive": False,
                    "last_event_ms": None,
                    "last_event_monotonic": None,
                    "last_error": "",
                    "error_count": 0,
                    "reconnect_count": _reconnect_count(conn, "trade"),
                }
                tasks[k] = asyncio.create_task(_feed_trades(conn, feeders[k]))
            if "orderbook" in types:
                k = _key(conn, "orderbook")
                feeders[k] = {
                    "connector": conn.exchange_name,
                    "stream_type": "orderbook",
                    "feeder_alive": False,
                    "last_event_ms": None,
                    "last_event_monotonic": None,
                    "last_error": "",
                    "error_count": 0,
                    "reconnect_count": _reconnect_count(conn, "orderbook"),
                }
                tasks[k] = asyncio.create_task(_feed_orderbook(conn, feeders[k]))

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=health_check_interval_s)
                except asyncio.TimeoutError:
                    _publish_health("degraded")
                    all_dead = bool(tasks) and all(
                        t.done() or t.cancelled() for t in tasks.values()
                    )
                    if all_dead:
                        raise StreamPipelineError(
                            f"all feeders dead for symbol={symbol}"
                        )
                    if self._last_stream_health.get("queue_idle_s", 0.0) >= stall_threshold_s:
                        _log.warning(
                            "stream_live queue stall: symbol=%s idle_s=%.1f",
                            symbol,
                            self._last_stream_health["queue_idle_s"],
                        )
                    continue
                last_event_monotonic = loop.time()
                last_event_timestamp_ms = event.timestamp_ms
                _publish_health("healthy")
                # Dispatcher les handlers enregistres
                for handler in self._handlers.get(event.event_type, []):
                    try:
                        handler(event)
                    except Exception as exc:
                        _log.warning("Handler error for %s: %s", event.event_type, exc)
                yield event
        finally:
            _publish_health("stopped")
            for t in tasks.values():
                t.cancel()

    @property
    def last_stream_health(self) -> dict:
        return dict(self._last_stream_health)
