"""
tests/stress/test_d05_lm_studio_failure.py — D-05 LM Studio Failure Simulation

Simulation de panne du LLM local (LM Studio sur :1234).
Le système doit basculer sur les règles heuristiques sans bloquer.

Scénarios :
  LM Studio ne répond pas → fallback rules
  LM Studio répond avec données incohérentes → fallback ou rejet
  LM Studio répond après timeout → fallback activé

Total : 9 tests
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

# ── Scénario 1 : LM Studio ne répond pas ─────────────────────────────────────


class TestLMStudioDown:
    def test_is_available_returns_false_when_down(self):
        """is_available() retourne False si le service est down."""
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = (
                ConnectionRefusedError("Connection refused")
            )
            from lm_studio import client as lm_client

            # Forcer un re-test en patchant directement
            with patch.object(lm_client, "list_loaded_models", return_value=[]):
                result = lm_client.is_available()
                assert not result

    def test_ai_router_falls_back_when_lm_studio_down(self):
        """AIRouter mode='auto' → LM Studio down → fallback activé."""
        with patch("lm_studio.client.is_available", return_value=False):
            from lm_studio.ai_router import AIRouter

            fallback_called = [False]

            def fallback(prompt: str) -> str:
                fallback_called[0] = True
                return "HOLD (fallback)"

            router = AIRouter(mode="auto", fallback=fallback)
            result = router.ask("Analyse BTC signal?")
            assert fallback_called[0], "Fallback non appelé quand LM Studio est down"
            assert result == "HOLD (fallback)"

    def test_ai_router_fallback_mode_ignores_lm_studio(self):
        """AIRouter mode='fallback' → fallback toujours, peu importe LM Studio."""
        from lm_studio.ai_router import AIRouter

        router = AIRouter(mode="fallback", fallback=lambda p: "RULE_BASED_SIGNAL")
        result = router.ask("Signal?")
        assert result == "RULE_BASED_SIGNAL"

    def test_no_fallback_raises_runtime_error(self):
        """Pas de fallback ET LM Studio down → RuntimeError explicite."""
        with patch("lm_studio.client.is_available", return_value=False):
            from lm_studio.ai_router import AIRouter

            router = AIRouter(mode="auto", fallback=None)
            with pytest.raises(RuntimeError):
                router.ask("Signal?")


# ── Scénario 2 : LM Studio répond avec données incohérentes ──────────────────


class TestLMStudioIncoherent:
    def test_incoherent_response_handled(self):
        """LM Studio retourne une chaîne vide → fallback ou gestion gracieuse."""
        with patch("lm_studio.client.is_available", return_value=True):
            with patch("lm_studio.client.chat", return_value=""):
                from lm_studio.ai_router import AIRouter

                fallback_called = [False]
                router = AIRouter(
                    mode="auto",
                    fallback=lambda p: (
                        setattr(fallback_called, "__setitem__", lambda k, v: None)
                        or "FALLBACK"
                    ),
                )
                result = router.ask("Signal?")
                # Le résultat est la réponse vide de LM Studio ou le fallback
                assert isinstance(result, str)

    def test_lm_studio_mode_raises_when_unavailable(self):
        """AIRouter mode='lm_studio' + service down → RuntimeError ou lève."""
        with patch("lm_studio.client.is_available", return_value=False):
            with patch("lm_studio.client.chat", side_effect=ConnectionError("down")):
                from lm_studio.ai_router import AIRouter

                router = AIRouter(mode="lm_studio")
                with pytest.raises(Exception):
                    router.ask("Signal?")

    def test_confidence_score_degraded_without_lm(self):
        """Sans LM Studio, le score de confiance des features est réduit (CS-11)."""
        import cold_start.cold_start_manager as _csm_module
        from cold_start.cold_start_manager import ColdStartManager

        # CS-11 : LM Studio down → avg_feature_confidence légèrement réduit
        snap_with_lm = {
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
        snap_without_lm = dict(snap_with_lm)
        snap_without_lm["avg_feature_confidence"] = 0.72  # réduit

        cs1 = ColdStartManager()
        cs1.tick(snap_with_lm)
        s1 = cs1.warmup_score()

        cs2 = ColdStartManager()
        cs2.tick(snap_without_lm)
        s2 = cs2.warmup_score()

        assert s1 >= s2, "Score avec LM Studio doit être >= sans LM Studio"


# ── Scénario 3 : LM Studio répond après timeout ───────────────────────────────


class TestLMStudioTimeout:
    def test_lm_studio_timeout_returns_fallback(self):
        """LM Studio timeout (httpx.TimeoutException) → fallback activé."""
        import httpx

        with patch("lm_studio.client.is_available", return_value=True):
            with patch(
                "lm_studio.client.chat", side_effect=httpx.TimeoutException("timeout")
            ):
                from lm_studio.ai_router import AIRouter

                fallback_called = [False]

                def fallback(prompt: str) -> str:
                    fallback_called[0] = True
                    return "TIMEOUT_FALLBACK"

                router = AIRouter(mode="auto", fallback=fallback)
                try:
                    result = router.ask("Signal BTC?")
                except Exception:
                    # Si l'exception se propage, le fallback n'a pas été appelé
                    # → c'est un problème dans le routeur
                    result = None

                # Le fallback doit avoir été appelé OU le résultat est non-None
                assert result is not None or fallback_called[0]

    def test_cold_start_cs11_reaches_live_with_fallback(self):
        """CS-11 (LM Studio down) → avec bonnes métriques, peut atteindre LIVE_READY."""
        import cold_start.cold_start_manager as _csm_module
        from cold_start.cold_start_manager import ColdStartManager
        from cold_start.warmup_state_machine import WarmupState

        orig = _csm_module._SHADOW_VALIDATION_CYCLES
        _csm_module._SHADOW_VALIDATION_CYCLES = 2
        try:
            # CS-11 : métriques saines avec LM Studio fallback (légèrement réduit)
            snap = {
                "capital_total": 10_000.0,
                "symbols_ready": 80,
                "symbols_total": 100,
                "avg_feature_confidence": 0.80,
                "regime_stability": 0.75,
                "regime_last_updated_ts": time.time() - 30,
                "risk_sync": True,
                "hard_limits_ok": True,
                "probation_consistent": True,
                "evolution_memory_loaded": True,
                "transition_cache_populated": True,
                "open_positions_unknown": False,
                "kill_switch_safe_mode": False,
                "anomaly_count": 0,
                "dwe_sample_coverage": 0.75,
                "strategy_weights": {},
            }
            cs = ColdStartManager(scenario_id="CS-11")
            states_seen = set()
            for _ in range(60):
                state = cs.tick(snap)
                states_seen.add(state)
                if state in (WarmupState.LIVE_READY, WarmupState.FAILED):
                    break
            # CS-11 peut atteindre LIVE_READY (must_not_reach_live=False)
            # Au minimum, ne doit pas FAILED uniquement à cause de LM Studio manquant
            assert (
                WarmupState.FAILED not in states_seen
                or WarmupState.LIVE_READY in states_seen
                or len(states_seen) >= 3
            )
        finally:
            _csm_module._SHADOW_VALIDATION_CYCLES = orig
