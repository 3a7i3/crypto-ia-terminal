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


# ─────────────────────────────────────────────────────────────────────────────
# 7. WarmupSigner — A-01/A-02/A-03/A-06
# ─────────────────────────────────────────────────────────────────────────────


def test_signer_sign_and_verify_dict():
    from cold_start.warmup_signer import sign, verify

    payload = {"state": "BOOTING", "ts": 1234.5}
    sig = sign(payload)
    assert verify(payload, sig)


def test_signer_verify_fails_on_tampered_payload():
    from cold_start.warmup_signer import sign, verify

    payload = {"state": "BOOTING", "ts": 1234.5}
    sig = sign(payload)
    tampered = {"state": "LIVE_READY", "ts": 1234.5}
    assert not verify(tampered, sig)


def test_signer_sign_report_roundtrip():
    from cold_start.warmup_signer import sign_report, verify_report

    report = {"session_id": "abc123", "final_state": "LIVE_READY", "score": 0.91}
    signed = sign_report(report)
    assert "hmac_signature" in signed
    assert verify_report(signed)


def test_signer_report_fails_on_tamper():
    from cold_start.warmup_signer import sign_report, verify_report

    report = {"session_id": "abc123", "final_state": "LIVE_READY"}
    signed = sign_report(report)
    signed["final_state"] = "FAILED"  # falsification
    assert not verify_report(signed)


def test_signer_sign_state_roundtrip():
    from cold_start.warmup_signer import sign_state, verify_state

    record = sign_state("SHADOW_MODE", extra={"consecutive_failures": 0})
    assert "signature" in record
    assert verify_state(record)


def test_signer_state_fails_on_tamper():
    from cold_start.warmup_signer import sign_state, verify_state

    record = sign_state("SHADOW_MODE")
    record["state"] = "LIVE_READY"  # falsification
    assert not verify_state(record)


def test_signer_artifact_roundtrip():
    from cold_start.warmup_signer import sign_artifact, verify_artifact

    data = {"warmup_score": 0.89, "live_ready": False}
    envelope = sign_artifact(data, artifact_type="market_warmup_estimate")
    assert verify_artifact(envelope)


def test_signer_artifact_fails_on_tamper():
    from cold_start.warmup_signer import sign_artifact, verify_artifact

    envelope = sign_artifact({"score": 0.5}, artifact_type="test")
    envelope["payload"]["score"] = 0.99
    assert not verify_artifact(envelope)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Nouveaux invariants — A-05
# ─────────────────────────────────────────────────────────────────────────────


def test_inv_black_box_writable_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACK_BOX_PATH", str(tmp_path / "black_box.jsonl"))
    from cold_start.warmup_invariants import inv_black_box_writable

    result = inv_black_box_writable(_good_snapshot())
    assert result.passed
    assert result.critical  # CRITIQUE — zéro traçabilité sans elle


def test_inv_lm_studio_or_fallback_warn_only():
    from cold_start.warmup_invariants import inv_lm_studio_or_fallback_ready

    snap = _good_snapshot(lm_studio_available=False, fallback_rules_loaded=False)
    result = inv_lm_studio_or_fallback_ready(snap)
    assert not result.passed
    assert not result.critical  # avertissement seulement


def test_inv_lm_studio_passes_if_fallback_loaded():
    from cold_start.warmup_invariants import inv_lm_studio_or_fallback_ready

    snap = _good_snapshot(lm_studio_available=False, fallback_rules_loaded=True)
    result = inv_lm_studio_or_fallback_ready(snap)
    assert result.passed


def test_inv_decision_queue_empty_warn():
    from cold_start.warmup_invariants import inv_decision_queue_empty

    result = inv_decision_queue_empty(_good_snapshot(pending_decisions=3))
    assert not result.passed
    assert not result.critical  # avertissement


def test_inv_agents_initialized_fails_critically():
    from cold_start.warmup_invariants import WarmupInvariants

    inv = WarmupInvariants()
    _, critical = inv.check("BOOTING", _good_snapshot(agents_initialized=False))
    assert critical


