"""
Tests pour observability/decision_event_bus.py

Couvre : subscribe/publish, dispatch asynchrone, erreur listener capturée,
         listener_count, start/stop, singleton get_bus().
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

from observability.decision_event_bus import DecisionEventBus, get_bus

# ── Fixture observation minimale ──────────────────────────────────────────────


def _fake_obs(**kwargs) -> Any:
    defaults = dict(
        observation_id="20260629-BTC-ABC123",
        symbol="BTC/USDT",
        side="BUY",
        score=75.0,
        trade_allowed=False,
        actionable=True,
        all_blockers=["conviction"],
        first_blocker="conviction",
        cycle=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_subscribe_increases_count():
    bus = DecisionEventBus()
    bus.start()
    assert bus.listener_count == 0
    bus.subscribe(lambda obs: None)
    assert bus.listener_count == 1
    bus.subscribe(lambda obs: None)
    assert bus.listener_count == 2
    bus.stop()


def test_publish_calls_listener():
    bus = DecisionEventBus()
    bus.start()
    received: list[Any] = []

    def listener(obs: Any) -> None:
        received.append(obs)

    bus.subscribe(listener)
    obs = _fake_obs()
    bus.publish(obs)
    # Attendre que le thread pool dispatche
    time.sleep(0.2)
    assert len(received) == 1
    assert received[0].symbol == "BTC/USDT"
    bus.stop()


def test_publish_multiple_listeners():
    bus = DecisionEventBus()
    bus.start()
    counts = [0, 0, 0]

    bus.subscribe(lambda obs: counts.__setitem__(0, counts[0] + 1))
    bus.subscribe(lambda obs: counts.__setitem__(1, counts[1] + 1))
    bus.subscribe(lambda obs: counts.__setitem__(2, counts[2] + 1))

    bus.publish(_fake_obs())
    time.sleep(0.3)
    assert counts == [1, 1, 1]
    bus.stop()


def test_failing_listener_does_not_crash_bus():
    bus = DecisionEventBus()
    bus.start()
    received: list[Any] = []

    def bad_listener(obs: Any) -> None:
        raise RuntimeError("Listener crash")

    def good_listener(obs: Any) -> None:
        received.append(obs)

    bus.subscribe(bad_listener)
    bus.subscribe(good_listener)
    bus.publish(_fake_obs())
    time.sleep(0.3)
    # Le bon listener doit quand même être appelé
    assert len(received) == 1
    bus.stop()


def test_publish_without_listeners_is_noop():
    bus = DecisionEventBus()
    bus.start()
    # Ne doit pas lever d'exception
    bus.publish(_fake_obs())
    bus.stop()


def test_unsubscribe():
    bus = DecisionEventBus()
    bus.start()
    received: list[Any] = []

    def listener(obs: Any) -> None:
        received.append(obs)

    bus.subscribe(listener)
    assert bus.listener_count == 1
    removed = bus.unsubscribe(listener)
    assert removed is True
    assert bus.listener_count == 0
    bus.publish(_fake_obs())
    time.sleep(0.2)
    assert len(received) == 0
    bus.stop()


def test_unsubscribe_unknown_returns_false():
    bus = DecisionEventBus()
    bus.start()
    removed = bus.unsubscribe(lambda obs: None)
    assert removed is False
    bus.stop()


def test_lazy_start_on_publish():
    bus = DecisionEventBus()
    received: list[Any] = []
    bus.subscribe(lambda obs: received.append(obs))
    # Pas de start() explicite — doit démarrer automatiquement
    bus.publish(_fake_obs())
    time.sleep(0.3)
    assert len(received) == 1
    bus.stop()


def test_thread_safety_concurrent_publish():
    bus = DecisionEventBus()
    bus.start()
    received: list[Any] = []
    lock = threading.Lock()

    def listener(obs: Any) -> None:
        with lock:
            received.append(obs.observation_id)

    bus.subscribe(listener)

    def publish_batch() -> None:
        for i in range(10):
            obs = _fake_obs(observation_id=f"OBS-{i}")
            bus.publish(obs)

    threads = [threading.Thread(target=publish_batch) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    time.sleep(0.5)
    assert len(received) == 30
    bus.stop()


def test_get_bus_singleton():
    b1 = get_bus()
    b2 = get_bus()
    assert b1 is b2


def test_repr_contains_state():
    bus = DecisionEventBus()
    bus.start()
    r = repr(bus)
    assert "listeners=0" in r
    assert "active=True" in r
    bus.stop()
