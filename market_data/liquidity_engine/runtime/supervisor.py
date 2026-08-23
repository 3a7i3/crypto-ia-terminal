from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from market_data.liquidity_engine.adapters import BinanceWebSocketClient, MexcWebSocketClient
from market_data.liquidity_engine.aggregation.liquidity import LiquidityAggregator
from market_data.liquidity_engine.config import LiquidityEngineConfig
from market_data.liquidity_engine.filters.trade_filter import TradeFilter
from market_data.liquidity_engine.metrics.runtime_metrics import RuntimeMetrics
from market_data.liquidity_engine.models import MarketEvent, TradeSizeLevel
from market_data.liquidity_engine.publishing.event_bus import EventBus
from market_data.liquidity_engine.publishing.publisher import (
    DataPublisher,
    InMemoryPublisher,
)
from observability.json_logger import get_logger


class LiquidityEngineSupervisor:
    def __init__(
        self,
        config: LiquidityEngineConfig,
        publisher: DataPublisher | None = None,
    ) -> None:
        self.config = config
        self.metrics = RuntimeMetrics()
        self.bus = EventBus(max_size=config.queue_max_size, metrics=self.metrics)
        self.trade_filter = TradeFilter(config)
        self.aggregator = LiquidityAggregator(config)
        self.publisher = publisher or InMemoryPublisher()
        self._log = get_logger("liquidity_engine.supervisor")
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        clients = []
        if self.config.binance_enabled:
            clients.append(
                BinanceWebSocketClient(
                    symbols=self.config.symbols,
                    ws_timeout_s=self.config.ws_timeout_s,
                    base_backoff_s=self.config.base_backoff_s,
                    max_backoff_s=self.config.max_backoff_s,
                )
            )
        if self.config.mexc_enabled:
            clients.append(
                MexcWebSocketClient(
                    symbols=self.config.symbols,
                    ws_timeout_s=self.config.ws_timeout_s,
                    base_backoff_s=self.config.base_backoff_s,
                    max_backoff_s=self.config.max_backoff_s,
                )
            )

        self._tasks.append(asyncio.create_task(self._consumer_loop(), name="liquidity_consumer"))
        self._tasks.append(asyncio.create_task(self._snapshot_loop(), name="liquidity_snapshot"))
        for client in clients:
            self._tasks.append(
                asyncio.create_task(
                    client.run(self._on_market_event, self.metrics),
                    name=f"ws_{client.exchange}",
                )
            )

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _on_market_event(self, event: MarketEvent) -> None:
        critical = event.priority > 0
        await self.bus.publish(event, critical=critical)

    async def _consumer_loop(self) -> None:
        while self._running:
            event = await self.bus.get()
            try:
                t0 = datetime.now(timezone.utc)
                self.metrics.messages_processed += 1

                if event.event_type == "trade":
                    classified = self.trade_filter.classify_trade(event)
                    self.aggregator.ingest_trade(classified)
                    await self.publisher.publish_event(
                        {
                            "type": "MARKET_EVENT",
                            "exchange": event.exchange,
                            "symbol": event.symbol,
                            "event_type": event.event_type,
                            "timestamp_exchange": event.timestamp_exchange.isoformat(),
                            "timestamp_received": event.timestamp_received.isoformat(),
                            "timestamp_processed": t0.isoformat(),
                            "notional_usd": event.notional_usd,
                            "price": event.price,
                            "quantity": event.quantity,
                            "side": event.side,
                            "trade_id": event.trade_id,
                            "latency_ms": event.latency_ms,
                            "size_level": classified.level.value,
                            "threshold_large": classified.threshold_large,
                            "threshold_whale": classified.threshold_whale,
                        }
                    )
                    if classified.level in (TradeSizeLevel.LARGE, TradeSizeLevel.WHALE):
                        self.metrics.big_trades_detected += 1
                        await self.publisher.publish_event(
                            {
                                "type": "BIG_TRADE_EVENT",
                                "exchange": event.exchange,
                                "symbol": event.symbol,
                                "size_level": classified.level.value,
                                "notional_usd": event.notional_usd,
                                "price": event.price,
                                "quantity": event.quantity,
                                "side": event.side,
                                "timestamp_exchange": event.timestamp_exchange.isoformat(),
                                "timestamp_received": event.timestamp_received.isoformat(),
                                "timestamp_processed": t0.isoformat(),
                                "latency_ms": event.latency_ms,
                            }
                        )

                elif event.event_type == "orderbook":
                    raw = event.raw_payload
                    bids = raw.get("bids", []) if isinstance(raw, dict) else []
                    asks = raw.get("asks", []) if isinstance(raw, dict) else []
                    self.aggregator.ingest_orderbook(event, bids=bids, asks=asks)

                proc_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
                self.metrics.record_processing_latency(proc_ms)
            except Exception as exc:
                self.metrics.messages_rejected += 1
                self._log.warning("consumer_loop_error", error=str(exc))

    async def _snapshot_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(1.0)
                now = datetime.now(timezone.utc)
                snap = self.aggregator.snapshot(now=now)
                payload = {
                    "type": "LIQUIDITY_SNAPSHOT",
                    "timestamp": now.isoformat(),
                    "metrics": self.metrics.as_dict(),
                    "queue_depth": self.bus.qsize(),
                    "windows": snap["windows"],
                    "pockets": snap["pockets"],
                }
                await self.publisher.publish_snapshot(payload)
            except Exception as exc:
                self._log.warning("snapshot_loop_error", error=str(exc))

    def metrics_snapshot(self) -> dict:
        return self.metrics.as_dict()