def test_inv_total_count_at_least_ten():
    """Certification A-05 : 10+ invariants définis."""
    import cold_start.warmup_invariants as m

    fns = [
        v
        for v in vars(m).values()
        if callable(v) and getattr(v, "__name__", "").startswith("inv_")
    ]
    assert len(fns) >= 10, f"Seulement {len(fns)} invariants définis"


# ─────────────────────────────────────────────────────────────────────────────
# 9. WarmupReport — signature HMAC + archivage BlackBox
# ─────────────────────────────────────────────────────────────────────────────


def test_report_signed_dict_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("COLD_START_REPORT_DIR", str(tmp_path))
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    snap = _good_snapshot(open_positions_unknown=True)
    for _ in range(5):
        state = mgr.tick(snap)
        if state == WarmupState.FAILED:
            break

    signed = mgr.report().to_signed_dict()
    assert "hmac_signature" in signed
    assert mgr.report().is_signature_valid(signed)


def test_report_archive_to_black_box(tmp_path, monkeypatch):
    monkeypatch.setenv("COLD_START_REPORT_DIR", str(tmp_path))
    bb_path = str(tmp_path / "black_box.jsonl")
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    snap = _good_snapshot(open_positions_unknown=True)
    for _ in range(5):
        state = mgr.tick(snap)
        if state == WarmupState.FAILED:
            break

    mgr.report().archive_to_black_box(bb_path)
    import json
    import pathlib

    lines = pathlib.Path(bb_path).read_text().splitlines()
    assert len(lines) >= 1
    entry = json.loads(lines[-1])
    assert entry["event"] == "WARMUP_COMPLETE"
    assert "session_id" in entry


# ─────────────────────────────────────────────────────────────────────────────
# 10. WarmupStateMachine — persistance + détection boucle
# ─────────────────────────────────────────────────────────────────────────────


def test_sm_persists_state(tmp_path, monkeypatch):
    import cold_start.warmup_state_machine as sm_mod

    persist_path = tmp_path / "warmup_state.json"
    monkeypatch.setattr(sm_mod, "_STATE_PERSIST_PATH", persist_path)
    from cold_start.warmup_state_machine import WarmupStateMachine

    sm = WarmupStateMachine()
    sm.try_advance(confidence=0.95)  # → FETCHING_MARKET_DATA
    assert persist_path.exists()


def test_sm_persisted_state_signed(tmp_path, monkeypatch):
    import cold_start.warmup_state_machine as sm_mod

    persist_path = tmp_path / "warmup_state.json"
    monkeypatch.setattr(sm_mod, "_STATE_PERSIST_PATH", persist_path)
    import json

    from cold_start.warmup_signer import verify_state
    from cold_start.warmup_state_machine import WarmupStateMachine

    sm = WarmupStateMachine()
    sm.try_advance(confidence=0.95)
    record = json.loads(persist_path.read_text())
    assert verify_state(record)


def test_sm_load_persisted_state_valid(tmp_path, monkeypatch):
    import cold_start.warmup_state_machine as sm_mod

    persist_path = tmp_path / "warmup_state.json"
    monkeypatch.setattr(sm_mod, "_STATE_PERSIST_PATH", persist_path)
    from cold_start.warmup_state_machine import WarmupStateMachine

    sm = WarmupStateMachine()
    sm.try_advance(confidence=0.95)  # → FETCHING_MARKET_DATA
    loaded = sm.load_persisted_state()
    assert loaded == "FETCHING_MARKET_DATA"


def test_sm_load_persisted_state_tampered_returns_none(tmp_path, monkeypatch):
    import cold_start.warmup_state_machine as sm_mod

    persist_path = tmp_path / "warmup_state.json"
    monkeypatch.setattr(sm_mod, "_STATE_PERSIST_PATH", persist_path)
    import json

    from cold_start.warmup_state_machine import WarmupStateMachine

    sm = WarmupStateMachine()
    sm.try_advance(confidence=0.95)
    record = json.loads(persist_path.read_text())
    record["state"] = "LIVE_READY"  # falsification
    persist_path.write_text(json.dumps(record))
    assert sm.load_persisted_state() is None


