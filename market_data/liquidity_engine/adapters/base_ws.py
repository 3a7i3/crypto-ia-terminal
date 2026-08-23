from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from market_data.liquidity_engine.metrics.runtime_metrics import RuntimeMetrics
from market_data.liquidity_engine.models import MarketEvent
from observability.json_logger import get_logger


class BaseWebSocketClient(ABC):
    exchange: str = "unknown"

    def __init__(
        self,
        symbols: list[str],
        ws_timeout_s: float,
        base_backoff_s: float,
        max_backoff_s: float,
        connect_factory: Any | None = None,
    ) -> None:
        self.symbols = [s.upper() for s in symbols]
        self.ws_timeout_s = ws_timeout_s
        self.base_backoff_s = base_backoff_s
        self.max_backoff_s = max_backoff_s
        self._connect_factory = connect_factory
        self._log = get_logger(f"liquidity_engine.ws.{self.exchange}")
        self._running = False

    async def run(self, on_event, metrics: RuntimeMetrics) -> None:
        self._running = True
        backoff = self.base_backoff_s
        while self._running:
            try:
                async with self._connect() as ws:
                    backoff = self.base_backoff_s
                    await self._subscribe(ws)
                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=self.ws_timeout_s)
                        except asyncio.TimeoutError:
                            if hasattr(ws, "ping"):
                                await ws.ping()
                            continue
                        metrics.messages_received += 1
                        received = datetime.now(timezone.utc)
                        events = self.parse_message(raw, received)
                        if not events:
                            metrics.messages_rejected += 1
                            continue
                        for event in events:
                            metrics.record_ws_latency(event.latency_ms)
                            await on_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                metrics.reconnect_count += 1
                self._log.warning(
                    "ws_reconnect",
                    exchange=self.exchange,
                    error=str(exc),
                    backoff_s=round(backoff, 2),
                )
                await asyncio.sleep(backoff)
                backoff = min(self.max_backoff_s, backoff * 2)

    def stop(self) -> None:
        self._running = False

    @abstractmethod
    async def _subscribe(self, ws: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def parse_message(self, raw_message: str, received_at: datetime) -> list[MarketEvent]:
        raise NotImplementedError

    def _connect(self):
        if self._connect_factory:
            return self._connect_factory(self.ws_url)
        import websockets

        return websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20)
