from __future__ import annotations

import time

from quant_hedge_ai.agents.intelligence.self_awareness_engine import (
    DangerLevel,
    SelfAwarenessEngine,
)


def test_operator_resume_lifts_halt_and_downgrades_to_warning() -> None:
    engine = SelfAwarenessEngine()
    engine.state().level = DangerLevel.CRITICAL
    engine.state().safe_mode = True
    engine.state().size_factor = 0.0
    engine.state().halt_until = time.time() + 3600

    engine.operator_resume(full_reset=False)

    state = engine.state()
    assert state.halt_until == 0.0
    assert state.level == DangerLevel.WARNING
    assert state.safe_mode is True
    assert state.size_factor == 0.25


def test_operator_resume_full_reset_returns_to_ok() -> None:
    engine = SelfAwarenessEngine()
    engine.state().level = DangerLevel.CRITICAL
    engine.state().safe_mode = True
    engine.state().halt_until = time.time() + 3600

    engine.operator_resume(full_reset=True)

    state = engine.state()
    assert state.level == DangerLevel.OK
    assert state.safe_mode is False
    assert state.halt_until == 0.0


def test_critical_halt_duration_is_configurable() -> None:
    engine = SelfAwarenessEngine()
    engine.CRITICAL_HALT_SECONDS = 120.0

    before = time.time()
    engine._apply_level(DangerLevel.CRITICAL, [])
    remaining = engine.state().halt_until - before

    assert 110.0 <= remaining <= 125.0