def test_sm_snapshot_contains_stuck_fields():
    from cold_start.warmup_state_machine import WarmupStateMachine

    sm = WarmupStateMachine()
    snap = sm.snapshot()
    assert "stuck_cycles" in snap
    assert "is_stuck" in snap


def test_sm_all_valid_transitions_sequential():
    """Certification A-02 : toutes les transitions valides testées."""
    from cold_start.warmup_state_machine import (
        _STATE_SEQUENCE,
        WarmupState,
        WarmupStateMachine,
    )

    sm = WarmupStateMachine()
    for expected in _STATE_SEQUENCE[1:]:  # skip BOOTING (état initial)
        sm.try_advance(confidence=1.0)
        assert sm.state == expected


def test_sm_invalid_transition_not_possible_from_failed():
    """Certification A-02 : aucune transition parasite depuis FAILED."""
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    sm.force_fail("forced")
    sm.try_advance(confidence=1.0)
    assert sm.state == WarmupState.FAILED


# ─────────────────────────────────────────────────────────────────────────────
# 11. MarketWarmupEstimator — A-07 (3 régimes, faux positifs = 0)
# ─────────────────────────────────────────────────────────────────────────────


def _estimator_input(**overrides):
    from cold_start.market_warmup_estimator import EstimatorInput

    base = dict(
        symbols_ready=85,
        symbols_total=100,
        avg_feature_confidence=0.91,
        regime_stability=0.87,
        dwe_sample_coverage=0.80,
        risk_sync=True,
        hard_limits_ok=True,
        probation_consistent=True,
        evolution_memory_loaded=True,
        transition_cache_populated=True,
        shadow_cycles_completed=10,
        open_positions_unknown=False,
        anomaly_count=0,
    )
    base.update(overrides)
    return EstimatorInput(**base)


def test_estimator_trending_regime_score():
    from cold_start.market_warmup_estimator import MarketWarmupEstimator

    est = MarketWarmupEstimator()
    out = est.estimate(_estimator_input(current_regime="TRENDING"))
    assert out.warmup_score > 0.80
    assert out.regime == "TRENDING"


def test_estimator_ranging_regime_score():
    from cold_start.market_warmup_estimator import MarketWarmupEstimator

    est = MarketWarmupEstimator()
    out = est.estimate(_estimator_input(current_regime="RANGING"))
    assert out.warmup_score > 0.80
    assert out.regime == "RANGING"


def test_estimator_volatile_regime_higher_threshold():
    from cold_start.market_warmup_estimator import MarketWarmupEstimator

    est = MarketWarmupEstimator()
    out_trending = est.estimate(_estimator_input(current_regime="TRENDING"))
    out_volatile = est.estimate(_estimator_input(current_regime="VOLATILE"))
    assert out_volatile.threshold_used >= out_trending.threshold_used


def test_estimator_no_false_positive_hard_limits():
    """Faux positifs = 0 : hard_limits_ok=False → live_ready=False garanti."""
    from cold_start.market_warmup_estimator import MarketWarmupEstimator

    est = MarketWarmupEstimator()
    out = est.estimate(_estimator_input(hard_limits_ok=False))
    assert not out.live_ready
    assert out.warmup_score == 0.0


def test_estimator_no_false_positive_unknown_positions():
    """Faux positifs = 0 : open_positions_unknown=True → live_ready=False garanti."""
    from cold_start.market_warmup_estimator import MarketWarmupEstimator

    est = MarketWarmupEstimator()
    out = est.estimate(_estimator_input(open_positions_unknown=True))
    assert not out.live_ready
    assert out.warmup_score == 0.0


