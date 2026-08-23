from __future__ import annotations

import pytest

from market_data.liquidity_engine.metrics.runtime_metrics import RuntimeMetrics
from market_data.liquidity_engine.publishing.event_bus import EventBus


class _Ev:
    def __init__(self, priority: int):
        self.priority = priority


@pytest.mark.asyncio
async def test_queue_full_drops_noncritical():
    m = RuntimeMetrics()
    bus = EventBus(max_size=1, metrics=m)
    await bus.publish(_Ev(priority=0), critical=False)
    ok = await bus.publish(_Ev(priority=0), critical=False)
    assert ok is False
    assert m.dropped_noncritical_events == 1


@pytest.mark.asyncio
async def test_queue_full_keeps_critical_by_eviction():
    m = RuntimeMetrics()
    bus = EventBus(max_size=1, metrics=m)
    await bus.publish(_Ev(priority=0), critical=False)
    ok = await bus.publish(_Ev(priority=1), critical=True)
    assert ok is True
    ev = await bus.get()
    assert ev.priority == 1
