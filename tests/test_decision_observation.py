"""
Tests pour observability/decision_observation.py

Couvre : build_from_result(), to_dict(), observation_id format,
         tolérance aux champs manquants, immutabilité (frozen).
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from observability.decision_observation import DecisionObservation, build_from_result

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_signal(**kwargs) -> Any:
    defaults = dict(
        symbol="BTC/USDT",
        signal="BUY",
        score=75,
        regime="bull_trend",
        confirmed=True,
        strength=0.8,
        actionable=True,
        timestamp=time.time(),
        components={"mtf": 30, "regime": 20, "data_quality": 12, "memory": 13},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_gate(allowed: bool = True, failed: list | None = None) -> Any:
    return SimpleNamespace(allowed=allowed, failed=failed or [])


def _minimal_result(**kwargs) -> Dict[str, Any]:
    r: Dict[str, Any] = {
        "signal": _make_signal(),
        "gate": _make_gate(),
        "prix": 67000.0,
        "trade_allowed": True,
        "meta_allowed": True,
        "meta_reason": "OK",
        "blockers": "",
        "order_size": 50.0,
        "regime": "bull_trend",
        "features": {"rsi": 65.0, "atr_ratio": 0.012},
    }
    r.update(kwargs)
    return r


# ── Tests build_from_result ───────────────────────────────────────────────────


def test_build_minimal():
    obs = build_from_result(_minimal_result(), cycle=1)
    assert isinstance(obs, DecisionObservation)
    assert obs.symbol == "BTC/USDT"
    assert obs.side == "BUY"
    assert obs.score == 75.0
    assert obs.price == 67000.0
    assert obs.cycle == 1
    assert obs.trade_allowed is True


def test_observation_id_format():
    obs = build_from_result(_minimal_result(), cycle=5)
    # Format : "YYYYMMDD-SYMBOL-XXXXXX"
    parts = obs.observation_id.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 8  # date
    assert parts[1] == "BTC"  # symbol sans USDT
    assert len(parts[2]) == 6  # hex court


def test_blockers_parsed_correctly():
    r = _minimal_result(
        trade_allowed=False,
        blockers="conviction, portfolio",
    )
    obs = build_from_result(r, cycle=2)
    assert obs.trade_allowed is False
    assert obs.first_blocker == "conviction"
    assert "portfolio" in obs.all_blockers
    assert len(obs.all_blockers) == 2


def test_human_verdict_refused():
    r = _minimal_result(trade_allowed=False, blockers="gate")
    obs = build_from_result(r, cycle=3)
    assert "REFUSÉ" in obs.human_verdict
    assert "Risk Gate" in obs.human_verdict


def test_human_verdict_allowed():
    r = _minimal_result(trade_allowed=True, blockers="")
    obs = build_from_result(r, cycle=3)
    assert obs.human_verdict == "AUTORISÉ"


def test_human_verdict_non_actionable():
    r = _minimal_result(
        signal=_make_signal(actionable=False, signal="HOLD"),
        trade_allowed=False,
        blockers="",
    )
    obs = build_from_result(r, cycle=3)
    assert "NON ACTIONABLE" in obs.human_verdict


def test_conviction_enrichment():
    conviction = SimpleNamespace(
        level=SimpleNamespace(value="MEDIUM"),
        score=55.0,
        size_factor=0.6,
        dimensions={"signal": 40.0, "mtf": 30.0, "regime": 20.0},
        blocks_trade=lambda: False,
    )
    r = _minimal_result(conviction=conviction)
    obs = build_from_result(r, cycle=1)
    assert obs.conviction_level == "MEDIUM"
    assert obs.conviction_score == 55.0
    assert obs.conviction_size_factor == 0.6
    assert obs.conviction_dimensions["signal"] == 40.0
    assert obs.conviction_ok is True


def test_conviction_blocking():
    conviction = SimpleNamespace(
        level=SimpleNamespace(value="SKIP"),
        score=10.0,
        size_factor=0.0,
        dimensions={},
        blocks_trade=lambda: True,
    )
    r = _minimal_result(
        trade_allowed=False, blockers="conviction", conviction=conviction
    )
    obs = build_from_result(r, cycle=1)
    assert obs.conviction_ok is False
    assert obs.conviction_level == "SKIP"


def test_gate_failed_list():
    gate = _make_gate(allowed=False, failed=["score_too_low", "mtf_not_confirmed"])
    r = _minimal_result(gate=gate, trade_allowed=False, blockers="gate")
    obs = build_from_result(r, cycle=1)
    assert obs.gate_allowed is False
    assert "score_too_low" in obs.gate_failed


def test_features_only_floats():
    r = _minimal_result(
        features={"rsi": 65.0, "label": "bullish", "atr": 150.0, "active": True}
    )
    obs = build_from_result(r, cycle=1)
    # Seuls les float/int doivent être dans features
    assert "rsi" in obs.features
    assert "atr" in obs.features
    assert "label" not in obs.features
    assert "active" not in obs.features


def test_frozen_dataclass():
    obs = build_from_result(_minimal_result(), cycle=1)
    with pytest.raises((AttributeError, TypeError)):
        obs.symbol = "ETH/USDT"  # type: ignore[misc]


def test_to_dict_roundtrip():
    obs = build_from_result(_minimal_result(), cycle=7)
    d = obs.to_dict()
    assert d["symbol"] == "BTC/USDT"
    assert d["cycle"] == 7
    assert isinstance(d["all_blockers"], list)
    assert isinstance(d["features"], dict)
    assert isinstance(d["state_history"], list)


def test_tolerant_missing_keys():
    # Résultat minimal sans aucun objet optionnel
    r: Dict[str, Any] = {
        "signal": _make_signal(),
        "prix": 1000.0,
    }
    obs = build_from_result(r, cycle=0)
    assert obs.symbol == "BTC/USDT"
    assert obs.gate_allowed is True  # défaut tolérant
    assert obs.conviction_ok is True
    assert obs.all_blockers == []


def test_score_decomposition():
    sig = _make_signal(
        components={"mtf": 35.5, "regime": 22.0, "data_quality": 10.0, "memory": 8.0}
    )
    obs = build_from_result(_minimal_result(signal=sig), cycle=1)
    assert obs.score_mtf == 35.5
    assert obs.score_regime == 22.0
    assert obs.score_data_quality == 10.0
    assert obs.score_memory == 8.0