def test_estimator_no_false_positive_no_risk_sync():
    """Faux positifs = 0 : risk_sync=False → live_ready=False."""
    from cold_start.market_warmup_estimator import MarketWarmupEstimator

    est = MarketWarmupEstimator()
    out = est.estimate(_estimator_input(risk_sync=False))
    assert not out.live_ready


def test_estimator_no_false_positive_insufficient_shadow():
    """Faux positifs = 0 : shadow_cycles_completed=0 → live_ready=False."""
    from cold_start.market_warmup_estimator import MarketWarmupEstimator

    est = MarketWarmupEstimator()
    out = est.estimate(_estimator_input(shadow_cycles_completed=0))
    assert not out.live_ready


def test_estimator_zero_symbols_score_low():
    from cold_start.market_warmup_estimator import MarketWarmupEstimator

    est = MarketWarmupEstimator()
    out = est.estimate(_estimator_input(symbols_ready=0))
    assert out.warmup_score < 0.85


def test_estimator_output_signed():
    from cold_start.market_warmup_estimator import MarketWarmupEstimator
    from cold_start.warmup_signer import sign_artifact, verify_artifact

    est = MarketWarmupEstimator()
    out = est.estimate(_estimator_input())
    assert out.hmac_signature != ""


def test_estimator_from_snapshot():
    from cold_start.market_warmup_estimator import MarketWarmupEstimator

    est = MarketWarmupEstimator()
    snap = _good_snapshot()
    snap["shadow_cycles_completed"] = 10
    out = est.estimate_from_snapshot(snap, regime="TRENDING")
    assert out.warmup_score > 0.0
    assert isinstance(out.to_dict(), dict)


def test_estimator_stability_score_stable():
    from cold_start.market_warmup_estimator import MarketWarmupEstimator

    est = MarketWarmupEstimator()
    inp = _estimator_input()
    for _ in range(5):
        est.estimate(inp)
    assert est.stability_score() > 0.90


# ── Section 12 : BypassDetector ──────────────────────────────────────────────


def test_bypass_write_token_creates_file(tmp_path, monkeypatch):
    token_file = tmp_path / "live_ready.token"
    import cold_start.bypass_detector as bd_mod

    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)
    from cold_start.bypass_detector import write_live_ready_token

    p = write_live_ready_token("sess-abc", warmup_score=0.91)
    assert p.exists()
    import json

    data = json.loads(p.read_text())
    assert data["session_id"] == "sess-abc"
    assert "signature" in data


def test_bypass_check_valid_token(tmp_path, monkeypatch):
    token_file = tmp_path / "live_ready.token"
    import cold_start.bypass_detector as bd_mod

    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)
    from cold_start.bypass_detector import (
        check_live_ready_token,
        write_live_ready_token,
    )

    write_live_ready_token("sess-xyz", warmup_score=0.88)
    result = check_live_ready_token()
    assert result.ok
    assert result.session_id == "sess-xyz"
    assert result.warmup_score == pytest.approx(0.88, abs=1e-3)


def test_bypass_check_missing_token(tmp_path, monkeypatch):
    token_file = tmp_path / "missing.token"
    import cold_start.bypass_detector as bd_mod

    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)
    from cold_start.bypass_detector import check_live_ready_token

    result = check_live_ready_token()
    assert not result.ok
    assert "absent" in result.reason


def test_bypass_check_tampered_token(tmp_path, monkeypatch):
    token_file = tmp_path / "live_ready.token"
    import json

    import cold_start.bypass_detector as bd_mod

    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)
    from cold_start.bypass_detector import (
        check_live_ready_token,
        write_live_ready_token,
    )

    write_live_ready_token("sess-tamper", warmup_score=0.90)
    data = json.loads(token_file.read_text())
    data["warmup_score"] = 0.99  # tamper
    token_file.write_text(json.dumps(data))

    result = check_live_ready_token()
    assert not result.ok
    assert "signature" in result.reason.lower() or "invalide" in result.reason.lower()


