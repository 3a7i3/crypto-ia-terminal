"""
Chaos — Fault containment zones.

Tests des zones d'isolation entre composants du runtime.
Invariants vérifiés :
  - Une panne dans une zone basse n'affecte jamais une zone haute
  - Les exceptions sont absorbées et ne remontent pas vers l'appelant
  - Les timeouts sont respectés et le fallback est retourné
  - La state machine reçoit report_error() à chaque panne isolée
  - ContainmentZone absorbe les exceptions comme un try/except
  - ContainmentGuard réunit zone + state machine correctement
  - Les priorités de zone sont ordonnées correctement
"""

from __future__ import annotations

import time

import pytest

from quant_hedge_ai.runtime.fault_containment import (
    ContainmentGuard,
    ContainmentZone,
    Zone,
    contained,
    is_higher_priority,
    zone_timeout,
)
from quant_hedge_ai.runtime.runtime_state_machine import (
    RuntimeStateMachine,
    SystemState,
)


def _sm_tight() -> RuntimeStateMachine:
    return RuntimeStateMachine(
        degraded_threshold=2,
        critical_threshold=6,
        safe_threshold=10,
        window_s=300.0,
        silence_s=999.0,
        stability_s=999.0,
    )


# ── Priorités et timeouts ──────────────────────────────────────────────────────


class TestZoneProperties:
    def test_execution_has_shortest_timeout(self):
        assert zone_timeout(Zone.EXECUTION) < zone_timeout(Zone.RISK)
        assert zone_timeout(Zone.RISK) < zone_timeout(Zone.AI_SCORING)
        assert zone_timeout(Zone.AI_SCORING) < zone_timeout(Zone.MONITORING)
        assert zone_timeout(Zone.MONITORING) < zone_timeout(Zone.DASHBOARD)

    def test_execution_highest_priority(self):
        for zone in [Zone.RISK, Zone.AI_SCORING, Zone.MONITORING, Zone.DASHBOARD]:
            assert is_higher_priority(
                Zone.EXECUTION, zone
            ), f"INVARIANT BRISÉ: EXECUTION doit être plus prioritaire que {zone}"

    def test_dashboard_lowest_priority(self):
        for zone in [Zone.EXECUTION, Zone.RISK, Zone.AI_SCORING, Zone.MONITORING]:
            assert not is_higher_priority(
                Zone.DASHBOARD, zone
            ), f"INVARIANT BRISÉ: DASHBOARD priorité > {zone}"

    def test_priority_is_transitive(self):
        assert is_higher_priority(Zone.EXECUTION, Zone.RISK)
        assert is_higher_priority(Zone.RISK, Zone.AI_SCORING)
        assert is_higher_priority(Zone.AI_SCORING, Zone.MONITORING)
        assert is_higher_priority(Zone.MONITORING, Zone.DASHBOARD)


# ── Décorateur @contained ─────────────────────────────────────────────────────


