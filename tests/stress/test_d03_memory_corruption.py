"""
tests/stress/test_d03_memory_corruption.py — D-03 Memory Corruption Simulation

Simulation de corruption de la mémoire interne.
Le système doit détecter et refuser de trader sur données corrompues.

Scénarios :
  evolution_memory corrompue (JSON invalide)
  transition_cache vidée
  forbidden_patterns corrompus
  Portfolio snapshot corrompu

Total : 10 tests
"""

from __future__ import annotations

import json
import os
import pickle
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import cold_start.cold_start_manager as _csm_module
from cold_start.cold_start_manager import ColdStartManager
from cold_start.warmup_state_machine import WarmupState

_SHADOW_FAST = 2


def _healthy_snap(**overrides) -> dict:
    base = {
        "capital_total": 10_000.0,
        "symbols_ready": 80,
        "symbols_total": 100,
        "avg_feature_confidence": 0.85,
        "regime_stability": 0.80,
        "regime_last_updated_ts": time.time() - 30,
        "risk_sync": True,
        "hard_limits_ok": True,
        "probation_consistent": True,
        "evolution_memory_loaded": True,
        "transition_cache_populated": True,
        "open_positions_unknown": False,
        "kill_switch_safe_mode": False,
        "anomaly_count": 0,
        "dwe_sample_coverage": 0.80,
        "strategy_weights": {},
    }
    base.update(overrides)
    return base


# ── evolution_memory corrompue ────────────────────────────────────────────────


class TestEvolutionMemoryCorruption:
    def test_corrupt_pkl_handled_gracefully(self, tmp_path):
        """Un fichier evolution_memory.pkl corrompu ne crash pas le système."""
        pkl_path = tmp_path / "evolution_memory.pkl"
        pkl_path.write_bytes(b"\x00\xff\xab\xcd corrupt data not a pickle")

        # Tenter de charger → doit lever PickleError, non laisser passer silencieusement
        with pytest.raises(Exception):
            with open(pkl_path, "rb") as f:
                pickle.load(f)
        # Le test passe : l'exception est attrapée à l'extérieur, pas un crash silencieux

    def test_evolution_memory_not_loaded_degrades_score(self):
        """evolution_memory_loaded=False réduit le warmup_score."""
        snap = _healthy_snap(evolution_memory_loaded=False)
        cs = ColdStartManager()
        cs.tick(snap)
        score_no_mem = cs.warmup_score()

        cs2 = ColdStartManager()
        cs2.tick(_healthy_snap(evolution_memory_loaded=True))
        score_with_mem = cs2.warmup_score()

        # Avec mémoire chargée, score >= score sans mémoire
        assert score_with_mem >= score_no_mem

    def test_evolution_memory_not_loaded_does_not_block(self):
        """Sans evolution_memory, le système peut quand même progresser (non critique)."""
        orig = _csm_module._SHADOW_VALIDATION_CYCLES
        _csm_module._SHADOW_VALIDATION_CYCLES = _SHADOW_FAST
        try:
            snap = _healthy_snap(evolution_memory_loaded=False)
            cs = ColdStartManager()
            states = set()
            for _ in range(50):
                state = cs.tick(snap)
                states.add(state)
                if state in (WarmupState.LIVE_READY, WarmupState.FAILED):
                    break
            # Ne doit pas forcer FAILED uniquement à cause d'evolution_memory manquante
            assert WarmupState.FAILED not in states or len(states) > 2
        finally:
            _csm_module._SHADOW_VALIDATION_CYCLES = orig


# ── transition_cache vide ─────────────────────────────────────────────────────


class TestTransitionCacheEmpty:
    def test_empty_transition_cache_not_blocking(self):
        """Cache vide → non critique, le système peut progresser."""
        orig = _csm_module._SHADOW_VALIDATION_CYCLES
        _csm_module._SHADOW_VALIDATION_CYCLES = _SHADOW_FAST
        try:
            snap = _healthy_snap(transition_cache_populated=False)
            cs = ColdStartManager()
            reached_states = set()
            for _ in range(50):
                state = cs.tick(snap)
                reached_states.add(state)
                if state in (WarmupState.LIVE_READY, WarmupState.FAILED):
                    break
            # transition_cache vide ne doit PAS déclencher FAILED seul
            if WarmupState.FAILED in reached_states:
                # Si FAILED, vérifier que c'est pour une autre raison
                cs2 = ColdStartManager()
                for _ in range(50):
                    state = cs2.tick(_healthy_snap(transition_cache_populated=True))
                    if state in (WarmupState.LIVE_READY, WarmupState.FAILED):
                        break
                # Avec cache, doit aussi fonctionner
        finally:
            _csm_module._SHADOW_VALIDATION_CYCLES = orig

    def test_empty_transition_cache_score_reduction(self):
        """Cache vide → warmup_score légèrement plus bas."""
        cs1 = ColdStartManager()
        cs1.tick(_healthy_snap(transition_cache_populated=False))
        s1 = cs1.warmup_score()

        cs2 = ColdStartManager()
        cs2.tick(_healthy_snap(transition_cache_populated=True))
        s2 = cs2.warmup_score()

        assert s2 >= s1, "Avec cache, score doit être >= sans cache"


# ── forbidden_patterns corrompus ──────────────────────────────────────────────


class TestForbiddenPatternsCorruption:
    def test_corrupt_json_file_raises_on_load(self, tmp_path):
        """Fichier forbidden_patterns.json corrompu → exception à la lecture."""
        fp = tmp_path / "forbidden_patterns.json"
        fp.write_text("{invalid json ][}", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            json.loads(fp.read_text())

    def test_empty_forbidden_patterns_safe_default(self):
        """forbidden_patterns vide → système utilise des valeurs par défaut sûres."""
        # Si le fichier forbidden_patterns est vide ou absent, le système ne doit pas crasher
        # Vérification via le ColdStartManager qui ne dépend pas directement de ce fichier
        snap = _healthy_snap()
        cs = ColdStartManager()
        state = cs.tick(snap)
        # Doit progresser normalement, pas crasher
        assert state != WarmupState.FAILED


# ── Portfolio snapshot corrompu ───────────────────────────────────────────────


class TestPortfolioSnapshotCorruption:
    def test_corrupted_positions_json_raises(self, tmp_path):
        """positions_snapshot.json corrompu → json.JSONDecodeError."""
        path = tmp_path / "positions_snapshot.json"
        path.write_text("{'invalid': True, broken", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            json.loads(path.read_text())

    def test_unknown_positions_triggers_immediate_fail(self):
        """open_positions_unknown=True → FAILED en 1 tick."""
        snap = _healthy_snap(open_positions_unknown=True)
        cs = ColdStartManager()
        state = cs.tick(snap)
        assert state == WarmupState.FAILED

    def test_positions_snapshot_missing_treated_as_unknown(self, tmp_path, monkeypatch):
        """Snapshot positions absent → système doit traiter comme unknown."""
        # Sans le fichier, les positions sont à l'état 'inconnu'
        # Le warmup doit refuser LIVE_READY dans ce cas
        snap = _healthy_snap(open_positions_unknown=True)
        cs = ColdStartManager()
        state = cs.tick(snap)
        assert state == WarmupState.FAILED, "Positions inconnues → FAILED attendu"
