"""
chaos_orchestrator.py — Injecteur de pannes multi-composants.

Orchestre des incidents composés (corrélés) contre la RuntimeStateMachine
pour valider que les mécanismes de protection interagissent correctement.

La vraie valeur ici n'est pas chaque panne individuelle (déjà couverte dans
tests/chaos/), mais les interactions entre protections concurrentes :
  - retry + dedup + state machine → risque de livelock
  - auto-heal + watchdog → risque de storm de transitions
  - fallback + circuit breaker → risque de masquage d'erreur

Usage :
    sm = RuntimeStateMachine(degraded_threshold=3, ...)
    orc = ChaosOrchestrator(sm)
    result = orc.run_scenario("network_partition")
    print(result.final_state, result.transitions, result.recovery_s)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from observability.json_logger import get_logger
from quant_hedge_ai.runtime.runtime_state_machine import (
    RuntimeStateMachine,
    SystemState,
)

_log = get_logger("quant_hedge_ai.runtime.chaos_orchestrator")


class FaultType(str, Enum):
    EXCHANGE_OFFLINE = "exchange_offline"
    WS_FREEZE = "ws_freeze"
    STALE_SIGNAL = "stale_signal"
    CACHE_CORRUPTION = "cache_corruption"
    CPU_SPIKE = "cpu_spike"
    PARTIAL_FILL = "partial_fill"
    DUPLICATE_ORDER = "duplicate_order"


@dataclass
class ScenarioResult:
    scenario_name: str
    faults_injected: int
    transitions: list[tuple[str, str]]  # (old, new) pour chaque transition
    final_state: SystemState
    reached_safe_mode: bool
    recovery_s: float | None  # temps de recovery (ou None si pas atteint)
    peak_error_count: int
    fault_breakdown: dict[str, int]


# ── Scénarios prédéfinis ────────────────────────────────────────────────────

# Format : list[FaultType] = séquence d'injections
_SCENARIOS: dict[str, list[FaultType]] = {
    # Panne réseau : exchange + websocket simultanés
    "network_partition": [
        FaultType.EXCHANGE_OFFLINE,
        FaultType.WS_FREEZE,
        FaultType.EXCHANGE_OFFLINE,
        FaultType.WS_FREEZE,
        FaultType.EXCHANGE_OFFLINE,
    ],
    # Données empoisonnées : corruption cache + signaux stale
    "data_storm": [
        FaultType.CACHE_CORRUPTION,
        FaultType.STALE_SIGNAL,
        FaultType.CACHE_CORRUPTION,
        FaultType.STALE_SIGNAL,
        FaultType.CACHE_CORRUPTION,
        FaultType.STALE_SIGNAL,
        FaultType.CACHE_CORRUPTION,
    ],
    # Cascade : chaque composant tombe l'un après l'autre
    "cascading_failure": [
        FaultType.WS_FREEZE,
        FaultType.STALE_SIGNAL,
        FaultType.CACHE_CORRUPTION,
        FaultType.CPU_SPIKE,
        FaultType.EXCHANGE_OFFLINE,
        FaultType.EXCHANGE_OFFLINE,
        FaultType.CPU_SPIKE,
        FaultType.EXCHANGE_OFFLINE,
        FaultType.EXCHANGE_OFFLINE,
        FaultType.CPU_SPIKE,
    ],
    # Spike ponctuel suivi de récupération rapide
    "spike_and_recover": [
        FaultType.CPU_SPIKE,
        FaultType.CPU_SPIKE,
        FaultType.CPU_SPIKE,
        # suivi de report_ok → RECOVERY
    ],
    # Retry storm : même faute répétée rapidement (bot loop)
    "retry_storm": [FaultType.DUPLICATE_ORDER] * 12,
    # Panne minimale pour valider la frontière DEGRADED
    "single_fault_degraded": [
        FaultType.EXCHANGE_OFFLINE,
        FaultType.EXCHANGE_OFFLINE,
        FaultType.EXCHANGE_OFFLINE,
    ],
}


class ChaosOrchestrator:
    """
    Injecte des séquences de pannes dans une RuntimeStateMachine
    et mesure le comportement systémique résultant.
    """

    def __init__(self, state_machine: RuntimeStateMachine) -> None:
        self._sm = state_machine
        self._transitions: list[tuple[str, str]] = []
        self._sm.on_transition(self._record_transition)

    def _record_transition(self, old: SystemState, new: SystemState) -> None:
        self._transitions.append((old.value, new.value))

    # ── API publique ───────────────────────────────────────────────────────────

    def inject(self, fault: FaultType) -> SystemState:
        """Injecte une panne unique. Retourne l'état résultant."""
        return self._sm.report_error(fault.value)

    def inject_many(self, faults: list[FaultType]) -> SystemState:
        """Injecte une liste de pannes en séquence."""
        state = self._sm.state
        for f in faults:
            state = self._sm.report_error(f.value)
        return state

    def run_scenario(self, name: str) -> ScenarioResult:
        """
        Exécute un scénario prédéfini et mesure les métriques de résilience.
        Remet la state machine à RECOVERY après le scénario (simule la résolution).
        """
        if name not in _SCENARIOS:
            raise ValueError(
                f"Scénario inconnu: {name!r}. Disponibles: {list(_SCENARIOS)}"
            )

        self._transitions.clear()
        t_start = time.perf_counter()
        faults = _SCENARIOS[name]

        for fault in faults:
            self._sm.report_error(fault.value)

        peak_errors = self._sm.error_count
        reached_safe = self._sm.state == SystemState.SAFE_MODE
        final_state = self._sm.state

        # Simule la résolution de l'incident
        self._sm.force_recovery()
        self._sm.report_ok()

        recovery_s = (
            time.perf_counter() - t_start
            if self._sm.state == SystemState.RECOVERY
            else None
        )

        result = ScenarioResult(
            scenario_name=name,
            faults_injected=len(faults),
            transitions=list(self._transitions),
            final_state=final_state,
            reached_safe_mode=reached_safe,
            recovery_s=round(recovery_s, 4) if recovery_s else None,
            peak_error_count=peak_errors,
            fault_breakdown=self._sm.fault_counts,
        )
        _log.info(
            "[Chaos] %s — %d faults, state=%s, transitions=%d",
            name,
            len(faults),
            final_state.value,
            len(self._transitions),
        )
        return result

    def run_all_scenarios(self) -> dict[str, ScenarioResult]:
        """Exécute tous les scénarios prédéfinis et retourne les résultats."""
        results = {}
        for name in _SCENARIOS:
            self._sm.reset()
            results[name] = self.run_scenario(name)
        return results

    def simulate_compound_failure(
        self,
        fault_sequences: list[list[FaultType]],
        ok_between: bool = False,
    ) -> ScenarioResult:
        """
        Injecte plusieurs séquences de pannes (issues de composants distincts).
        Si ok_between=True, insère un report_ok() entre chaque séquence.
        Utile pour tester les interactions entre mécanismes de protection.
        """
        self._transitions.clear()
        all_faults: list[FaultType] = []
        for i, seq in enumerate(fault_sequences):
            all_faults.extend(seq)
            for f in seq:
                self._sm.report_error(f.value)
            if ok_between and i < len(fault_sequences) - 1:
                self._sm.report_ok()

        final = self._sm.state
        self._sm.force_recovery()

        return ScenarioResult(
            scenario_name="compound",
            faults_injected=len(all_faults),
            transitions=list(self._transitions),
            final_state=final,
            reached_safe_mode=final == SystemState.SAFE_MODE,
            recovery_s=None,
            peak_error_count=self._sm.error_count,
            fault_breakdown=self._sm.fault_counts,
        )

    @staticmethod
    def available_scenarios() -> list[str]:
        return list(_SCENARIOS)
