"""
Tests pour observability/decision_explainer.py

Couvre : format stable, sections présentes, tronquage, fallback erreur,
         signaux BUY/SELL/HOLD, refus simple/multi-bloqueurs, trade autorisé.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from observability.decision_explainer import _MAX_CHARS, explain

# ── Fixture ───────────────────────────────────────────────────────────────────


def _obs(**kwargs) -> Any:
    defaults = dict(
        observation_id="20260629-ETH-A3B2C1",
        packet_id="abc-123",
        symbol="ETH/USDT",
        side="BUY",
        score=78.0,
        score_raw=78.0,
        price=3250.40,
        regime="bull_trend",
        confirmed=True,
        strength=0.8,
        actionable=True,
        score_mtf=32.0,
        score_regime=20.0,
        score_data_quality=12.0,
        score_memory=14.0,
        trade_allowed=True,
        first_blocker=None,
        all_blockers=[],
        human_verdict="AUTORISÉ",
        authority_ok=True,
        meta_allowed=True,
        meta_reason="OK",
        personality_name="momentum_following",
        personality_min_score=60.0,
        gate_allowed=True,
        gate_failed=[],
        awareness_ok=True,
        awareness_level="OK",
        conviction_ok=True,
        conviction_level="HIGH",
        conviction_score=82.0,
        conviction_size_factor=1.0,
        conviction_dimensions={
            "signal": 40.0,
            "mtf": 30.0,
            "regime": 20.0,
            "memory": 10.0,
        },
        notrade_ok=True,
        notrade_reason=None,
        notrade_rejection_score=5.0,
        portfolio_ok=True,
        portfolio_reason=None,
        portfolio_size_factor=0.9,
        cae_ok=True,
        cae_size_usd=45.0,
        cae_kelly=0.12,
        cae_ev=0.018,
        mistake_ok=True,
        mistake_reason=None,
        override_ok=True,
        override_level="CLEAR",
        override_size_factor=1.0,
        override_reason=None,
        radar_ok=True,
        radar_level="NONE",
        radar_threat_count=0,
        arbitration_decision="EXECUTE",
        base_size_usd=50.0,
        final_size_usd=45.0,
        features={"rsi": 65.0},
        state_history=[],
        reasoning=[],
        cycle=42,
        ts=0.0,
        ts_iso="",
        engine_version="v9",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── Tests de structure ────────────────────────────────────────────────────────


def test_contains_symbol():
    msg = explain(_obs(), cycle=42)
    assert "ETH/USDT" in msg


def test_contains_score():
    msg = explain(_obs(), cycle=10)
    assert "78" in msg


def test_contains_price():
    msg = explain(_obs(), cycle=1)
    assert "3250" in msg or "3,250" in msg


def test_contains_pipeline_section():
    msg = explain(_obs(), cycle=1)
    assert "PIPELINE" in msg


def test_contains_sizing_section():
    msg = explain(_obs(), cycle=1)
    assert "SIZING" in msg


def test_contains_scores_section():
    msg = explain(_obs(), cycle=1)
    assert "SCORES" in msg


def test_contains_observation_id():
    msg = explain(_obs(), cycle=1)
    assert "20260629-ETH-A3B2C1" in msg


def test_all_12_layers_present():
    msg = explain(_obs(), cycle=1)
    for layer in [
        "authority",
        "meta",
        "gate",
        "conviction",
        "no_trade",
        "awareness",
        "portfolio",
        "capital",
        "mistake_mem",
        "exec_override",
        "threat_radar",
    ]:
        assert layer in msg, f"Layer '{layer}' absent du message"


def test_green_checkmarks_for_all_ok():
    msg = explain(_obs(), cycle=1)
    assert msg.count("✅") >= 10


def test_verdict_autorise():
    msg = explain(_obs(trade_allowed=True, human_verdict="AUTORISÉ"), cycle=1)
    assert "AUTORISÉ" in msg


def test_verdict_refuse_single():
    obs = _obs(
        trade_allowed=False,
        all_blockers=["conviction"],
        first_blocker="conviction",
        human_verdict="REFUSÉ — Conviction",
        conviction_ok=False,
        conviction_level="SKIP",
        conviction_score=10.0,
        conviction_size_factor=0.0,
    )
    msg = explain(obs, cycle=5)
    assert "⛔" in msg
    assert "REFUSÉ" in msg


def test_verdict_refuse_multi_blockers():
    obs = _obs(
        trade_allowed=False,
        all_blockers=["conviction", "portfolio"],
        first_blocker="conviction",
        human_verdict="REFUSÉ — Conviction + Portfolio Brain",
        conviction_ok=False,
        portfolio_ok=False,
        portfolio_reason="exposition totale 38%>35%",
    )
    msg = explain(obs, cycle=5)
    # Deux ⛔ dans le pipeline
    assert msg.count("⛔") >= 2


def test_sell_signal_icon():
    obs = _obs(side="SELL")
    msg = explain(obs, cycle=1)
    assert "📉" in msg


def test_hold_signal_icon():
    obs = _obs(side="HOLD", actionable=False, human_verdict="NON ACTIONABLE")
    msg = explain(obs, cycle=1)
    assert "⏸" in msg


def test_gate_failed_displayed():
    obs = _obs(
        gate_allowed=False,
        gate_failed=["score_too_low", "mtf_not_confirmed"],
        trade_allowed=False,
        all_blockers=["gate"],
        first_blocker="gate",
    )
    msg = explain(obs, cycle=1)
    assert "score_too_low" in msg or "BLOQUÉ" in msg


def test_cae_details_displayed():
    msg = explain(_obs(), cycle=1)
    assert "$45" in msg
    assert "kelly" in msg


def test_conviction_dimension_displayed():
    obs = _obs(conviction_dimensions={"signal": 40.0, "mtf": 30.0})
    msg = explain(obs, cycle=1)
    assert "sig=" in msg or "40" in msg


def test_arbitrator_displayed():
    obs = _obs(arbitration_decision="EXECUTE")
    msg = explain(obs, cycle=1)
    assert "arbitrator" in msg
    assert "EXECUTE" in msg


def test_max_chars_respected():
    obs = _obs(
        portfolio_reason="A" * 500,
        meta_reason="B" * 500,
        notrade_reason="C" * 500,
    )
    msg = explain(obs, cycle=1)
    assert len(msg) <= _MAX_CHARS


def test_fallback_on_internal_error():
    """Si l'obs est cassé, explain() doit quand même retourner quelque chose."""
    broken = SimpleNamespace(symbol="X/USDT", human_verdict="?", cycle=1)
    msg = explain(broken, cycle=1)  # type: ignore[arg-type]
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_cycle_number_in_output():
    msg = explain(_obs(), cycle=99)
    assert "99" in msg or "C99" in msg


def test_scores_decomposition_displayed():
    msg = explain(_obs(), cycle=1)
    assert "MTF:" in msg
    assert "/40" in msg
    assert "/25" in msg
