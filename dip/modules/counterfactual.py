"""
dip/modules/counterfactual.py — D04 Counterfactual Engine.

Répond à la question "Et si?" pour chaque décision:
  - Que se serait-il passé si une couche n'avait pas existé?
  - Que se serait-il passé si un seuil avait été différent?

Toutes les simulations sont marquées SIMULÉES avec confiance ≤ 0.85.
Disclaimer systématique (ADR-0014).

Le simulateur replay le graph en supprimant/modifiant des couches.
Pas d'accès au moteur de décision réel — simulation pure sur le graph.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from dip.core.store import DIPStore, LRUCache
from dip.core.types import DecisionStatus, LayerStatus, ScenarioType, now_us
from dip.modules.decision_graph import DecisionGraph, get_graph_engine

_DISCLAIMER = (
    "Simulation basée sur le replay du graphe décisionnel. "
    "L'exécution réelle pourrait différer en raison de la latence, du slippage, "
    "et des effets de second ordre entre couches. "
    "Confiance maximale: 0.85."
)


# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Scenario:
    scenario_type: ScenarioType
    target_layer: Optional[str]
    parameter_overrides: Optional[dict[str, float]]
    context_overrides: Optional[dict[str, Any]]
    description: str


@dataclass(frozen=True)
class ImpactAssessment:
    outcome_changed: bool
    confidence_delta: float
    estimated_pnl_impact: float
    risk_delta: float
    exposure_delta: float


@dataclass(frozen=True)
class CounterfactualResult:
    counterfactual_id: str
    packet_id: str
    scenario: Scenario
    original_status: DecisionStatus
    counterfactual_status: DecisionStatus
    confidence_delta: float
    impact: ImpactAssessment
    confidence: float
    disclaimer: str
    created_at_us: int


@dataclass(frozen=True)
class SensitivityReport:
    layer: str
    symbol: str
    period_hours: int
    total_decisions: int
    approvals_without_layer: int
    approvals_with_layer: int
    sensitivity_score: float
    recommendation: str


@dataclass(frozen=True)
class ThresholdRecommendation:
    layer: str
    current_threshold: float
    recommended_threshold: float
    expected_impact_pct: float
    confidence: float
    rationale: str


@dataclass(frozen=True)
class CounterfactualBatch:
    batch_id: str
    packet_id: str
    results: tuple[CounterfactualResult, ...]
    total_scenarios: int
    outcome_changed_count: int
    avg_confidence_delta: float


# ── Simulateur de pipeline ────────────────────────────────────────────────────


class PipelineSimulator:
    """
    Simule un pipeline décisionnel en supprimant ou modifiant des couches.
    Travaille uniquement sur le DecisionGraph existant (pas d'accès au moteur).
    """

    @staticmethod
    def simulate_without_layer(
        graph: DecisionGraph, layer_to_remove: str
    ) -> tuple[DecisionStatus, float]:
        """
        Retire une couche du graph et recalcule le résultat.
        Retourne (nouveau_statut, nouvelle_confiance).
        """
        remaining_nodes = [n for n in graph.nodes if n.layer != layer_to_remove]
        if not remaining_nodes:
            return DecisionStatus.UNKNOWN, 0.0

        # Si la couche retirée était le bloqueur, le packet passe aux couches suivantes
        blocker_removed = any(
            n.layer == layer_to_remove and n.status == LayerStatus.BLOCKED
            for n in graph.nodes
        )

        if blocker_removed:
            # Cherche le prochain bloqueur dans les couches restantes
            next_blocker = next(
                (n for n in remaining_nodes if n.status == LayerStatus.BLOCKED), None
            )
            if next_blocker:
                return DecisionStatus.REJECTED, 0.0
            else:
                # Toutes les couches restantes passent
                final_conf = (
                    remaining_nodes[-1].confidence_after if remaining_nodes else 0.0
                )
                return DecisionStatus.APPROVED, final_conf
        else:
            # Couche non-bloquante retirée: résultat inchangé
            return graph.status, graph.metrics.confidence_end

    @staticmethod
    def simulate_with_threshold(
        graph: DecisionGraph,
        layer: str,
        threshold_multiplier: float,
    ) -> tuple[DecisionStatus, float]:
        """
        Simule un changement de seuil pour une couche.
        threshold_multiplier < 1.0 = seuil plus permissif.
        threshold_multiplier > 1.0 = seuil plus strict.
        """
        target_nodes = [n for n in graph.nodes if n.layer == layer]
        if not target_nodes:
            return graph.status, graph.metrics.confidence_end

        target = target_nodes[0]

        # Seuil plus permissif: une couche qui bloquait pourrait maintenant passer
        if target.status == LayerStatus.BLOCKED and threshold_multiplier < 1.0:
            # Probabilité de passage avec le nouveau seuil
            new_conf = target.confidence_before * threshold_multiplier
            if new_conf > 0.0:
                # Cherche le prochain bloqueur
                after_target = [
                    n for n in graph.nodes if n.node_id > target.node_id  # type: ignore
                ]
                next_block = next(
                    (n for n in after_target if n.status == LayerStatus.BLOCKED), None
                )
                if next_block:
                    return DecisionStatus.REJECTED, 0.0
                return DecisionStatus.APPROVED, new_conf

        # Seuil plus strict: une couche qui passait pourrait maintenant bloquer
        elif target.status == LayerStatus.PASSED and threshold_multiplier > 1.0:
            adjusted_conf = target.confidence_after * (1.0 / threshold_multiplier)
            if adjusted_conf < 0.3:  # seuil minimal arbitraire
                return DecisionStatus.REJECTED, 0.0

        return graph.status, graph.metrics.confidence_end


# ── Impact Assessment ──────────────────────────────────────────────────────────


class ImpactAssessor:

    @staticmethod
    def assess(
        original_status: DecisionStatus,
        cf_status: DecisionStatus,
        original_conf: float,
        cf_conf: float,
        base_size_usd: float = 10.0,
    ) -> ImpactAssessment:
        outcome_changed = original_status != cf_status
        conf_delta = cf_conf - original_conf

        # Estimation PnL: si le résultat change de REJECTED → APPROVED,
        # impact positif estimé (base size × facteur risk/reward de 1.5)
        if outcome_changed and cf_status == DecisionStatus.APPROVED:
            pnl_impact = base_size_usd * 1.5 * cf_conf
        elif outcome_changed and cf_status == DecisionStatus.REJECTED:
            pnl_impact = -base_size_usd * 0.5
        else:
            pnl_impact = 0.0

        # Risk delta approximatif
        risk_delta = (
            0.05 if outcome_changed and cf_status == DecisionStatus.APPROVED else 0.0
        )

        return ImpactAssessment(
            outcome_changed=outcome_changed,
            confidence_delta=conf_delta,
            estimated_pnl_impact=round(pnl_impact, 2),
            risk_delta=round(risk_delta, 3),
            exposure_delta=round(risk_delta * 0.5, 3),
        )


# ── Engine ─────────────────────────────────────────────────────────────────────


class CounterfactualEngine:
    """D04 — Moteur de simulations contrefactuelles."""

    def __init__(self) -> None:
        self._graph_engine = get_graph_engine()
        self._cache: LRUCache[CounterfactualResult] = LRUCache(
            max_entries=5_000, ttl_seconds=3_600
        )
        self._store = DIPStore.instance()

    def simulate_without_layer(
        self, packet_id: str, layer: str
    ) -> Optional[CounterfactualResult]:
        graph = self._graph_engine.get_graph(packet_id)
        if not graph:
            return None

        cf_status, cf_conf = PipelineSimulator.simulate_without_layer(graph, layer)
        original_conf = graph.metrics.confidence_end

        impact = ImpactAssessor.assess(graph.status, cf_status, original_conf, cf_conf)

        scenario = Scenario(
            scenario_type=ScenarioType.LAYER_REMOVAL,
            target_layer=layer,
            parameter_overrides=None,
            context_overrides=None,
            description=f"Que se passerait-il si la couche '{layer}' n'existait pas?",
        )

        result = self._make_result(
            packet_id, scenario, graph.status, cf_status, cf_conf, original_conf, impact
        )
        self._persist(result)
        return result

    def simulate_with_threshold(
        self, packet_id: str, layer: str, threshold_multiplier: float
    ) -> Optional[CounterfactualResult]:
        graph = self._graph_engine.get_graph(packet_id)
        if not graph:
            return None

        cf_status, cf_conf = PipelineSimulator.simulate_with_threshold(
            graph, layer, threshold_multiplier
        )
        original_conf = graph.metrics.confidence_end

        impact = ImpactAssessor.assess(graph.status, cf_status, original_conf, cf_conf)

        scenario = Scenario(
            scenario_type=ScenarioType.THRESHOLD_CHANGE,
            target_layer=layer,
            parameter_overrides={"threshold_multiplier": threshold_multiplier},
            context_overrides=None,
            description=f"Seuil de '{layer}' × {threshold_multiplier:.2f}",
        )

        result = self._make_result(
            packet_id, scenario, graph.status, cf_status, cf_conf, original_conf, impact
        )
        self._persist(result)
        return result

    def batch_simulate(
        self, packet_id: str, scenarios: list[Scenario]
    ) -> CounterfactualBatch:
        results = []
        for scenario in scenarios[:100]:  # limite de sécurité
            if (
                scenario.scenario_type == ScenarioType.LAYER_REMOVAL
                and scenario.target_layer
            ):
                r = self.simulate_without_layer(packet_id, scenario.target_layer)
            elif scenario.scenario_type == ScenarioType.THRESHOLD_CHANGE:
                multiplier = (scenario.parameter_overrides or {}).get(
                    "threshold_multiplier", 1.0
                )
                r = self.simulate_with_threshold(
                    packet_id, scenario.target_layer or "", multiplier
                )
            else:
                r = None
            if r:
                results.append(r)

        outcome_changed = sum(1 for r in results if r.impact.outcome_changed)
        avg_conf_delta = (
            sum(r.confidence_delta for r in results) / len(results) if results else 0.0
        )

        return CounterfactualBatch(
            batch_id=str(uuid.uuid4()),
            packet_id=packet_id,
            results=tuple(results),
            total_scenarios=len(results),
            outcome_changed_count=outcome_changed,
            avg_confidence_delta=avg_conf_delta,
        )

    def get_layer_sensitivity(
        self, layer: str, symbol: str, hours: int = 168
    ) -> SensitivityReport:
        start_us = now_us() - hours * 3_600_000_000
        rows = self._store.get_decisions(symbol=symbol, start_us=start_us, limit=5_000)
        total = len(rows)
        approvals_with = sum(1 for r in rows if r.get("status") == "APPROVED")
        approvals_without = 0

        for r in rows:
            if r.get("graph_json"):
                graph = self._graph_engine._deserialize(r["graph_json"])
                if graph:
                    cf_status, _ = PipelineSimulator.simulate_without_layer(
                        graph, layer
                    )
                    if cf_status == DecisionStatus.APPROVED:
                        approvals_without += 1

        sensitivity = abs(approvals_without - approvals_with) / max(total, 1)

        if sensitivity > 0.3:
            rec = f"La couche '{layer}' a un impact élevé sur les approbations ({sensitivity:.0%}). Surveiller attentivement."
        elif sensitivity > 0.1:
            rec = f"La couche '{layer}' a un impact modéré. Calibration possible après N≥500 trades."
        else:
            rec = f"La couche '{layer}' a un impact faible sur les décisions pour {symbol}."

        return SensitivityReport(
            layer=layer,
            symbol=symbol,
            period_hours=hours,
            total_decisions=total,
            approvals_without_layer=approvals_without,
            approvals_with_layer=approvals_with,
            sensitivity_score=round(sensitivity, 4),
            recommendation=rec,
        )

    def _make_result(
        self,
        packet_id: str,
        scenario: Scenario,
        original_status: DecisionStatus,
        cf_status: DecisionStatus,
        cf_conf: float,
        original_conf: float,
        impact: ImpactAssessment,
    ) -> CounterfactualResult:
        conf_delta = cf_conf - original_conf
        return CounterfactualResult(
            counterfactual_id=f"cf_{uuid.uuid4().hex[:8]}",
            packet_id=packet_id,
            scenario=scenario,
            original_status=original_status,
            counterfactual_status=cf_status,
            confidence_delta=round(conf_delta, 4),
            impact=impact,
            confidence=min(0.85, 0.70 + abs(conf_delta) * 0.2),
            disclaimer=_DISCLAIMER,
            created_at_us=now_us(),
        )

    def _persist(self, result: CounterfactualResult) -> None:
        try:
            self._store.insert_counterfactual(
                {
                    "cf_id": result.counterfactual_id,
                    "packet_id": result.packet_id,
                    "scenario_type": result.scenario.scenario_type.value,
                    "target_layer": result.scenario.target_layer,
                    "original_result": result.original_status.value,
                    "counterfactual_result": result.counterfactual_status.value,
                    "outcome_changed": int(result.impact.outcome_changed),
                    "confidence_delta": result.confidence_delta,
                    "estimated_pnl_impact": result.impact.estimated_pnl_impact,
                    "confidence": result.confidence,
                    "created_at_us": result.created_at_us,
                }
            )
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[CounterfactualEngine] = None
_engine_lock = threading.Lock()


def get_counterfactual_engine() -> CounterfactualEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = CounterfactualEngine()
    return _engine
