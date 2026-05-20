from __future__ import annotations

import logging
from types import SimpleNamespace

import advisor_loop

from quant_hedge_ai.agents.intelligence.meta_strategy_engine import MetaStrategyEngine
from quant_hedge_ai.agents.intelligence.regime_transition_smoother import (
    RegimeTransitionSmoother,
)
from quant_hedge_ai.agents.risk.global_risk_gate import GlobalRiskGate


def test_meta_strategy_applies_atr_sl_to_trend_regimes():
    engine = MetaStrategyEngine()

    bull = engine.select(
        "bull_trend",
        {"atr_pct": 0.015, "realized_volatility": 0.01},
    )
    bear = engine.select(
        "bear_trend",
        {"atr_pct": 0.014, "realized_volatility": 0.01},
    )

    assert bull.sl_pct == 0.03
    assert bear.sl_pct == 0.021


def test_meta_strategy_keeps_atr_sl_floor_for_low_atr():
    engine = MetaStrategyEngine()

    personality = engine.select(
        "bull_trend",
        {"atr_pct": 0.002, "realized_volatility": 0.01},
    )

    assert personality.sl_pct == 0.008


def test_meta_strategy_uses_smoothed_transition_sl_factor():
    engine = MetaStrategyEngine()

    personality = engine.select(
        "bull_trend",
        {"atr_pct": 0.01, "realized_volatility": 0.01},
        transition_profile={"smoothed_sl_factor": 1.75},
    )

    assert personality.sl_pct == 0.0175


def test_regime_transition_smoother_ramps_threshold_and_sl():
    smoother = RegimeTransitionSmoother(ramp_cycles=4)

    initial = smoother.advance("sideways", cycle_index=1)
    steps = [smoother.advance("bull_trend", cycle_index=i) for i in range(2, 6)]

    assert initial.transition_active is False
    assert steps[0].old_regime == "sideways"
    assert steps[0].new_regime == "bull_trend"
    assert steps[0].transition_started is True
    assert steps[0].smoothed_threshold < steps[-1].smoothed_threshold
    assert steps[0].smoothed_threshold != steps[0].target_threshold
    assert steps[0].smoothed_sl_factor < steps[-1].smoothed_sl_factor
    assert steps[-1].transition_completed is True
    assert steps[-1].remaining_transition_cycles == 0
    assert steps[-1].smoothed_threshold == steps[-1].target_threshold
    assert steps[-1].smoothed_sl_factor == steps[-1].target_sl_factor


def test_global_risk_gate_uses_transition_threshold_override():
    gate = GlobalRiskGate(min_signal_score=70)
    gate.set_transition_threshold(68)

    result = gate.check(
        SimpleNamespace(
            score=68,
            confirmed=True,
            regime="bull_trend",
            signal="BUY",
            symbol="BTCUSDT",
        )
    )

    assert result.conditions["signal_score"] is True


def test_transition_debug_log_includes_required_fields(caplog, monkeypatch):
    monkeypatch.setenv("TRANSITION_DEBUG_LOG", "true")
    caplog.set_level(logging.INFO, logger="advisor_loop")

    advisor_loop._log_transition_debug(
        {
            "old_regime": "sideways",
            "new_regime": "bull_trend",
            "cycle_index": 12,
            "smoothed_threshold": 68,
            "target_threshold": 72,
            "smoothed_sl_factor": 1.625,
            "target_sl_factor": 2.0,
            "remaining_transition_cycles": 2,
            "transition_active": True,
            "transition_started": False,
            "transition_completed": False,
        }
    )

    assert "old_regime=sideways" in caplog.text
    assert "new_regime=bull_trend" in caplog.text
    assert "smoothed_threshold=68" in caplog.text
    assert "remaining_transition_cycles=2" in caplog.text
