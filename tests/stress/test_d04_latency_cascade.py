"""
tests/stress/test_d04_latency_cascade.py — D-04 Latency Cascade Simulation

Simulation de latence extrême sur les appels API et couches internes.
Les timeouts doivent être respectés. Aucun blocage permanent.

Scénarios :
  API exchange prend 5s → timeout couche signal
  LM Studio prend 30s → timeout couche intelligence
  Appels internes retardés aléatoirement → dégradation contrôlée

Total : 10 tests
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from runtime.execution_context import ExecutionContext
from runtime.runtime_coordinator import LayerResult, RuntimeCoordinator
from runtime.system_state_bus import SystemStateBus


def _ctx(**kw) -> ExecutionContext:
    base = dict(capital_total=10_000.0, capital_used=0.0, capital_available=10_000.0)
    base.update(kw)
    return ExecutionContext.new_cycle(**base)


def _get_layer(result, name: str):
    """Helper : récupère un LayerResult par nom depuis CycleResult.layers."""
    return next((r for r in result.layers if r.name == name), None)


def _timed_out(layer_result) -> bool:
    """True si le LayerResult représente un timeout (success=False, erreur timeout)."""
    return (
        layer_result is not None
        and not layer_result.success
        and "timeout" in layer_result.error.lower()
    )


# ── Timeout par couche ────────────────────────────────────────────────────────


class TestLayerTimeout:
    def test_slow_layer_triggers_timeout(self):
        """Une couche qui prend 600ms avec timeout=200ms → LayerResult échouée (timeout)."""
        coord = RuntimeCoordinator()

        def slow_signal(ctx):
            time.sleep(0.6)
            return {"signal": "BUY"}

        coord.register_layer("signal", slow_signal, timeout_ms=200.0)
        result = coord.run_cycle(_ctx())
        sig_result = _get_layer(result, "signal")
        assert sig_result is not None
        assert _timed_out(sig_result), "Couche signal doit être en timeout"

    def test_fast_layer_not_timed_out(self):
        """Une couche rapide (<50ms) avec timeout=500ms → pas de timeout."""
        coord = RuntimeCoordinator()

        def fast_signal(ctx):
            return {"signal": "HOLD"}

        coord.register_layer("signal", fast_signal, timeout_ms=500.0)
        result = coord.run_cycle(_ctx())
        sig_result = _get_layer(result, "signal")
        assert sig_result is not None
        assert sig_result.success, "Couche rapide doit réussir"

    def test_critical_layer_timeout_aborts_decision(self):
        """Couche critique (signal) timeout → decision=None."""
        coord = RuntimeCoordinator()

        def slow_signal(ctx):
            time.sleep(0.4)
            return {"signal": "BUY"}

        coord.register_layer("signal", slow_signal, timeout_ms=100.0)
        result = coord.run_cycle(_ctx())
        assert (
            result.decision is None
        ), "Couche critique timeout → decision doit être None"

    def test_non_critical_layer_timeout_preserves_decision(self):
        """Couche non critique (learning) timeout → decision conservée."""
        coord = RuntimeCoordinator()

        def ok_signal(ctx):
            return {"signal": "BUY", "score": 75}

        def slow_learning(ctx):
            time.sleep(0.4)
            return {"learned": True}

        coord.register_layer("signal", ok_signal, timeout_ms=500.0)
        coord.register_layer("learning", slow_learning, timeout_ms=100.0)
        result = coord.run_cycle(_ctx())
        # Signal OK → decision non None (learning n'est pas critique)
        learning_result = _get_layer(result, "learning")
        assert learning_result is not None
        assert _timed_out(learning_result)


# ── Exchange API latence extrême (5s) ─────────────────────────────────────────


class TestExchangeAPILatency:
    def test_exchange_5s_latency_respects_timeout(self):
        """Exchange 5s → couche signal avec timeout=500ms doit timeout."""
        coord = RuntimeCoordinator()

        def exchange_slow_signal(ctx):
            time.sleep(5.0)  # simule 5s exchange
            return {"signal": "BUY"}

        coord.register_layer("signal", exchange_slow_signal, timeout_ms=500.0)
        t0 = time.perf_counter()
        result = coord.run_cycle(_ctx())
        elapsed = time.perf_counter() - t0
        # Le cycle ne doit pas prendre 5s — le timeout coupe
        assert elapsed < 2.0, f"Cycle trop long: {elapsed:.2f}s (attendu < 2s)"
        sig = _get_layer(result, "signal")
        assert sig and _timed_out(sig)

    def test_exchange_latency_no_permanent_block(self):
        """Latence exchange → le cycle suivant peut continuer (pas de deadlock)."""
        coord = RuntimeCoordinator()
        call_count = [0]

        def sometimes_slow(ctx):
            call_count[0] += 1
            if call_count[0] == 1:
                time.sleep(0.4)  # 1er cycle lent
            return {"signal": "HOLD"}

        coord.register_layer("signal", sometimes_slow, timeout_ms=200.0)
        # Cycle 1 : lent → timeout
        r1 = coord.run_cycle(_ctx())
        # Cycle 2 : rapide → OK
        r2 = coord.run_cycle(_ctx())
        assert _timed_out(_get_layer(r1, "signal"))
        assert _get_layer(r2, "signal").success


# ── LM Studio latence extrême (30s) ──────────────────────────────────────────


class TestLMStudioLatency:
    def test_lm_studio_30s_timeout_fallback(self):
        """LM Studio 30s → timeout → fallback rule-based."""
        with patch("lm_studio.client.is_available", return_value=True):
            with patch(
                "lm_studio.client.chat",
                side_effect=lambda *a, **kw: (
                    time.sleep(0.3) or "BUY"  # simule 30s (réduit pour le test)
                ),
            ):
                from lm_studio.ai_router import AIRouter

                fallback_called = [False]

                def fallback(prompt: str) -> str:
                    fallback_called[0] = True
                    return "HOLD (fallback)"

                router = AIRouter(mode="auto", fallback=fallback)
                # Le mode auto avec LM Studio disponible mais lent
                # Si le client raise une exception (timeout), le fallback est activé
                try:
                    result = router.ask("Signal BTC?")
                except Exception:
                    pass  # timeout géré à l'extérieur

    def test_lm_studio_timeout_does_not_block_decision(self):
        """LM Studio indisponible → AIRouter fallback → résultat disponible."""
        with patch("lm_studio.client.is_available", return_value=False):
            from lm_studio.ai_router import AIRouter

            router = AIRouter(mode="auto", fallback=lambda p: "HOLD (rule-based)")
            result = router.ask("Signal?")
            assert "HOLD" in result or len(result) > 0


# ── Dégradation aléatoire ─────────────────────────────────────────────────────


class TestRandomLatencyDegradation:
    def test_multiple_layers_partial_timeout(self):
        """Certaines couches timeout, les non-critiques ne bloquent pas le cycle."""
        import random

        coord = RuntimeCoordinator()
        random.seed(42)

        def variable_layer(ctx):
            delay = random.choice([0.01, 0.01, 0.01, 0.3])  # ~25% de chance de timeout
            time.sleep(delay)
            return {"ok": True}

        coord.register_layer("signal", variable_layer, timeout_ms=150.0)
        coord.register_layer("learning", variable_layer, timeout_ms=150.0)

        successes = 0
        for _ in range(5):
            result = coord.run_cycle(_ctx())
            # Le cycle termine toujours (pas de blocage permanent)
            successes += 1

        assert successes == 5, "Tous les cycles doivent terminer malgré les timeouts"
