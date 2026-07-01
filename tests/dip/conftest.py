"""
Fixtures partagées pour les tests DIP.

Fournit:
  - obs_approved / obs_rejected : DecisionObservation synthétiques
  - tmp_store : DIPStore en mémoire (:memory:)
  - populated_store : store avec N=10 décisions pré-insérées
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dip.core.store import DIPStore
from dip.core.types import compute_hash, now_us

# ── Mock DecisionObservation ───────────────────────────────────────────────────


def _make_obs(
    trade_allowed: bool, symbol: str = "BTCUSDT", regime: str = "SIDEWAYS"
) -> Any:
    obs = MagicMock()
    obs.packet_id = str(uuid.uuid4())
    obs.symbol = symbol
    obs.direction = "LONG"
    obs.trade_allowed = trade_allowed
    obs.first_blocker = None if trade_allowed else "NoTradeLayer"
    obs.all_blockers = [] if trade_allowed else ["NoTradeLayer"]
    obs.regime = regime
    obs.personality_name = "momentum"

    # Layer fields
    obs.score = 75.0
    obs.ts = 1750000000.0  # unix timestamp seconds
    obs.authority_ok = True
    obs.meta_allowed = True
    obs.meta_reason = "OK"
    obs.gate_allowed = True
    obs.gate_failed = None
    obs.awareness_ok = True
    obs.awareness_level = "NORMAL"
    obs.conviction_ok = True
    obs.conviction_level = "HIGH"
    obs.conviction_score = 0.75
    obs.conviction_size_factor = 1.0
    obs.notrade_ok = True
    obs.notrade_reason = None
    obs.notrade_rejection_score = 0.0
    obs.portfolio_ok = True
    obs.portfolio_reason = None
    obs.portfolio_size_factor = 1.0
    obs.cae_ok = True
    obs.cae_size_usd = 10.0
    obs.cae_kelly = 0.3
    obs.cae_ev = 0.05
    obs.mistake_ok = True
    obs.mistake_reason = None
    obs.override_ok = True
    obs.override_level = "NONE"
    obs.override_size_factor = 1.0
    obs.override_reason = None
    obs.radar_ok = True
    obs.radar_level = "LOW"
    obs.radar_threat_count = 0
    obs.arbitration_decision = "APPROVED" if trade_allowed else "REJECTED"
    obs.human_verdict = None
    obs.state_history = []
    obs.reasoning = "Test observation"

    if not trade_allowed:
        obs.meta_allowed = False
        obs.meta_reason = "confidence_too_low"
        obs.first_blocker = "MetaStrategy"
        obs.all_blockers = ["MetaStrategy"]

    return obs


@pytest.fixture
def obs_approved():
    return _make_obs(trade_allowed=True)


@pytest.fixture
def obs_rejected():
    return _make_obs(trade_allowed=False)


@pytest.fixture
def obs_rejected_gate():
    # Start from approved (meta passes), then override gate
    obs = _make_obs(trade_allowed=True)
    obs.trade_allowed = False
    obs.gate_allowed = False
    obs.gate_failed = ["regime_filter"]  # must be a list for join()
    obs.first_blocker = "Gate"
    obs.all_blockers = ["Gate"]
    obs.arbitration_decision = "REJECTED"
    return obs


# ── DIPStore in-memory ────────────────────────────────────────────────────────


@pytest.fixture
def tmp_store(tmp_path):
    """DIPStore avec fichier temporaire."""
    db = tmp_path / "test_dip.sqlite"
    # Reset singleton pour les tests
    DIPStore._instance = None
    store = DIPStore.instance(db_path=db)
    yield store
    # Cleanup
    DIPStore._instance = None


def _insert_decision(store: DIPStore, **kwargs) -> str:
    packet_id = kwargs.get("packet_id", str(uuid.uuid4()))
    data = {
        "packet_id": packet_id,
        "symbol": kwargs.get("symbol", "BTCUSDT"),
        "direction": kwargs.get("direction", "LONG"),
        "regime": kwargs.get("regime", "SIDEWAYS"),
        "status": kwargs.get("status", "REJECTED"),
        "created_at_us": kwargs.get("created_at_us", now_us()),
        "root_cause_layer": kwargs.get("root_cause_layer", "NoTradeLayer"),
        "explainability_score": kwargs.get("explainability_score", None),
        "explainability_grade": kwargs.get("explainability_grade", None),
        "graph_json": kwargs.get("graph_json", None),
        "hash": "placeholder",
    }
    store.upsert_decision(packet_id, data)
    return packet_id


@pytest.fixture
def populated_store(tmp_store):
    """Store avec 10 décisions (8 REJECTED, 2 APPROVED)."""
    for i in range(8):
        _insert_decision(
            tmp_store,
            symbol="BTCUSDT",
            status="REJECTED",
            regime="SIDEWAYS",
            root_cause_layer="NoTradeLayer",
        )
    for i in range(2):
        _insert_decision(
            tmp_store,
            symbol="BTCUSDT",
            status="APPROVED",
            regime="TRENDING_UP",
            root_cause_layer=None,
        )
    return tmp_store