class TestContainedDecorator:
    def test_success_returns_value(self):
        @contained(zone=Zone.MONITORING)
        def good_fn():
            return 42

        assert good_fn() == 42

    def test_exception_absorbed_returns_fallback(self):
        @contained(zone=Zone.MONITORING, fallback="default")
        def bad_fn():
            raise RuntimeError("crash dans MONITORING")

        result = bad_fn()
        assert (
            result == "default"
        ), "INVARIANT BRISÉ: exception dans MONITORING ne doit pas remonter"

    def test_exception_absorbed_no_propagation(self):
        @contained(zone=Zone.DASHBOARD, fallback=None)
        def crashing_fn():
            raise ValueError("dashboard crash")

        try:
            result = crashing_fn()
        except Exception:
            pytest.fail(
                "CRASH SILENCIEUX: exception DASHBOARD remontée vers l'appelant"
            )
        assert result is None

    def test_timeout_returns_fallback(self):
        @contained(zone=Zone.MONITORING, timeout_s=0.05, fallback="timeout_fallback")
        def slow_fn():
            time.sleep(1.0)
            return "should_not_reach"

        result = slow_fn()
        assert (
            result == "timeout_fallback"
        ), "INVARIANT BRISÉ: timeout dans MONITORING doit retourner le fallback"

    def test_fast_fn_within_timeout(self):
        @contained(zone=Zone.AI_SCORING, timeout_s=1.0, fallback="HOLD")
        def fast_fn():
            return "BUY"

        assert fast_fn() == "BUY"

    def test_exception_reports_to_state_machine(self):
        sm = _sm_tight()

        @contained(zone=Zone.MONITORING, fallback=None, state_machine=sm)
        def bad_fn():
            raise RuntimeError("monitored crash")

        bad_fn()
        bad_fn()
        assert (
            sm.state == SystemState.DEGRADED
        ), f"INVARIANT BRISÉ: 2 pannes MONITORING → état {sm.state}"

    def test_timeout_reports_to_state_machine(self):
        sm = _sm_tight()

        @contained(
            zone=Zone.AI_SCORING, timeout_s=0.05, fallback="HOLD", state_machine=sm
        )
        def slow_fn():
            time.sleep(1.0)

        slow_fn()
        slow_fn()
        assert sm.error_count >= 2, "Timeouts doivent être reportés à la state machine"


# ── ContainmentZone (context manager) ─────────────────────────────────────────


class TestContainmentZone:
    def test_happy_path(self):
        with ContainmentZone(Zone.AI_SCORING, fallback="HOLD") as z:
            z.result = "BUY"
        assert z.result == "BUY"
        assert z.success is True

    def test_exception_absorbed(self):
        with ContainmentZone(Zone.DASHBOARD, fallback="safe") as z:
            raise RuntimeError("dashboard boom")
        assert z.result == "safe"
        assert z.success is False
        assert z.error is not None

    def test_exception_does_not_propagate(self):
        try:
            with ContainmentZone(Zone.MONITORING, fallback=0) as z:
                raise ValueError("monitoring error")
        except ValueError:
            pytest.fail("CRASH SILENCIEUX: exception de MONITORING non absorbée")
        assert z.result == 0

    def test_elapsed_ms_populated(self):
        with ContainmentZone(Zone.MONITORING) as z:
            time.sleep(0.01)
        assert z.elapsed_ms >= 5.0, f"elapsed_ms trop faible: {z.elapsed_ms}ms"

    def test_exception_reports_to_state_machine(self):
        sm = _sm_tight()
        for _ in range(2):
            with ContainmentZone(Zone.MONITORING, fallback=None, state_machine=sm) as z:
                raise RuntimeError("monitored")
        assert sm.state == SystemState.DEGRADED

    def test_result_not_overwritten_on_success(self):
        with ContainmentZone(Zone.RISK, fallback="reject") as z:
            z.result = "accept"
        # Pas d'exception → result doit rester "accept"
        assert z.result == "accept"


# ── ContainmentGuard ──────────────────────────────────────────────────────────


