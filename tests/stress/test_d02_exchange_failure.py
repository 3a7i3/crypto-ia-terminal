"""
tests/stress/test_d02_exchange_failure.py — D-02 Exchange Failure Simulation

Simulation de panne d'un ou plusieurs exchanges.
Le système doit refuser de trader sur données invalides ou absentes.

Scénarios :
  1 exchange down                → dégradation contrôlée (couverture partielle)
  2 exchanges down simultanément → couverture très basse
  Tous exchanges down            → FAILED ou SHADOW_MODE forcé
  Données partielles             → rejet feature incomplète
  Données corrompues             → rejet invariant

Total : 12 tests
"""

from __future__ import annotations

import time

import pytest

import cold_start.cold_start_manager as _csm_module
from cold_start.cold_start_manager import ColdStartManager
from cold_start.warmup_state_machine import WarmupState

_TERMINAL = {WarmupState.LIVE_READY, WarmupState.FAILED}
_SHADOW_FAST = 2


def _run(snapshot: dict, max_ticks: int = 30) -> tuple:
    orig = _csm_module._SHADOW_VALIDATION_CYCLES
    _csm_module._SHADOW_VALIDATION_CYCLES = _SHADOW_FAST
    try:
        cs = ColdStartManager()
        snap = dict(snapshot)
        for n in range(max_ticks):
            state = cs.tick(snap)
            if state in _TERMINAL:
                return state, n + 1, cs.snapshot()
        return cs.current_state(), max_ticks, cs.snapshot()
    finally:
        _csm_module._SHADOW_VALIDATION_CYCLES = orig


# ── Scénario 1 : 1 exchange down ─────────────────────────────────────────────


class TestOneExchangeDown:
    def test_partial_coverage_degrades_gracefully(self):
        """1 exchange down → 60% symboles + features dégradées → dégradation contrôlée."""
        snap = {
            "capital_total": 10_000.0,
            "symbols_ready": 60,
            "symbols_total": 100,
            "avg_feature_confidence": 0.72,
            "regime_stability": 0.65,
            "regime_last_updated_ts": time.time() - 30,
            "risk_governor_state": "NORMAL",
            "risk_sync": True,
            "hard_limits_ok": True,
            "probation_consistent": True,
            "evolution_memory_loaded": True,
            "transition_cache_populated": True,
            "open_positions_unknown": False,
            "kill_switch_safe_mode": False,
            "anomaly_count": 0,
            "dwe_sample_coverage": 0.60,
            "strategy_weights": {
                "scalp": 0.25,
                "momentum": 0.25,
                "mean_reversion": 0.25,
                "breakout": 0.25,
            },
        }
        state, ticks, snap_out = _run(snap, max_ticks=50)
        # Avec 60% couverture et features 0.72, le système peut FAILED (boucle détectée)
        # ou rester bloqué — les 2 sont "dégradation contrôlée" (pas de LIVE_READY)
        assert (
            state != WarmupState.LIVE_READY
        ), "1 exchange down avec features dégradées ne doit pas atteindre LIVE_READY"

    def test_one_exchange_down_never_live_with_low_confidence(self):
        """1 exchange down → feature confidence < 0.70 → bloqué."""
        snap = {
            "capital_total": 10_000.0,
            "symbols_ready": 58,
            "symbols_total": 100,
            "avg_feature_confidence": 0.55,  # sous le seuil
            "regime_stability": 0.50,
            "regime_last_updated_ts": time.time() - 60,
            "risk_sync": True,
            "hard_limits_ok": True,
            "probation_consistent": True,
            "evolution_memory_loaded": True,
            "transition_cache_populated": True,
            "open_positions_unknown": False,
            "kill_switch_safe_mode": False,
            "anomaly_count": 0,
            "dwe_sample_coverage": 0.55,
            "strategy_weights": {},
        }
        state, ticks, _ = _run(snap, max_ticks=20)
        assert state != WarmupState.LIVE_READY


# ── Scénario 2 : 2 exchanges down ────────────────────────────────────────────


class TestTwoExchangesDown:
    def test_two_exchanges_down_blocks_progression(self):
        """2 exchanges down → 35% symboles → bloqué en FETCHING_MARKET_DATA."""
        snap = {
            "capital_total": 10_000.0,
            "symbols_ready": 35,
            "symbols_total": 100,
            "avg_feature_confidence": 0.40,
            "regime_stability": 0.30,
            "regime_last_updated_ts": time.time() - 120,
            "risk_sync": True,
            "hard_limits_ok": True,
            "probation_consistent": True,
            "evolution_memory_loaded": True,
            "transition_cache_populated": False,
            "open_positions_unknown": False,
            "kill_switch_safe_mode": False,
            "anomaly_count": 1,
            "dwe_sample_coverage": 0.30,
            "strategy_weights": {},
        }
        state, ticks, _ = _run(snap, max_ticks=20)
        assert state != WarmupState.LIVE_READY

    def test_two_exchanges_down_score_degraded(self):
        """2 exchanges down → warmup_score réduit visible dans le snapshot."""
        snap = {
            "capital_total": 10_000.0,
            "symbols_ready": 35,
            "symbols_total": 100,
            "avg_feature_confidence": 0.40,
            "regime_stability": 0.30,
            "regime_last_updated_ts": time.time() - 60,
            "risk_sync": True,
            "hard_limits_ok": True,
            "probation_consistent": True,
            "evolution_memory_loaded": True,
            "transition_cache_populated": False,
            "open_positions_unknown": False,
            "kill_switch_safe_mode": False,
            "anomaly_count": 0,
            "dwe_sample_coverage": 0.25,
            "strategy_weights": {},
        }
        cs = ColdStartManager()
        cs.tick(snap)
        assert (
            cs.warmup_score() < 0.80
        ), f"Score {cs.warmup_score():.3f} doit être < 0.80 avec 35% couverture"


