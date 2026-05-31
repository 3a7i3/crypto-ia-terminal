"""
Tests P10-F — OperationalState machine (RUNNING / DEGRADED / HALTED).
"""

from __future__ import annotations

import time

from capital_deployment.operational_state import OperationalState, OpState


def _state() -> OperationalState:
    return OperationalState()


# ── État initial ──────────────────────────────────────────────────────────────


def test_initial_state_is_running():
    s = _state()
    assert s.is_running()
    assert s.state == OpState.RUNNING


# ── RUNNING → DEGRADED ───────────────────────────────────────────────────────


def test_single_error_stays_running():
    s = _state()
    s.record_error()
    assert s.is_running()


def test_two_errors_triggers_degraded():
    s = _state()
    s.record_error()
    s.record_error()
    assert s.is_degraded()


def test_degraded_callback_called_once():
    calls = []
    s = OperationalState(on_degraded=lambda r: calls.append(r))
    for _ in range(3):
        s.record_error()
    assert len(calls) == 1
    assert s.is_degraded()


# ── RUNNING → HALTED (10 erreurs) ────────────────────────────────────────────


def test_ten_consecutive_errors_halts():
    s = _state()
    for _ in range(10):
        s.record_error()
    assert s.is_halted()


def test_halted_callback_called():
    calls = []
    s = OperationalState(on_halted=lambda r: calls.append(r))
    for _ in range(10):
        s.record_error()
    assert len(calls) == 1
    assert "HALTED" in calls[0] or "10" in calls[0]


# ── Récupération DEGRADED → RUNNING ──────────────────────────────────────────


def test_success_after_errors_returns_to_running():
    calls = []
    s = OperationalState(on_recovered=lambda: calls.append(True))
    s.record_error()
    s.record_error()
    assert s.is_degraded()
    s.record_success()
    assert s.is_running()
    assert len(calls) == 1


def test_consecutive_errors_reset_after_success():
    s = _state()
    s.record_error()
    s.record_error()
    s.record_success()
    assert s.summary()["consecutive_errors"] == 0


def test_success_while_running_stays_running():
    s = _state()
    s.record_success()
    assert s.is_running()


# ── reset() — opérateur /RESUME ──────────────────────────────────────────────


def test_reset_from_halted_returns_running():
    s = _state()
    for _ in range(10):
        s.record_error()
    assert s.is_halted()
    s.reset()
    assert s.is_running()


def test_reset_clears_counter():
    s = _state()
    for _ in range(5):
        s.record_error()
    s.reset()
    assert s.summary()["consecutive_errors"] == 0


def test_reset_from_degraded_returns_running():
    s = _state()
    s.record_error()
    s.record_error()
    s.reset()
    assert s.is_running()


# ── DEGRADED durée → HALTED ──────────────────────────────────────────────────


def test_degraded_duration_triggers_halt(monkeypatch):
    s = OperationalState()
    s.DEGRADED_MAX_DURATION_S = 0.01  # 10ms pour le test
    s.record_error()
    s.record_error()
    assert s.is_degraded()
    time.sleep(0.05)
    s.record_error()
    assert s.is_halted()


# ── summary ───────────────────────────────────────────────────────────────────


def test_summary_running():
    s = _state()
    snap = s.summary()
    assert snap["state"] == "RUNNING"
    assert snap["consecutive_errors"] == 0
    assert snap["degraded_duration_s"] is None


def test_summary_degraded_has_duration():
    s = _state()
    s.record_error()
    s.record_error()
    snap = s.summary()
    assert snap["state"] == "DEGRADED"
    assert snap["degraded_duration_s"] is not None
    assert snap["degraded_duration_s"] >= 0


# ── Idempotence callbacks ─────────────────────────────────────────────────────


def test_halt_callback_not_called_twice():
    calls = []
    s = OperationalState(on_halted=lambda r: calls.append(r))
    for _ in range(15):
        s.record_error()
    assert len(calls) == 1


def test_degraded_not_called_again_if_already_degraded():
    calls = []
    s = OperationalState(on_degraded=lambda r: calls.append(r))
    for _ in range(5):
        s.record_error()
    assert s.is_degraded()
    assert len(calls) == 1
