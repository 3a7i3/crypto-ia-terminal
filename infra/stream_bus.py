"""
StreamBus — couche de streaming découplée pour Annalise
Ingère les WebSockets CCXT en tâche asyncio permanente.
Expose un LatestSnapshot lu par le cycle ML sans blocage.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import ccxt.pro as ccxtpro

from observability.json_logger import get_logger

_log = get_logger("StreamBus")
# ------------------------------------------------------------------
# Structures de données
# ------------------------------------------------------------------


@dataclass
class Tick:
    symbol: str
    timestamp: float
    kind: str  # 'orderbook' | 'trade' | 'ticker' | 'funding'
    data: dict


@dataclass
class LatestSnapshot:
    """
    Dict-like store atomique : toujours la donnée la plus récente.
    Le cycle ML lit ici — jamais dans les queues brutes.
    """

    orderbooks: dict = field(default_factory=dict)  # symbol → orderbook
    trades: dict = field(default_factory=dict)  # symbol → [derniers trades]
    tickers: dict = field(default_factory=dict)  # symbol → ticker
    funding: dict = field(default_factory=dict)  # symbol → funding rate
    whale_alerts: list = field(default_factory=list)  # alertes récentes
    updated_at: float = field(default_factory=time.time)
    tick_count: int = 0
    drop_count: int = 0

    def get_mid_price(self, symbol: str) -> Optional[float]:
        ob = self.orderbooks.get(symbol)
        if ob and ob.get("bids") and ob.get("asks"):
            return (ob["bids"][0][0] + ob["asks"][0][0]) / 2
        return self.tickers.get(symbol, {}).get("last")

    def get_spread(self, symbol: str) -> Optional[float]:
        ob = self.orderbooks.get(symbol)
        if ob and ob.get("bids") and ob.get("asks"):
            bid, ask = ob["bids"][0][0], ob["asks"][0][0]
            return (ask - bid) / bid if bid > 0 else None
        return None

    def get_orderbook_imbalance(self, symbol: str, depth: int = 10) -> Optional[float]:
        ob = self.orderbooks.get(symbol)
        if not ob:
            return None
        bid_vol = sum(qty for _, qty in ob.get("bids", [])[:depth])
        ask_vol = sum(qty for _, qty in ob.get("asks", [])[:depth])
        total = bid_vol + ask_vol
        return (bid_vol - ask_vol) / total if total > 0 else 0.0


# ------------------------------------------------------------------
# StreamBus
# ------------------------------------------------------------------


class StreamBus:
    """
    Usage dans main_v91.py :

        bus = StreamBus(
            symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            exchange_id="binance",
            whale_threshold_usd=500_000,
        )
        asyncio.create_task(bus.start())   # lance une fois, tourne en permanence

        # Dans le cycle ML — lecture instantanée, non-bloquante
        snap = bus.snapshot
        btc_price = snap.get_mid_price("BTC/USDT")
        imbalance = snap.get_orderbook_imbalance("BTC/USDT")
    """

    def __init__(
        self,
        symbols: list[str],
        exchange_id: str = "mexc",
        exchange_config: dict = None,
        whale_threshold_usd: float = 500_000,
        queue_maxsize: int = 5000,
        trade_history_size: int = 200,
        on_whale: Optional[Callable] = None,
    ):
        import os

        self.symbols = symbols
        self.exchange_id = exchange_id

        if exchange_config is None:
            exchange_config = {"enableRateLimit": True}
            prefix = self.exchange_id.upper()
            api_key = os.getenv(f"{prefix}_API_KEY")
            api_secret = os.getenv(f"{prefix}_API_SECRET")
            if api_key and api_secret:
                exchange_config["apiKey"] = api_key
                exchange_config["secret"] = api_secret
                _log.info(
                    "StreamBus: clés API %s chargées depuis l'environnement",
                    self.exchange_id,
                )
        self.exchange_config = exchange_config
        self.whale_threshold_usd = whale_threshold_usd
        self.queue_maxsize = queue_maxsize
        self.trade_history_size = trade_history_size
        self.on_whale = on_whale

        self.snapshot = LatestSnapshot()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self._running = False
        self._exchange: Optional[ccxtpro.Exchange] = None
        self._trade_buffer: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=trade_history_size)
        )

    async def start(self) -> None:
        self._running = True
        exchange_class = getattr(ccxtpro, self.exchange_id)
        self._exchange = exchange_class(self.exchange_config)
        _log.info(
            f"StreamBus démarré — {len(self.symbols)} symboles sur {self.exchange_id}"
        )
        try:
            await asyncio.gather(
                self._ingest_orderbooks(),
                self._ingest_trades(),
                self._ingest_tickers(),
                self._process_queue(),
                return_exceptions=True,
            )
        finally:
            await self._exchange.close()
            _log.info("StreamBus arrêté")

    async def stop(self) -> None:
        self._running = False

    async def _ingest_orderbooks(self) -> None:
        while self._running:
            try:
                tasks = [self._watch_orderbook(symbol) for symbol in self.symbols]
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                _log.error(f"Orderbook ingest error: {e} — reconnexion dans 5s")
                await asyncio.sleep(5)

    async def _watch_orderbook(self, symbol: str) -> None:
        while self._running:
            try:
                ob = await self._exchange.watch_order_book(symbol, limit=20)
                await self._enqueue(
                    Tick(
                        symbol=symbol,
                        timestamp=time.time(),
                        kind="orderbook",
                        data={"bids": ob["bids"][:20], "asks": ob["asks"][:20]},
                    )
                )
            except Exception as e:
                _log.warning(f"OrderBook {symbol}: {e}")
                await asyncio.sleep(2)

    async def _ingest_trades(self) -> None:
        while self._running:
            try:
                tasks = [self._watch_trades(symbol) for symbol in self.symbols]
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                _log.error(f"Trades ingest error: {e} — reconnexion dans 5s")
                await asyncio.sleep(5)

    async def _watch_trades(self, symbol: str) -> None:
        while self._running:
            try:
                trades = await self._exchange.watch_trades(symbol)
                for trade in trades:
                    await self._enqueue(
                        Tick(
                            symbol=symbol,
                            timestamp=trade.get("timestamp", time.time() * 1000) / 1000,
                            kind="trade",
                            data={
                                "price": trade["price"],
                                "amount": trade["amount"],
                                "side": trade["side"],
                                "cost": trade.get(
                                    "cost", trade["price"] * trade["amount"]
                                ),
                            },
                        )
                    )
            except Exception as e:
                _log.warning(f"Trades {symbol}: {e}")
                await asyncio.sleep(2)

    async def _ingest_tickers(self) -> None:
        while self._running:
            try:
                tickers = await self._exchange.watch_tickers(self.symbols)
                for symbol, ticker in tickers.items():
                    await self._enqueue(
                        Tick(
                            symbol=symbol,
                            timestamp=time.time(),
                            kind="ticker",
                            data={
                                "last": ticker.get("last"),
                                "volume": ticker.get("baseVolume"),
                                "change": ticker.get("percentage"),
                                "high": ticker.get("high"),
                                "low": ticker.get("low"),
                            },
                        )
                    )
            except Exception as e:
                _log.error(f"Tickers error: {e} — reconnexion dans 3s")
                await asyncio.sleep(3)

    async def _enqueue(self, tick: Tick) -> None:
        try:
            self._queue.put_nowait(tick)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._queue.put_nowait(tick)
            self.snapshot.drop_count += 1

    async def _process_queue(self) -> None:
        while self._running:
            try:
                tick = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                self._apply(tick)
                self.snapshot.tick_count += 1
                self.snapshot.updated_at = time.time()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                _log.error(f"Queue processor error: {e}")

    def _apply(self, tick: Tick) -> None:
        s = tick.symbol
        if tick.kind == "orderbook":
            self.snapshot.orderbooks[s] = tick.data
        elif tick.kind == "trade":
            self._trade_buffer[s].append(tick.data)
            self.snapshot.trades[s] = list(self._trade_buffer[s])
            self._check_whale(s, tick.data)
        elif tick.kind == "ticker":
            self.snapshot.tickers[s] = tick.data
        elif tick.kind == "funding":
            self.snapshot.funding[s] = tick.data

    def _check_whale(self, symbol: str, trade: dict) -> None:
        cost = trade.get("cost", 0)
        if cost >= self.whale_threshold_usd:
            alert = {
                "symbol": symbol,
                "side": trade["side"],
                "amount_usd": cost,
                "price": trade["price"],
                "timestamp": time.time(),
            }
            self.snapshot.whale_alerts.append(alert)
            if len(self.snapshot.whale_alerts) > 50:
                self.snapshot.whale_alerts = self.snapshot.whale_alerts[-50:]
            _log.warning(
                f"WHALE {symbol} {trade['side'].upper()} "
                f"${cost:,.0f} @ {trade['price']}"
            )
            if self.on_whale:
                asyncio.create_task(self._fire_whale_callback(alert))

    async def _fire_whale_callback(self, alert: dict) -> None:
        try:
            if asyncio.iscoroutinefunction(self.on_whale):
                await self.on_whale(alert)
            else:
                self.on_whale(alert)
        except Exception as e:
            _log.error(f"Whale callback error: {e}")

    def stats(self) -> dict:
        return {
            "queue_size": self._queue.qsize(),
            "tick_count": self.snapshot.tick_count,
            "drop_count": self.snapshot.drop_count,
            "drop_rate": (self.snapshot.drop_count / max(self.snapshot.tick_count, 1)),
            "symbols_with_ob": len(self.snapshot.orderbooks),
            "last_update_age": time.time() - self.snapshot.updated_at,
        }
