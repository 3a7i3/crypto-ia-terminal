"""ATTRITION / REJECTIONS (Attrition / Refus) — mission §9.

Answers "where are candidates disappearing?" Every rate here is a
PercentageMetric with an explicit numerator/denominator label — never a
bare percentage. RejectionStore only persists actionable signals where
trade_allowed=False and side in (BUY,SELL,LONG,SHORT); HOLD/non-
actionable signals are never counted as rejections
(observability/rejection_store.py:292-308). This means any rate whose
denominator is "rejection records" is scoped to actionable-but-refused
candidates, not to all signals evaluated — activity_tracker's
execution_ratio is the one metric in the repo denominated over all
signals (executed + refused).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, PercentageMetric
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class AttritionSnapshot(DomainSnapshot):
    by_layer_breakdown: Mapping[str, int] = None  # blocker name -> count of rejection records
    dominant_blocker: str = None
    rejection_rate_over_rejections: PercentageMetric = None  # rejections-only denominator
    execution_ratio: PercentageMetric = None  # signals-wide denominator (executed vs refused)


def compose_attrition_snapshot(
    *,
    observed_at_utc: datetime,
    by_layer_breakdown: Mapping[str, int],
    dominant_blocker: str,
    rejection_rate_over_rejections: PercentageMetric,
    execution_ratio: PercentageMetric,
    freshness: FreshnessStatus,
    status: str,
    source: str = "observability.rejection_store.RejectionStore + quant_hedge_ai.agents.intelligence.activity_tracker",
    source_version: str = None,
    evidence: Mapping[str, object] = None,
) -> AttritionSnapshot:
    return AttritionSnapshot(
        domain="attrition",
        observed_at_utc=observed_at_utc,
        source=source,
        source_version=source_version,
        freshness=freshness,
        status=status,
        evidence=evidence or {},
        by_layer_breakdown=dict(by_layer_breakdown),
        dominant_blocker=dominant_blocker,
        rejection_rate_over_rejections=rejection_rate_over_rejections,
        execution_ratio=execution_ratio,
    )


METRICS = (
    MetricDefinition(
        metric_id="attrition.by_layer_pct",
        domain="attrition",
        operator_label_fr="Répartition des refus par couche",
        technical_name="DecisionTraceService.statistics().by_layer_pct",
        definition_fr="Part de chaque couche bloqueuse parmi les refus enregistrés dans la fenêtre interrogée.",
        unit="pct",
        value_type="percentage",
        numerator="refus attribués à cette couche",
        denominator="total des enregistrements de refus dans la fenêtre (PAS le total des signaux évalués)",
        freshness_source="RejectionStore JSONL rotation (daily UTC)",
        expected_cadence="on query",
        polarity="not_applicable",
        evidence_source="visualization/decision_trace_service.py:350-374",
        presentation_priority="primary",
        null_semantics="ZERO si RejectionStore contient des enregistrements mais aucun pour la couche; UNAVAILABLE si le store est injoignable",
    ),
    MetricDefinition(
        metric_id="attrition.execution_ratio",
        domain="attrition",
        operator_label_fr="Taux d'exécution",
        technical_name="ActivityTracker.execution_ratio",
        definition_fr="Fraction des signaux évalués qui ont été exécutés (dénominateur = exécutés + refusés, PAS uniquement les refus).",
        unit="pct",
        value_type="percentage",
        numerator="signaux exécutés",
        denominator="signaux exécutés + signaux refusés (cumul cycle)",
        freshness_source="ActivityTracker cycle cadence",
        expected_cadence="per advisor loop cycle",
        polarity="higher_is_better",
        evidence_source="quant_hedge_ai/agents/intelligence/activity_tracker.py:198-200",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="attrition.no_trade_layer_rejection_rate",
        domain="attrition",
        operator_label_fr="Taux de refus — couche no-trade",
        technical_name="no_trade_layer.NoTradeLayer.stats().rejection_rate",
        definition_fr="Ratio refusé/vérifié pour la couche no-trade spécifiquement.",
        unit="pct",
        value_type="percentage",
        numerator="vérifications refusées par la couche no-trade",
        denominator="vérifications totales de la couche no-trade",
        freshness_source="in-process counter, reset on process restart",
        expected_cadence="NOT_CURRENTLY_AVAILABLE — calculé mais jamais lu",
        polarity="lower_is_better",
        evidence_source="quant_hedge_ai/agents/intelligence/no_trade_layer.py:182-191",
        presentation_priority="diagnostic",
        null_semantics="UNAVAILABLE — aucun point d'appel de .stats() trouvé dans le dépôt (code mort du point de vue observabilité)",
    ),
)

MODULES = (
    ModuleDescriptor(
        module_id="attrition.rejection_store",
        domain="attrition",
        purpose="Journal append-only des refus de candidats actionnables",
        canonical_source="observability/rejection_store.py",
        status="CANONICAL_EXISTING",
        consumers=("visualization/decision_trace_service.py", "tools/decision_trace.py", "visualization/api/decision_api.py"),
        freshness_source="daily JSONL rotation, fsync par écriture",
        dependencies=("observability.decision_event_bus",),
        known_debt="Ne persiste que les signaux actionnables refusés (trade_allowed=False, side actionnable) — HOLD exclu; tout dénominateur doit préciser ce périmètre.",
    ),
    ModuleDescriptor(
        module_id="attrition.decision_trace_service",
        domain="attrition",
        purpose="Agrégation en lecture seule des refus (by_layer, by_regime, by_personality)",
        canonical_source="visualization/decision_trace_service.py",
        status="CANONICAL_EXISTING",
        consumers=("tools/decision_trace.py", "visualization/api/decision_api.py"),
        freshness_source="RejectionStore JSONL",
        dependencies=("observability.rejection_store",),
        known_debt="Aucune écriture — présentation pure sur données canoniques.",
    ),
    ModuleDescriptor(
        module_id="attrition.activity_tracker",
        domain="attrition",
        purpose="Ratio exécution/refus au niveau cycle + diagnostic de stagnation",
        canonical_source="quant_hedge_ai/agents/intelligence/activity_tracker.py",
        status="CANONICAL_EXISTING",
        consumers=("chief_officer.py", "system_intel_reporter.py", "Telegram TRADING_STALLED alert"),
        freshness_source="per advisor loop cycle",
        dependencies=(),
        known_debt="Alimenté par une chaîne 'blockers' séparée du pipeline legacy, pas directement dérivée de RejectionStore — deux comptages parallèles à réconcilier.",
    ),
    ModuleDescriptor(
        module_id="attrition.no_trade_layer_stats_unused",
        domain="attrition",
        purpose="Compteur checked/rejected dédié à la couche no-trade",
        canonical_source="quant_hedge_ai/agents/intelligence/no_trade_layer.py",
        status="UNUSED",
        consumers=(),
        freshness_source="n/a",
        dependencies=(),
        known_debt="Calcul correct et non ambigu (rejection_rate) mais .stats() n'a aucun point d'appel dans le dépôt.",
    ),
    ModuleDescriptor(
        module_id="attrition.gate_rejections_csv",
        domain="attrition",
        purpose="Second compteur indépendant, basé fichier, de chaque vérification du risk gate (pass et fail)",
        canonical_source="quant_hedge_ai/agents/risk/global_risk_gate.py::_gate_csv_log()",
        status="DUPLICATED",
        consumers=("databases/gate_rejections.csv (offline analysis)",),
        freshness_source="per gate check",
        dependencies=(),
        known_debt="Existe en parallèle de RejectionStore/metrics_bus decision_packet.rejected_by.* — trois comptages du même événement de gate à réconcilier avant de choisir une source canonique unique.",
    ),
)