class TestContainmentGuard:
    def test_run_success(self):
        sm = _sm_tight()
        guard = ContainmentGuard(sm)
        result = guard.run(Zone.AI_SCORING, lambda: "SELL", fallback="HOLD")
        assert result == "SELL"

    def test_run_exception_returns_fallback(self):
        sm = _sm_tight()
        guard = ContainmentGuard(sm)

        def crash():
            raise RuntimeError("AI crash")

        result = guard.run(Zone.AI_SCORING, crash, fallback="HOLD")
        assert result == "HOLD", "INVARIANT BRISÉ: panne AI_SCORING doit retourner HOLD"

    def test_run_timeout_returns_fallback(self):
        sm = _sm_tight()
        guard = ContainmentGuard(sm)

        result = guard.run(
            Zone.AI_SCORING,
            lambda: time.sleep(2.0),
            timeout_s=0.05,
            fallback="HOLD",
        )
        assert result == "HOLD"

    def test_run_exception_escalates_state_machine(self):
        sm = _sm_tight()
        guard = ContainmentGuard(sm)

        for _ in range(2):
            guard.run(
                Zone.MONITORING,
                lambda: (_ for _ in ()).throw(RuntimeError()),
                fallback=None,
            )

        assert sm.state == SystemState.DEGRADED

    def test_result_for_success(self):
        sm = _sm_tight()
        guard = ContainmentGuard(sm)
        cr = guard.result_for(Zone.AI_SCORING, lambda: 99)
        assert cr.success is True
        assert cr.value == 99
        assert cr.zone == Zone.AI_SCORING

    def test_result_for_failure(self):
        sm = _sm_tight()
        guard = ContainmentGuard(sm)
        cr = guard.result_for(Zone.MONITORING, lambda: 1 / 0)
        assert cr.success is False
        assert cr.value is None
        assert cr.error is not None

    def test_result_for_timeout(self):
        sm = _sm_tight()
        guard = ContainmentGuard(sm)
        # Override timeout via zone (EXECUTION = 200ms)
        cr = guard.result_for(Zone.EXECUTION, lambda: time.sleep(1.0))
        assert cr.timed_out is True
        assert cr.success is False


# ── Isolation inter-zones ─────────────────────────────────────────────────────


class TestZoneIsolation:
    def test_dashboard_crash_does_not_affect_execution(self):
        """Panne DASHBOARD : la zone EXECUTION continue de fonctionner."""
        sm = _sm_tight()
        guard = ContainmentGuard(sm)

        # 9 pannes dans DASHBOARD (sous le seuil SAFE_MODE de 10)
        for _ in range(9):
            guard.run(Zone.DASHBOARD, lambda: 1 / 0, fallback=None)

        # EXECUTION doit toujours fonctionner
        result = guard.run(Zone.EXECUTION, lambda: "order_ok", fallback="rejected")
        assert (
            result == "order_ok"
        ), "INVARIANT BRISÉ: pannes DASHBOARD ont bloqué EXECUTION"
        assert sm.can_trade is True or sm.state != SystemState.SAFE_MODE

    def test_monitoring_crash_does_not_crash_ai_scoring(self):
        """Pannes MONITORING ne propagent pas d'exception vers AI_SCORING."""
        sm = _sm_tight()
        guard = ContainmentGuard(sm)

        @contained(zone=Zone.MONITORING, fallback=None, state_machine=sm)
        def broken_monitoring():
            raise RuntimeError("metrics down")

        broken_monitoring()  # ne doit pas lever d'exception

        # AI_SCORING doit fonctionner normalement
        signal = guard.run(Zone.AI_SCORING, lambda: "BUY", fallback="HOLD")
        assert signal == "BUY"

    def test_concurrent_zones_independent(self):
        """Plusieurs zones peuvent s'exécuter en parallèle sans interférence."""
        import threading

        sm = _sm_tight()
        guard = ContainmentGuard(sm)
        results = {}
        errors = []

        def run_zone(zone, fn, fallback, key):
            try:
                results[key] = guard.run(zone, fn, fallback=fallback)
            except Exception as e:
                errors.append(f"{key}: {e}")

        threads = [
            threading.Thread(
                target=run_zone,
                args=(Zone.EXECUTION, lambda: "exec", "rejected", "exec"),
            ),
            threading.Thread(
                target=run_zone, args=(Zone.MONITORING, lambda: 1 / 0, None, "monitor")
            ),
            threading.Thread(
                target=run_zone, args=(Zone.AI_SCORING, lambda: "BUY", "HOLD", "ai")
            ),
            threading.Thread(
                target=run_zone,
                args=(Zone.DASHBOARD, lambda: time.sleep(0.01), None, "dash"),
            ),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Erreurs sous parallélisme: {errors}"
        assert results.get("exec") == "exec", "EXECUTION doit réussir"
        assert results.get("monitor") is None, "MONITORING crash → fallback None"
        assert results.get("ai") == "BUY", "AI_SCORING doit réussir"
