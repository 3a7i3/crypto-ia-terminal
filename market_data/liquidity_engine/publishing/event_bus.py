from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from market_data.liquidity_engine.metrics.runtime_metrics import RuntimeMetrics


class EventBus:
    def __init__(self, max_size: int, metrics: RuntimeMetrics) -> None:
        self._max_size = max_size
        self._items: deque[Any] = deque()
        self._condition = asyncio.Condition()
        self._metrics = metrics

    async def publish(self, event: Any, critical: bool = False) -> bool:
        async with self._condition:
            if len(self._items) >= self._max_size:
                if not (critical and self._drop_one_noncritical_if_possible()):
                    self._metrics.dropped_events += 1
                    if critical:
                        self._metrics.dropped_critical_events += 1
                    else:
                        self._metrics.dropped_noncritical_events += 1
                    self._metrics.queue_depth = len(self._items)
                    return False
            self._items.append(event)
            self._metrics.queue_depth = len(self._items)
            self._condition.notify(1)
            return True

    async def get(self) -> Any:
        async with self._condition:
            while not self._items:
                await self._condition.wait()
            item = self._items.popleft()
            self._metrics.queue_depth = len(self._items)
            return item

    def qsize(self) -> int:
        return len(self._items)

    def _drop_one_noncritical_if_possible(self) -> bool:
        for idx, candidate in enumerate(list(self._items)):
            if not bool(getattr(candidate, "priority", 0) > 0):
                try:
                    del self._items[idx]
                    self._metrics.dropped_events += 1
                    self._metrics.dropped_noncritical_events += 1
                    return True
                except Exception:
                    return False
        return False
