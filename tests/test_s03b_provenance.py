"""
S-03B — tests focalisés sur la remédiation de provenance de décision.

Couvre :
  - identité (packet_id/trace_id préservés, observation_id résistant aux
    collisions, échec de provenance explicite)
  - RejectionStore : skip sur provenance invalide
  - EventBus : compteurs de livraison
"""

from __future__ import annotations

import time
import uuid
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from observability.decision_event_bus import DecisionEventBus
from observability.decision_observation import (
    build_from_result,
    get_provenance_failure_stats,
    normalize_side,
    side_to_packet_vocabulary,
)
from observability.rejection_store import RejectionStore


def _make_signal(**kwargs) -> Any:
    defaults = dict(
        symbol="BTC/USDT",
        signal="BUY",
        score=75,
        regime="bull_trend",
        confirmed=True,
        strength=0.8,
        actionable=True,
        components={"mtf": 30, "regime": 20, "data_quality": 12, "memory": 13},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_packet(packet_id: str = "", side: str = "LONG") -> Any:
    if not packet_id:
        return None
    return SimpleNamespace(
        packet_id=packet_id,
        metadata={"trace_id": "trace-xyz"},
        side=SimpleNamespace(value=side),
        state_history=[],
        reasoning=[],
    )


def _minimal_result(**kwargs) -> Dict[str, Any]:
    r: Dict[str, Any] = {
        "signal": _make_signal(),
        "gate": SimpleNamespace(allowed=True, failed=[]),
        "prix": 67000.0,
        "trade_allowed": False,
        "meta_allowed": True,
        "meta_reason": "OK",
        "blockers": "conviction,portfolio",
        "order_size": 50.0,
        "regime": "bull_trend",
        "features": {"rsi": 65.0, "atr_ratio": 0.012},
    }
    r.update(kwargs)
    return r


# ── Identité ────────────────────────────────────────────────────────────────


def test_packet_id_and_trace_id_preserved():
    dp = _make_packet(packet_id=str(uuid.uuid4()))
    result = _minimal_result(decision_packet=dp)
    obs = build_from_result(result, cycle=1)
    assert obs.packet_id == str(dp.packet_id)
    assert obs.trace_id == "trace-xyz"
    assert obs.provenance_valid is True


def test_observation_id_collision_resistant_across_many_generations():
    dp = _make_packet(packet_id=str(uuid.uuid4()))
    result = _minimal_result(decision_packet=dp)
    ids = {build_from_result(result, cycle=i).observation_id for i in range(500)}
    assert len(ids) == 500  # aucune collision
    # ne se termine plus par 6 hex chars tronqués — l'entropie du suffixe
    # doit être un uuid4 hex complet (32 chars)
    sample = next(iter(ids))
    suffix = sample.split("-")[-1]
    assert len(suffix) == 32


def test_missing_packet_id_triggers_provenance_failure_and_rejection_skip(tmp_path):
    before = get_provenance_failure_stats()["missing_packet_id"]
    result = _minimal_result(decision_packet=None)
    obs = build_from_result(result, cycle=1)
    assert obs.packet_id == ""
    assert obs.provenance_valid is False
    after = get_provenance_failure_stats()["missing_packet_id"]
    assert after == before + 1

    store = RejectionStore(store_dir=tmp_path)
    store.on_observation(obs)
    assert store.stats()["writes"] == 0
    assert store.stats()["skipped_provenance"] == 1


def test_rejection_store_persists_when_provenance_valid(tmp_path):
    dp = _make_packet(packet_id=str(uuid.uuid4()))
    result = _minimal_result(decision_packet=dp)
    obs = build_from_result(result, cycle=1)
    store = RejectionStore(store_dir=tmp_path)
    store.on_observation(obs)
    assert store.stats()["writes"] == 1
    assert store.stats()["skipped_provenance"] == 0


# ── Side vocabulary ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [("BUY", "BUY"), ("LONG", "BUY"), ("SELL", "SELL"), ("SHORT", "SELL"),
     ("HOLD", "HOLD"), ("FLAT", "HOLD")],
)
def test_normalize_side(raw, expected):
    assert normalize_side(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [("BUY", "LONG"), ("SELL", "SHORT"), ("HOLD", "FLAT")],
)
def test_side_to_packet_vocabulary(raw, expected):
    assert side_to_packet_vocabulary(raw) == expected


# ── First-blocker consistency ─────────────────────────────────────────────────


def test_first_blocker_consistent_between_observation_and_rejection_store(tmp_path):
    dp = _make_packet(packet_id=str(uuid.uuid4()))
    result = _minimal_result(decision_packet=dp, blockers="conviction,portfolio")
    obs = build_from_result(result, cycle=1)
    assert obs.first_blocker == "conviction"
    assert obs.all_blockers == ["conviction", "portfolio"]

    store = RejectionStore(store_dir=tmp_path)
    store.on_observation(obs)
    path = store._get_path()
    import json

    with open(path) as f:
        line = json.loads(f.readline())
    assert line["first_blocker"] == "conviction"
    assert line["all_blockers"] == ["conviction", "portfolio"]


# ── EventBus counters ──────────────────────────────────────────────────────────


def test_eventbus_counters_success_and_failure():
    bus = DecisionEventBus(max_workers=2)
    bus.start()

    ok_calls = []

    def good_listener(obs):
        ok_calls.append(obs)

    def bad_listener(obs):
        raise RuntimeError("boom")

    bus.subscribe(good_listener)
    bus.subscribe(bad_listener)

    bus.publish(object())
    time.sleep(0.3)

    stats = bus.get_stats()
    assert stats["observations_published"] == 1
    assert stats["listener_deliveries_submitted"] == 2
    assert stats["listener_deliveries_succeeded"] == 1
    assert stats["listener_deliveries_failed"] == 1
    assert len(ok_calls) == 1

    bus.stop()
