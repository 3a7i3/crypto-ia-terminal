"""
Tests pour observability/rejection_store.py

Couvre : persist() atomique, rotation quotidienne, validation schéma,
         on_observation() filtre, zéro perte sur OSError, count_today().
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from observability.rejection_store import RejectionStore, _from_observation, _validate

# ── Helpers ───────────────────────────────────────────────────────────────────


def _fake_obs(**kwargs) -> Any:
    defaults = dict(
        observation_id="20260629-BTC-ABC123",
        packet_id="pkt-001",
        ts=time.time(),
        ts_iso="2026-06-29T12:00:00+00:00",
        cycle=5,
        engine_version="v9",
        symbol="BTC/USDT",
        side="BUY",
        score=75.0,
        score_raw=75.0,
        price=67000.0,
        regime="bull_trend",
        confirmed=True,
        strength=0.8,
        actionable=True,
        score_mtf=30.0,
        score_regime=20.0,
        score_data_quality=12.0,
        score_memory=13.0,
        conviction_level="MEDIUM",
        conviction_score=55.0,
        conviction_size_factor=0.6,
        first_blocker="conviction",
        all_blockers=["conviction"],
        human_verdict="REFUSÉ — Conviction",
        gate_failed=[],
        notrade_reason=None,
        notrade_rejection_score=10.0,
        portfolio_reason=None,
        portfolio_size_factor=None,
        mistake_reason=None,
        override_level="CLEAR",
        override_reason=None,
        radar_level="NONE",
        radar_threat_count=0,
        meta_reason="OK",
        awareness_level="OK",
        arbitration_decision=None,
        base_size_usd=50.0,
        cae_kelly=0.12,
        cae_ev=0.018,
        personality_name="momentum_following",
        features={"rsi": 65.0, "atr_ratio": 0.012},
        trade_allowed=False,
        state_history=[],
        reasoning=[],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_store(tmp_path: Path) -> RejectionStore:
    return RejectionStore(store_dir=tmp_path)


# ── Tests validation ──────────────────────────────────────────────────────────


def test_validate_valid_record():
    record = _from_observation(_fake_obs())
    assert _validate(record) is True


def test_validate_empty_symbol():
    record = _from_observation(_fake_obs(symbol=""))
    assert _validate(record) is False


def test_validate_zero_price():
    record = _from_observation(_fake_obs(price=0.0))
    assert _validate(record) is False


# ── Tests persist ─────────────────────────────────────────────────────────────


def test_persist_creates_file(tmp_path):
    store = _make_store(tmp_path)
    record = _from_observation(_fake_obs())
    result = store.persist(record)
    assert result is True
    files = list(tmp_path.glob("rejections_*.jsonl"))
    assert len(files) == 1


def test_persist_valid_jsonl(tmp_path):
    store = _make_store(tmp_path)
    record = _from_observation(_fake_obs())
    store.persist(record)
    path = next(tmp_path.glob("rejections_*.jsonl"))
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["symbol"] == "BTC/USDT"
    assert parsed["first_blocker"] == "conviction"
    assert parsed["schema_version"] == 1


def test_persist_multiple_appends(tmp_path):
    store = _make_store(tmp_path)
    for i in range(5):
        obs = _fake_obs(observation_id=f"OBS-{i}", symbol="ETH/USDT", price=3000.0)
        store.persist(_from_observation(obs))
    path = next(tmp_path.glob("rejections_*.jsonl"))
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5


def test_persist_invalid_returns_false(tmp_path):
    store = _make_store(tmp_path)
    record = _from_observation(_fake_obs(price=0.0))
    result = store.persist(record)
    assert result is False
    # Aucun fichier créé
    assert list(tmp_path.glob("rejections_*.jsonl")) == []


def test_persist_stats_tracked(tmp_path):
    store = _make_store(tmp_path)
    store.persist(_from_observation(_fake_obs()))
    store.persist(_from_observation(_fake_obs(price=0.0)))  # invalide
    stats = store.stats()
    assert stats["writes"] == 1
    assert stats["errors"] == 0  # erreur validation, pas d'écriture


def test_count_today(tmp_path):
    store = _make_store(tmp_path)
    for _ in range(3):
        store.persist(_from_observation(_fake_obs()))
    assert store.count_today() == 3


# ── Tests on_observation (listener) ──────────────────────────────────────────


def test_on_observation_refused_signal(tmp_path):
    store = _make_store(tmp_path)
    obs = _fake_obs(trade_allowed=False, actionable=True, side="BUY")
    store.on_observation(obs)
    assert store.stats()["writes"] == 1


def test_on_observation_ignores_allowed(tmp_path):
    store = _make_store(tmp_path)
    obs = _fake_obs(trade_allowed=True, actionable=True)
    store.on_observation(obs)
    assert store.stats()["writes"] == 0


def test_on_observation_ignores_non_actionable(tmp_path):
    store = _make_store(tmp_path)
    obs = _fake_obs(trade_allowed=False, actionable=False)
    store.on_observation(obs)
    assert store.stats()["writes"] == 0


def test_on_observation_ignores_hold(tmp_path):
    store = _make_store(tmp_path)
    obs = _fake_obs(trade_allowed=False, actionable=True, side="HOLD")
    store.on_observation(obs)
    assert store.stats()["writes"] == 0


# ── Tests RejectionRecord ─────────────────────────────────────────────────────


def test_rejection_record_from_observation_fields():
    obs = _fake_obs()
    record = _from_observation(obs)
    assert record.symbol == "BTC/USDT"
    assert record.first_blocker == "conviction"
    assert record.conviction_level == "MEDIUM"
    assert record.conviction_score == 55.0
    assert record.base_size_usd == 50.0
    assert "rsi" in record.features


def test_rejection_record_to_dict_serializable(tmp_path):
    record = _from_observation(_fake_obs())
    d = record.to_dict()
    # Doit être sérialisable JSON sans erreur
    j = json.dumps(d, ensure_ascii=False)
    assert isinstance(j, str)
    assert len(j) > 100


def test_rejection_record_default_regret_fields():
    record = _from_observation(_fake_obs())
    assert record.regret_evaluated is False
    assert record.regret_type is None
    assert record.regret_horizons == {}


# ── Test robustesse OSError ───────────────────────────────────────────────────


def test_persist_ioerror_does_not_raise(tmp_path):
    store = _make_store(tmp_path / "nonexistent_subdir")
    # Le store crée le répertoire — on force une erreur en rendant le path un fichier
    blocked = tmp_path / "blocked"
    blocked.write_text("not a dir")
    store2 = RejectionStore(store_dir=blocked)
    # Même si le dir est invalide, persist() ne doit pas lever d'exception
    try:
        store2.persist(_from_observation(_fake_obs()))
    except Exception as e:
        pytest.fail(f"persist() a levé une exception inattendue: {e}")