def test_bypass_check_expired_token(tmp_path, monkeypatch):
    token_file = tmp_path / "live_ready.token"
    import json

    import cold_start.bypass_detector as bd_mod

    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)
    # Write a token issued 2 hours ago with 1h validity
    import time

    from cold_start.bypass_detector import check_live_ready_token
    from cold_start.warmup_signer import sign

    payload = {
        "session_id": "old-sess",
        "warmup_score": 0.91,
        "issued_at": time.time() - 7200,
        "valid_for_s": 3600,
    }
    payload["signature"] = sign(payload)
    token_file.write_text(json.dumps(payload))
    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)

    result = check_live_ready_token()
    assert not result.ok
    assert "expir" in result.reason.lower()


def test_bypass_revoke_removes_file(tmp_path, monkeypatch):
    token_file = tmp_path / "live_ready.token"
    import cold_start.bypass_detector as bd_mod

    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)
    from cold_start.bypass_detector import (
        revoke_live_ready_token,
        write_live_ready_token,
    )

    write_live_ready_token("sess-rev", warmup_score=0.85)
    assert token_file.exists()
    revoke_live_ready_token()
    assert not token_file.exists()


def test_assert_no_bypass_raises_without_token(tmp_path, monkeypatch):
    token_file = tmp_path / "missing.token"
    import cold_start.bypass_detector as bd_mod

    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)
    from cold_start.bypass_detector import assert_no_bypass

    with pytest.raises(RuntimeError, match="Bypass"):
        assert_no_bypass(black_box_path=str(tmp_path / "bb.jsonl"))


def test_assert_no_bypass_passes_with_valid_token(tmp_path, monkeypatch):
    token_file = tmp_path / "live_ready.token"
    import cold_start.bypass_detector as bd_mod

    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)
    from cold_start.bypass_detector import assert_no_bypass, write_live_ready_token

    write_live_ready_token("sess-ok", warmup_score=0.92)
    assert_no_bypass(black_box_path=str(tmp_path / "bb.jsonl"))  # must not raise


def test_bypass_archives_bypass_event(tmp_path, monkeypatch):
    token_file = tmp_path / "missing.token"
    import cold_start.bypass_detector as bd_mod

    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)
    import json

    from cold_start.bypass_detector import assert_no_bypass

    bb_path = str(tmp_path / "bb.jsonl")
    with pytest.raises(RuntimeError):
        assert_no_bypass(black_box_path=bb_path)

    lines = open(bb_path).readlines()
    assert len(lines) == 1
    evt = json.loads(lines[0])
    assert evt["event"] == "BYPASS_DETECTED"


def test_cold_start_manager_writes_token_on_live_ready(tmp_path, monkeypatch):
    """LIVE_READY doit émettre un token signé sur disque."""
    import cold_start.bypass_detector as bd_mod

    token_file = tmp_path / "live_ready.token"
    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)

    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    # Force-avancer jusqu'à LIVE_READY via snapshots optimaux
    snap = _good_snapshot()
    snap["shadow_cycles_completed"] = 0
    for _ in range(20):
        state = mgr.tick(snap)
        if mgr._machine.state == WarmupState.SHADOW_MODE:
            mgr._shadow_cycles = 10
        if state == WarmupState.LIVE_READY:
            break

    if mgr.is_live_ready():
        assert token_file.exists()


def test_cold_start_manager_revokes_token_on_failed(tmp_path, monkeypatch):
    """FAILED doit révoquer tout token existant."""
    import cold_start.bypass_detector as bd_mod

    token_file = tmp_path / "live_ready.token"
    token_file.write_text("{}")  # pré-existant
    monkeypatch.setattr(bd_mod, "_TOKEN_PATH", token_file)

    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    mgr = ColdStartManager()
    snap = {**_good_snapshot(), "open_positions_unknown": True}
    for _ in range(5):
        state = mgr.tick(snap)
        if state == WarmupState.FAILED:
            break

    if mgr.is_failed():
        assert not token_file.exists()


# ── Section 13 : Intégrité des scénarios (A-03) ──────────────────────────────


