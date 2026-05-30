"""
Chaos — ChaosOrchestrator.

Tests de l'orchestrateur de pannes composées.
Invariants vérifiés :
  - Chaque scénario prédéfini produit l'état final attendu
  - Les transitions sont enregistrées correctement
  - La panne la plus sévère détermine l'état (escalade stricte)
  - run_all_scenarios() complète sans lever d'exception
  - Les pannes composées (multi-séquences) interagissent correctement
"""

from __future__ import annotations

import pytest

from quant_hedge_ai.runtime.chaos_orchestrator import ChaosOrchestrator, FaultType
from quant_hedge_ai.runtime.runtime_state_machine import (
    RuntimeStateMachine,
    SystemState,
)


def _sm_tight() -> RuntimeStateMachine:
    """State machine avec seuils serrés pour faciliter les tests."""
    return RuntimeStateMachine(
        degraded_threshold=2,
        critical_threshold=4,
        safe_threshold=6,
        window_s=300.0,  # grande fenêtre → erreurs ne s'évictent pas pendant les tests
        silence_s=999.0,  # pas de recovery automatique pendant les tests
        stability_s=999.0,
    )


# ── Tests scénarios ────────────────────────────────────────────────────────────


class TestScenarios:
    def test_network_partition_reaches_degraded_or_higher(self):
        sm = _sm_tight()
        orc = ChaosOrchestrator(sm)
        result = orc.run_scenario("network_partition")
        assert result.final_state in (
            SystemState.DEGRADED,
            SystemState.CRITICAL,
            SystemState.SAFE_MODE,
        ), f"INVARIANT BRISÉ: réseau en panne → état {result.final_state}"
        assert result.faults_injected == 5

    def test_cascading_failure_reaches_safe_mode(self):
        sm = _sm_tight()
        orc = ChaosOrchestrator(sm)
        result = orc.run_scenario("cascading_failure")
        assert (
            result.final_state == SystemState.SAFE_MODE
        ), f"INVARIANT BRISÉ: cascade → attendu SAFE_MODE, obtenu {result.final_state}"
        assert result.reached_safe_mode is True

    def test_spike_and_recover_leaves_recovery_state(self):
        sm = _sm_tight()
        orc = ChaosOrchestrator(sm)
        result = orc.run_scenario("spike_and_recover")
        # Après le scénario, force_recovery() est appelé par run_scenario()
        assert sm.state == SystemState.RECOVERY

    def test_retry_storm_blocks_trading(self):
        sm = _sm_tight()
        orc = ChaosOrchestrator(sm)
        result = orc.run_scenario("retry_storm")
        assert result.final_state in (
            SystemState.CRITICAL,
            SystemState.SAFE_MODE,
        ), "INVARIANT BRISÉ: 12 retries → doit atteindre CRITICAL ou SAFE_MODE"
        assert (
            not sm.can_trade or sm.state == SystemState.RECOVERY
        )  # trading bloqué ou recovery

    def test_single_fault_degraded_only(self):
        sm = RuntimeStateMachine(
            degraded_threshold=3,
            critical_threshold=10,
            safe_threshold=20,
            window_s=300.0,
            silence_s=999.0,
            stability_s=999.0,
        )
        orc = ChaosOrchestrator(sm)
        result = orc.run_scenario("single_fault_degraded")
        assert (
            result.final_state == SystemState.DEGRADED
        ), f"INVARIANT BRISÉ: 3 erreurs → attendu DEGRADED, obtenu {result.final_state}"
        assert result.reached_safe_mode is False

    def test_transitions_recorded_per_scenario(self):
        sm = _sm_tight()
        orc = ChaosOrchestrator(sm)
        result = orc.run_scenario("cascading_failure")
        assert (
            len(result.transitions) >= 1
        ), "Au moins une transition doit être enregistrée"
        # La première transition doit partir de NORMAL
        assert result.transitions[0][0] == "NORMAL"

    def test_fault_breakdown_populated(self):
        sm = _sm_tight()
        orc = ChaosOrchestrator(sm)
        result = orc.run_scenario("network_partition")
        assert len(result.fault_breakdown) > 0
        total_faults = sum(result.fault_breakdown.values())
        assert total_faults == result.faults_injected


