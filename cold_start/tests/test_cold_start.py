"""
test_cold_start.py — Tests du Cold Start Protocol (P10)

Couvre :
  1. WarmupStateMachine — transitions, timeouts, FAILED
  2. WarmupMetrics — calcul score, live_ready
  3. WarmupInvariants — 8 invariants définis
  4. ColdStartManager — tick(), is_live_ready(), failure_reason()
  5. WarmupScenarios — validation des 12 scénarios CS-01 → CS-12
  6. WarmupReport — génération rapport
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("P10_SHADOW_MIN_CYCLES", "3")  # accélérer les tests
os.environ.setdefault("P10_LIVE_READY_THRESHOLD", "0.85")
os.environ.setdefault("P10_MAX_ZERO_DATA_TICKS", "5")  # CS-03 échoue vite


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _good_snapshot(**overrides) -> dict:
    """Snapshot système sain — passe tous les invariants."""
    base = {
        "capital_total": 10_000.0,
        "symbols_ready": 85,
        "symbols_total": 100,
        "avg_feature_confidence": 0.88,
        "regime_stability": 0.82,
        "regime_last_updated_ts": time.time() - 60,
        "risk_governor_state": "NORMAL",
        "risk_sync": True,
        "hard_limits_ok": True,
        "probation_consistent": True,
        "evolution_memory_loaded": True,
        "transition_cache_populated": True,
        "strategy_weights": {
            "scalp": 0.20,
            "momentum": 0.25,
            "mean_reversion": 0.25,
            "breakout": 0.15,
            "grid": 0.15,
        },
        "open_positions_unknown": False,
        "kill_switch_safe_mode": False,
        "anomaly_count": 0,
        "dwe_sample_coverage": 0.80,
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# 1. WarmupStateMachine
# ─────────────────────────────────────────────────────────────────────────────


def test_sm_initial_state():
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    assert sm.state == WarmupState.BOOTING


def test_sm_advance_with_high_confidence():
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    state = sm.try_advance(confidence=0.95)
    assert state == WarmupState.FETCHING_MARKET_DATA


def test_sm_no_advance_with_low_confidence():
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    state = sm.try_advance(confidence=0.10)
    assert state == WarmupState.BOOTING


def test_sm_force_fail():
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    state = sm.force_fail("test failure")
    assert state == WarmupState.FAILED


def test_sm_no_advance_after_live_ready():
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    # Avancer jusqu'à LIVE_READY
    for _ in range(10):
        sm.try_advance(confidence=1.0)
    assert sm.state == WarmupState.LIVE_READY
    # Doit rester LIVE_READY
    sm.try_advance(confidence=1.0)
    assert sm.state == WarmupState.LIVE_READY


def test_sm_reset_after_fail():
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    sm.force_fail("test")
    sm.reset()
    assert sm.state == WarmupState.BOOTING


def test_sm_snapshot_contains_history():
    from cold_start.warmup_state_machine import WarmupStateMachine

    sm = WarmupStateMachine()
    sm.try_advance(confidence=0.90)
    snap = sm.snapshot()
    assert "history" in snap
    assert len(snap["history"]) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 2. WarmupMetrics
# ─────────────────────────────────────────────────────────────────────────────


def test_metrics_score_zero_on_hard_limit_breach():
    from cold_start.warmup_metrics import WarmupMetrics

    m = WarmupMetrics(hard_limits_ok=False)
    assert m.warmup_score == 0.0


def test_metrics_score_zero_on_unknown_positions():
    from cold_start.warmup_metrics import WarmupMetrics

    m = WarmupMetrics(
        hard_limits_ok=True,
        open_positions_unknown=True,
        risk_sync=True,
        symbols_ready=90,
        symbols_total=100,
    )
    assert m.warmup_score == 0.0


def test_metrics_live_ready_requires_shadow_cycles():
    from cold_start.warmup_metrics import WarmupMetrics

    m = WarmupMetrics(
        symbols_ready=90,
        symbols_total=100,
        avg_feature_confidence=0.90,
        regime_stability=0.85,
        risk_sync=True,
        hard_limits_ok=True,
        probation_consistent=True,
        evolution_memory_loaded=True,
        transition_cache_populated=True,
        shadow_cycles_completed=0,  # pas encore de shadow
    )
    assert not m.live_ready


def test_metrics_live_ready_with_all_conditions():
    from cold_start.warmup_metrics import WarmupMetrics

    m = WarmupMetrics(
        symbols_ready=90,
        symbols_total=100,
        avg_feature_confidence=0.90,
        regime_stability=0.85,
        risk_sync=True,
        hard_limits_ok=True,
        probation_consistent=True,
        evolution_memory_loaded=True,
        transition_cache_populated=True,
        shadow_cycles_completed=10,
        open_positions_unknown=False,
    )
    assert m.live_ready


def test_metrics_data_coverage():
    from cold_start.warmup_metrics import WarmupMetrics

    m = WarmupMetrics(symbols_ready=75, symbols_total=100)
    assert abs(m.data_coverage - 0.75) < 1e-6


def test_metrics_history_stability():
    from cold_start.warmup_metrics import MetricsHistory, WarmupMetrics

    hist = MetricsHistory(window=3)
    for _ in range(3):
        m = WarmupMetrics(
            symbols_ready=85,
            symbols_total=100,
            avg_feature_confidence=0.88,
            regime_stability=0.82,
            risk_sync=True,
        )
        hist.record(m)
    # Scores très stables → stabilité proche de 1.0
    assert hist.stability_score() > 0.90


# ─────────────────────────────────────────────────────────────────────────────
# 3. WarmupInvariants
# ─────────────────────────────────────────────────────────────────────────────


def test_inv_capital_not_negative_passes():
    from cold_start.warmup_invariants import WarmupInvariants

    inv = WarmupInvariants()
    results, critical = inv.check("BOOTING", _good_snapshot())
    assert not critical


def test_inv_capital_negative_fails():
    from cold_start.warmup_invariants import WarmupInvariants

    inv = WarmupInvariants()
    results, critical = inv.check("BOOTING", _good_snapshot(capital_total=-100.0))
    assert critical


def test_inv_unknown_positions_fails_validating_risk():
    from cold_start.warmup_invariants import WarmupInvariants

    inv = WarmupInvariants()
    _, critical = inv.check(
        "VALIDATING_RISK", _good_snapshot(open_positions_unknown=True)
    )
    assert critical


def test_inv_hard_limits_breach_fails():
    from cold_start.warmup_invariants import WarmupInvariants

    inv = WarmupInvariants()
    _, critical = inv.check(
        "FETCHING_MARKET_DATA", _good_snapshot(hard_limits_ok=False)
    )
    assert critical


def test_inv_nan_weights_fails():
    from cold_start.warmup_invariants import WarmupInvariants

    inv = WarmupInvariants()
    snap = _good_snapshot()
    snap["strategy_weights"]["scalp"] = float("nan")
    _, critical = inv.check("VALIDATING_RISK", snap)
    assert critical


def test_inv_weights_sum_one_fails():
    from cold_start.warmup_invariants import WarmupInvariants

    inv = WarmupInvariants()
    snap = _good_snapshot()
    snap["strategy_weights"]["scalp"] = 0.99  # somme > 1
    _, critical = inv.check("VALIDATING_RISK", snap)
    assert critical


def test_inv_all_pass_good_snapshot():
    from cold_start.warmup_invariants import WarmupInvariants

    inv = WarmupInvariants()
    for state in [
        "BOOTING",
        "FETCHING_MARKET_DATA",
        "BUILDING_FEATURES",
        "STABILIZING_REGIMES",
        "VALIDATING_RISK",
        "SHADOW_MODE",
        "LIVE_READY",
    ]:
        _, critical = inv.check(state, _good_snapshot())
        assert not critical, f"Invariant critique inattendu à l'état {state}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. ColdStartManager
# ─────────────────────────────────────────────────────────────────────────────


def test_manager_initial_not_live_ready():
    from cold_start.cold_start_manager import ColdStartManager

    mgr = ColdStartManager()
    assert not mgr.is_live_ready()


def test_manager_fails_on_unknown_positions():
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    snap = _good_snapshot(open_positions_unknown=True)
    # BOOTING passe (invariant ajouté), FETCHING_MARKET_DATA fail
    state = WarmupState.BOOTING
    for _ in range(5):
        state = mgr.tick(snap)
        if state == WarmupState.FAILED:
            break
    assert state == WarmupState.FAILED


def test_manager_fails_on_negative_capital():
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    state = mgr.tick(_good_snapshot(capital_total=-500.0))
    assert state == WarmupState.FAILED


def test_manager_progresses_through_states():
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    # Injecter un snapshot parfait — doit avancer rapidement
    snap = _good_snapshot()
    states_seen = set()
    for _ in range(50):
        state = mgr.tick(snap)
        states_seen.add(state)
        if state in (WarmupState.LIVE_READY, WarmupState.FAILED):
            break
    assert WarmupState.FETCHING_MARKET_DATA in states_seen


def test_manager_warmup_score_nonzero_on_good_snapshot():
    from cold_start.cold_start_manager import ColdStartManager

    mgr = ColdStartManager()
    mgr.tick(_good_snapshot())
    assert mgr.warmup_score() > 0.0


def test_manager_failure_reason_set():
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    snap = _good_snapshot(open_positions_unknown=True)
    for _ in range(5):
        state = mgr.tick(snap)
        if state == WarmupState.FAILED:
            break
    assert mgr.failure_reason() != ""


def test_manager_snapshot_contains_state():
    from cold_start.cold_start_manager import ColdStartManager

    mgr = ColdStartManager()
    mgr.tick(_good_snapshot())
    snap = mgr.snapshot()
    assert "state" in snap
    assert "warmup_score" in snap
    assert "live_ready" in snap


def test_manager_live_ready_after_full_warmup():
    """Snapshot parfait + P10_SHADOW_MIN_CYCLES=3 → doit atteindre LIVE_READY."""
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    snap = _good_snapshot()
    for _ in range(100):
        state = mgr.tick(snap)
        if state == WarmupState.LIVE_READY:
            break
    assert mgr.is_live_ready(), f"état final: {mgr.current_state().name}"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Scénarios CS-01 → CS-12
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "scenario_id,expected_no_live,expected_fail",
    [
        ("CS-01", True, False),  # premier boot — pas live immédiatement
        ("CS-03", False, True),  # exchange down — FAILED après MAX_ZERO_DATA_TICKS
        ("CS-04", True, False),  # TF manquante — features trop basses
        (
            "CS-05",
            False,
            False,
        ),  # drift sans historique — progresse lentement, peut atteindre live
        ("CS-06", False, True),  # snapshot corrompu — FAILED
        ("CS-09", False, True),  # positions inconnues — FAILED
        ("CS-10", True, False),  # latency extrême — couverture < 60%
        ("CS-11", False, False),  # LM Studio down — peut atteindre live
        ("CS-12", True, False),  # 72h offline — pas live immédiatement
    ],
)
def test_scenario_behavior(scenario_id, expected_no_live, expected_fail):
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_scenarios import get_scenario
    from cold_start.warmup_state_machine import WarmupState

    scenario = get_scenario(scenario_id)
    mgr = ColdStartManager(scenario_id=scenario_id)
    snap = scenario.initial_snapshot

    final_state = WarmupState.BOOTING
    for _ in range(30):  # max 30 ticks par scénario
        final_state = mgr.tick(snap)
        if final_state in (WarmupState.LIVE_READY, WarmupState.FAILED):
            break

    if expected_fail:
        assert (
            final_state == WarmupState.FAILED
        ), f"{scenario_id}: attendu FAILED, obtenu {final_state.name}"
    if expected_no_live:
        assert (
            final_state != WarmupState.LIVE_READY
        ), f"{scenario_id}: ne devrait PAS atteindre LIVE_READY en 30 ticks"


def test_scenario_cs02_crash_recovery_progresses():
    """CS-02 : reboot avec probation incohérente — doit progresser si ça se règle."""
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_scenarios import get_scenario
    from cold_start.warmup_state_machine import WarmupState

    scenario = get_scenario("CS-02")
    mgr = ColdStartManager(scenario_id="CS-02")

    # D'abord avec snapshot dégradé
    snap_bad = scenario.initial_snapshot.copy()
    for _ in range(5):
        mgr.tick(snap_bad)

    # Puis snapshot récupéré
    snap_good = _good_snapshot()
    for _ in range(50):
        state = mgr.tick(snap_good)
        if state in (WarmupState.LIVE_READY, WarmupState.FAILED):
            break

    # Doit avoir progressé (pas rester bloqué en BOOTING)
    assert mgr.current_state() != WarmupState.BOOTING


def test_scenario_cs07_stale_cache_blocked():
    """CS-07 : régime périmé de 48h — doit rester bloqué en STABILIZING_REGIMES."""
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_scenarios import get_scenario
    from cold_start.warmup_state_machine import WarmupState

    scenario = get_scenario("CS-07")
    mgr = ColdStartManager(scenario_id="CS-07")
    snap = scenario.initial_snapshot

    for _ in range(20):
        state = mgr.tick(snap)
        if state == WarmupState.LIVE_READY:
            break

    assert state != WarmupState.LIVE_READY


def test_scenario_cs08_no_transition_cache_can_live():
    """CS-08 : transition cache vide — ne bloque pas LIVE_READY."""
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_scenarios import get_scenario
    from cold_start.warmup_state_machine import WarmupState

    scenario = get_scenario("CS-08")
    mgr = ColdStartManager(scenario_id="CS-08")
    snap = scenario.initial_snapshot

    for _ in range(100):
        state = mgr.tick(snap)
        if state == WarmupState.LIVE_READY:
            break

    # Pas de cache ne doit pas empêcher live_ready si tout le reste est bon
    assert not mgr.is_failed()


# ─────────────────────────────────────────────────────────────────────────────
# 6. WarmupReport
# ─────────────────────────────────────────────────────────────────────────────


def test_report_generated_after_fail():
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    # open_positions_unknown=True → invariant critique dès FETCHING_MARKET_DATA
    # Il faut 2 ticks : BOOTING→FETCHING (tick 1), puis fail à FETCHING (tick 2)
    snap = _good_snapshot(open_positions_unknown=True)
    for _ in range(5):
        state = mgr.tick(snap)
        if state == WarmupState.FAILED:
            break
    report = mgr.report()
    assert report.finished_at is not None
    assert not report.succeeded
    assert report.failure_reason != ""


def test_report_summary_string():
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    snap = _good_snapshot(open_positions_unknown=True)
    for _ in range(5):
        state = mgr.tick(snap)
        if state == WarmupState.FAILED:
            break
    summary = mgr.report().print_summary()
    assert "FAILED" in summary or "LIVE_READY" in summary


def test_report_to_dict_complete():
    from cold_start.cold_start_manager import ColdStartManager

    mgr = ColdStartManager()
    mgr.tick(_good_snapshot())
    d = mgr.report().to_dict()
    assert "session_id" in d
    assert "state_transitions" in d
    assert "invariant_results" in d


def test_scenarios_all_have_unique_ids():
    from cold_start.warmup_scenarios import SCENARIOS

    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))
    assert len(ids) == 12


def test_scenarios_all_have_initial_snapshot():
    from cold_start.warmup_scenarios import SCENARIOS

    for s in SCENARIOS:
        assert isinstance(s.initial_snapshot, dict)
        assert "capital_total" in s.initial_snapshot