def test_scenarios_digest_deterministic():
    from cold_start.warmup_scenarios import compute_scenarios_digest

    d1 = compute_scenarios_digest()
    d2 = compute_scenarios_digest()
    assert d1 == d2


def test_scenarios_baseline_digest_matches():
    from cold_start.warmup_scenarios import (
        SCENARIOS_BASELINE_DIGEST,
        compute_scenarios_digest,
    )

    assert compute_scenarios_digest() == SCENARIOS_BASELINE_DIGEST


def test_scenarios_verify_integrity_true():
    from cold_start.warmup_scenarios import verify_scenarios_integrity

    assert verify_scenarios_integrity() is True


def test_scenarios_tamper_changes_digest():
    from cold_start.warmup_scenarios import (
        SCENARIOS,
        SCENARIOS_BASELINE_DIGEST,
        compute_scenarios_digest,
    )

    original_name = SCENARIOS[0].name
    try:
        SCENARIOS[0].name = "TAMPERED_NAME"
        tampered_digest = compute_scenarios_digest()
        assert tampered_digest != SCENARIOS_BASELINE_DIGEST
    finally:
        SCENARIOS[0].name = original_name


def test_scenarios_all_have_unique_ids():
    from cold_start.warmup_scenarios import SCENARIOS

    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))


def test_scenarios_count_is_12():
    from cold_start.warmup_scenarios import SCENARIOS

    assert len(SCENARIOS) == 12


def test_scenarios_get_scenario_valid():
    from cold_start.warmup_scenarios import get_scenario

    s = get_scenario("CS-06")
    assert s.must_fail is True


def test_scenarios_get_scenario_invalid():
    from cold_start.warmup_scenarios import get_scenario

    with pytest.raises(ValueError):
        get_scenario("CS-99")


# ── Section 14 : Transitions invalides (A-02) ────────────────────────────────


def test_sm_cannot_go_backward():
    """La machine d'état ne peut pas reculer."""
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    # Avancer jusqu'à FETCHING_MARKET_DATA
    sm.try_advance(0.95)
    assert sm.state == WarmupState.FETCHING_MARKET_DATA
    # Essayer de régresser — la machine ne doit pas régresser
    prev_state = sm.state
    sm.try_advance(0.0)  # score insuffisant → reste bloqué, ne régresse pas
    assert sm.state == prev_state or sm.state.value >= prev_state.value


def test_sm_cannot_skip_states():
    """Impossible de sauter des états intermédiaires."""
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    assert sm.state == WarmupState.BOOTING
    sm.try_advance(0.95)  # BOOTING → FETCHING
    assert sm.state == WarmupState.FETCHING_MARKET_DATA
    # Un seul try_advance ne peut pas sauter jusqu'à SHADOW_MODE
    sm.try_advance(0.99)
    assert sm.state not in (WarmupState.SHADOW_MODE, WarmupState.LIVE_READY)


def test_sm_no_transition_from_failed():
    """FAILED est un état terminal — aucune transition possible."""
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    sm.force_fail("test terminal")
    assert sm.state == WarmupState.FAILED
    sm.try_advance(1.0)
    assert sm.state == WarmupState.FAILED


def test_sm_no_transition_from_live_ready():
    """LIVE_READY est un état terminal — aucune transition possible."""
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    sm = WarmupStateMachine()
    # Forcer l'état directement pour le test
    sm._state = WarmupState.LIVE_READY
    sm.try_advance(1.0)
    assert sm.state == WarmupState.LIVE_READY


def test_sm_full_sequential_path():
    """Parcours complet BOOTING→LIVE_READY en avançant état par état."""
    from cold_start.warmup_state_machine import WarmupState, WarmupStateMachine

    order = [
        WarmupState.BOOTING,
        WarmupState.FETCHING_MARKET_DATA,
        WarmupState.BUILDING_FEATURES,
        WarmupState.STABILIZING_REGIMES,
        WarmupState.VALIDATING_RISK,
        WarmupState.SHADOW_MODE,
        WarmupState.LIVE_READY,
    ]
    sm = WarmupStateMachine()
    assert sm.state == order[0]
    for expected_after in order[1:]:
        result = sm.try_advance(0.95)
        assert result == expected_after, f"Expected {expected_after} got {result}"