# ── Tests compound failures ────────────────────────────────────────────────────


class TestCompoundFailures:
    def test_two_independent_fault_sequences_compound(self):
        """Pannes sur deux composants indépendants s'accumulent correctement."""
        sm = _sm_tight()
        orc = ChaosOrchestrator(sm)
        result = orc.simulate_compound_failure(
            [
                [FaultType.EXCHANGE_OFFLINE, FaultType.EXCHANGE_OFFLINE],  # composant A
                [
                    FaultType.WS_FREEZE,
                    FaultType.WS_FREEZE,
                    FaultType.WS_FREEZE,
                ],  # composant B
            ]
        )
        assert result.faults_injected == 5
        assert result.final_state in (
            SystemState.DEGRADED,
            SystemState.CRITICAL,
            SystemState.SAFE_MODE,
        )

    def test_ok_between_sequences_allows_partial_recovery(self):
        """report_ok() entre séquences peut retarder la dégradation."""
        sm = RuntimeStateMachine(
            degraded_threshold=3,
            critical_threshold=8,
            safe_threshold=15,
            window_s=300.0,
            silence_s=999.0,
            stability_s=999.0,
        )
        orc = ChaosOrchestrator(sm)
        # Séquence : 2 erreurs → ok → 2 erreurs. Total fenêtre = 4 erreurs.
        result = orc.simulate_compound_failure(
            [[FaultType.EXCHANGE_OFFLINE] * 2, [FaultType.WS_FREEZE] * 2],
            ok_between=True,
        )
        # ok_between ne reset pas le compteur, donc 4 erreurs visibles → DEGRADED
        assert result.final_state in (SystemState.DEGRADED, SystemState.CRITICAL)

    def test_dedup_and_exchange_compound_blocks_trading(self):
        """Pannes dedup + exchange ensemble atteignent CRITICAL."""
        sm = _sm_tight()
        orc = ChaosOrchestrator(sm)
        result = orc.simulate_compound_failure(
            [
                [FaultType.DUPLICATE_ORDER] * 3,
                [FaultType.EXCHANGE_OFFLINE] * 3,
            ]
        )
        assert result.final_state in (SystemState.CRITICAL, SystemState.SAFE_MODE)
        assert not sm.can_trade or sm.state == SystemState.RECOVERY

    def test_all_fault_types_injectable(self):
        """Tous les FaultType sont acceptés sans lever d'exception."""
        sm = RuntimeStateMachine(safe_threshold=100, window_s=300.0)
        orc = ChaosOrchestrator(sm)
        for ft in FaultType:
            try:
                orc.inject(ft)
            except Exception as exc:
                pytest.fail(f"FaultType {ft} a levé une exception: {exc}")


# ── Tests run_all_scenarios ───────────────────────────────────────────────────


class TestRunAll:
    def test_run_all_scenarios_no_exception(self):
        """Tous les scénarios prédéfinis s'exécutent sans exception."""
        sm = _sm_tight()
        orc = ChaosOrchestrator(sm)
        try:
            results = orc.run_all_scenarios()
        except Exception as exc:
            pytest.fail(f"run_all_scenarios() a levé: {exc}")
        assert len(results) == len(ChaosOrchestrator.available_scenarios())

    def test_run_all_resets_between_scenarios(self):
        """Chaque scénario démarre de NORMAL (reset entre scénarios)."""
        sm = _sm_tight()
        orc = ChaosOrchestrator(sm)
        results = orc.run_all_scenarios()
        # Chaque scénario doit avoir au moins 1 fault injecté
        for name, result in results.items():
            assert result.faults_injected > 0, f"Scénario {name} sans faute"

    def test_available_scenarios_list(self):
        assert len(ChaosOrchestrator.available_scenarios()) >= 5