# ── Scénario 3 : Tous exchanges down ─────────────────────────────────────────


class TestAllExchangesDown:
    def test_all_exchanges_down_fails(self):
        """0 symboles × _MAX_ZERO_DATA_TICKS → FAILED obligatoire."""
        orig_zero = _csm_module._MAX_ZERO_DATA_TICKS
        _csm_module._MAX_ZERO_DATA_TICKS = 5  # réduit pour la vitesse
        try:
            snap = {
                "capital_total": 10_000.0,
                "symbols_ready": 0,
                "symbols_total": 100,
                "avg_feature_confidence": 0.0,
                "regime_stability": 0.0,
                "regime_last_updated_ts": time.time(),
                "risk_sync": False,
                "hard_limits_ok": True,
                "probation_consistent": True,
                "evolution_memory_loaded": False,
                "transition_cache_populated": False,
                "open_positions_unknown": False,
                "kill_switch_safe_mode": False,
                "anomaly_count": 0,
                "dwe_sample_coverage": 0.0,
                "strategy_weights": {},
            }
            state, ticks, snap_out = _run(snap, max_ticks=20)
            assert (
                state == WarmupState.FAILED
            ), f"Tous exchanges down doit → FAILED, obtenu {state.name}"
        finally:
            _csm_module._MAX_ZERO_DATA_TICKS = orig_zero

    def test_all_exchanges_down_failure_reason_set(self):
        """Raison de FAILED doit mentionner l'absence de données marché."""
        orig_zero = _csm_module._MAX_ZERO_DATA_TICKS
        _csm_module._MAX_ZERO_DATA_TICKS = 3
        try:
            snap = {
                "capital_total": 10_000.0,
                "symbols_ready": 0,
                "symbols_total": 100,
                "avg_feature_confidence": 0.0,
                "regime_stability": 0.0,
                "regime_last_updated_ts": time.time(),
                "risk_sync": False,
                "hard_limits_ok": True,
                "probation_consistent": True,
                "evolution_memory_loaded": False,
                "transition_cache_populated": False,
                "open_positions_unknown": False,
                "kill_switch_safe_mode": False,
                "anomaly_count": 0,
                "dwe_sample_coverage": 0.0,
                "strategy_weights": {},
            }
            cs = ColdStartManager()
            for _ in range(10):
                state = cs.tick(snap)
                if state == WarmupState.FAILED:
                    break
            assert cs.is_failed()
            reason = cs.failure_reason()
            assert reason, "La raison du FAILED ne doit pas être vide"
        finally:
            _csm_module._MAX_ZERO_DATA_TICKS = orig_zero


# ── Scénario 4 : Données partielles ──────────────────────────────────────────


class TestPartialData:
    def test_partial_data_blocks_live_ready(self):
        """60% symboles + features incomplètes → ne peut pas atteindre LIVE_READY."""
        snap = {
            "capital_total": 10_000.0,
            "symbols_ready": 60,
            "symbols_total": 100,
            "avg_feature_confidence": 0.58,  # sous 0.70 requis
            "regime_stability": 0.45,
            "regime_last_updated_ts": time.time() - 30,
            "risk_sync": True,
            "hard_limits_ok": True,
            "probation_consistent": True,
            "evolution_memory_loaded": True,
            "transition_cache_populated": True,
            "open_positions_unknown": False,
            "kill_switch_safe_mode": False,
            "anomaly_count": 0,
            "dwe_sample_coverage": 0.55,
            "strategy_weights": {},
        }
        state, ticks, _ = _run(snap, max_ticks=25)
        assert state != WarmupState.LIVE_READY


# ── Scénario 5 : Données corrompues ──────────────────────────────────────────


class TestCorruptedData:
    def test_unknown_positions_is_critical_invariant(self):
        """Positions inconnues → invariant critique → FAILED immédiat."""
        from cold_start.warmup_invariants import (
            WarmupInvariants,
            inv_no_unknown_positions,
        )

        snap = {"open_positions_unknown": True, "capital_total": 10_000.0}
        result = inv_no_unknown_positions(snap)
        assert not result.passed
        assert result.critical

    def test_negative_capital_is_critical_invariant(self):
        """Capital négatif → invariant critique."""
        from cold_start.warmup_invariants import inv_capital_not_negative

        snap = {"capital_total": -500.0}
        result = inv_capital_not_negative(snap)
        assert not result.passed

    def test_corrupted_data_triggers_failed(self):
        """Données corrompues (positions inconnues) → FAILED en 1 tick."""
        snap = {
            "capital_total": 10_000.0,
            "symbols_ready": 80,
            "symbols_total": 100,
            "avg_feature_confidence": 0.85,
            "regime_stability": 0.80,
            "regime_last_updated_ts": time.time() - 10,
            "risk_sync": True,
            "hard_limits_ok": True,
            "probation_consistent": True,
            "evolution_memory_loaded": True,
            "transition_cache_populated": True,
            "open_positions_unknown": True,  # corruption
            "kill_switch_safe_mode": False,
            "anomaly_count": 0,
            "dwe_sample_coverage": 0.80,
            "strategy_weights": {},
        }
        state, ticks, _ = _run(snap, max_ticks=5)
        assert state == WarmupState.FAILED
        assert ticks <= 2