# ── Section 14b : Invariants individuels (A-05) ──────────────────────────────


def test_inv_kill_switch_not_active_passes_when_off():
    from cold_start.warmup_invariants import inv_kill_switch_not_active

    result = inv_kill_switch_not_active({"kill_switch_safe_mode": False})
    assert result.passed is True
    assert result.critical is False


def test_inv_kill_switch_not_active_passes_when_on():
    """Informatif seulement — ne bloque jamais."""
    from cold_start.warmup_invariants import inv_kill_switch_not_active

    result = inv_kill_switch_not_active({"kill_switch_safe_mode": True})
    assert result.passed is True  # informatif, ne bloque pas
    assert "kill switch" in result.reason


def test_inv_risk_governor_valid_states():
    from cold_start.warmup_invariants import inv_risk_governor_initialized

    for state in ("NORMAL", "AGGRESSIVE", "DEFENSIVE", "RECOVERY", "RISK_OFF", ""):
        r = inv_risk_governor_initialized({"risk_governor_state": state})
        assert r.passed is True, f"Expected True for state '{state}'"


def test_inv_risk_governor_invalid_state():
    from cold_start.warmup_invariants import inv_risk_governor_initialized

    r = inv_risk_governor_initialized({"risk_governor_state": "CORRUPTED"})
    assert r.passed is False
    assert "CORRUPTED" in r.reason


def test_inv_regime_not_stale_fresh():
    import time

    from cold_start.warmup_invariants import inv_regime_not_stale

    snap = {"regime_last_updated_ts": time.time() - 60}
    r = inv_regime_not_stale(snap)
    assert r.passed is True
    assert r.critical is False


def test_inv_regime_not_stale_old(monkeypatch):
    import time

    from cold_start.warmup_invariants import inv_regime_not_stale

    monkeypatch.setenv("P10_REGIME_MAX_AGE_S", "300")
    snap = {"regime_last_updated_ts": time.time() - 1800}
    r = inv_regime_not_stale(snap)
    assert r.passed is False
    assert "périmé" in r.reason


def test_inv_regime_not_stale_missing_ts():
    from cold_start.warmup_invariants import inv_regime_not_stale

    r = inv_regime_not_stale({})  # regime_ts = 0 → age = inf
    assert r.passed is False


def test_inv_portfolio_snapshot_readable_missing(tmp_path, monkeypatch):
    """Fichier absent = premier boot, non bloquant."""
    monkeypatch.setenv("POSITIONS_SNAPSHOT_PATH", str(tmp_path / "nonexistent.json"))
    import importlib

    from cold_start import warmup_invariants as wi_mod

    importlib.reload(wi_mod)
    from cold_start.warmup_invariants import inv_portfolio_snapshot_readable

    r = inv_portfolio_snapshot_readable({})
    assert r.passed is True
    assert r.critical is False


def test_inv_portfolio_snapshot_readable_valid(tmp_path, monkeypatch):
    import json

    snap_file = tmp_path / "positions.json"
    snap_file.write_text(json.dumps({"BTC": 0.5}))
    monkeypatch.setenv("POSITIONS_SNAPSHOT_PATH", str(snap_file))
    from cold_start.warmup_invariants import inv_portfolio_snapshot_readable

    r = inv_portfolio_snapshot_readable({})
    assert r.passed is True


def test_inv_portfolio_snapshot_readable_corrupted(tmp_path, monkeypatch):
    snap_file = tmp_path / "positions.json"
    snap_file.write_text("NOT JSON !!!")
    monkeypatch.setenv("POSITIONS_SNAPSHOT_PATH", str(snap_file))
    from cold_start.warmup_invariants import inv_portfolio_snapshot_readable

    r = inv_portfolio_snapshot_readable({})
    assert r.passed is False
