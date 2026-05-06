from __future__ import annotations

import asyncio
import json

import pytest

from event_bus.bus import EventBus
from event_bus.events import BaseEvent, CrashEvent, OrderFilledEvent, SecurityAlertEvent


@pytest.fixture(autouse=True)
def fresh_bus():
    EventBus.reset()
    yield EventBus.get()
    EventBus.reset()


def test_duplicate_subscribe_is_ignored(fresh_bus):
    received = []

    fresh_bus.subscribe(SecurityAlertEvent, received.append)
    fresh_bus.subscribe(SecurityAlertEvent, received.append)
    fresh_bus.emit(SecurityAlertEvent(rule="duplicate"))

    assert len(received) == 1
    assert fresh_bus.subscriber_count(SecurityAlertEvent) == 1


def test_clear_dead_letters_returns_count(fresh_bus):
    fresh_bus.emit(CrashEvent(context="unhandled"))
    fresh_bus.emit(OrderFilledEvent(symbol="BTC/USDT"))

    assert len(fresh_bus.dead_letters()) == 2
    assert fresh_bus.clear_dead_letters() == 2
    assert fresh_bus.dead_letters() == []


def test_replay_without_type_returns_last_events(fresh_bus):
    fresh_bus.emit(SecurityAlertEvent(rule="a"))
    fresh_bus.emit(CrashEvent(context="b"))
    fresh_bus.emit(OrderFilledEvent(symbol="ETH/USDT"))

    replayed = fresh_bus.replay(last_n=2)

    assert [type(event) for event in replayed] == [CrashEvent, OrderFilledEvent]


@pytest.mark.asyncio
async def test_emit_async_waits_for_async_handlers(fresh_bus):
    received = []

    async def handler(event: BaseEvent) -> None:
        await asyncio.sleep(0)
        received.append(event)

    fresh_bus.subscribe_async(SecurityAlertEvent, handler)
    await fresh_bus.emit_async(SecurityAlertEvent(rule="async"))

    assert len(received) == 1
    assert received[0].rule == "async"


@pytest.mark.asyncio
async def test_sync_emit_schedules_async_handlers_when_loop_exists(fresh_bus):
    called = asyncio.Event()

    async def handler(event: BaseEvent) -> None:
        called.set()

    fresh_bus.subscribe_async(SecurityAlertEvent, handler)
    fresh_bus.emit(SecurityAlertEvent(rule="scheduled"))

    await asyncio.wait_for(called.wait(), timeout=1)


def test_configure_audit_writes_jsonl(tmp_path, fresh_bus):
    audit_path = tmp_path / "nested" / "events.jsonl"
    fresh_bus.configure_audit(audit_path)

    fresh_bus.emit(SecurityAlertEvent(severity="high", rule="audit"))

    rows = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["rule"] == "audit"
