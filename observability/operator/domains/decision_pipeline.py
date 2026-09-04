"""DECISION PIPELINE (Pipeline décisionnel) — mission §8.

The conceptual chain (MARKET DATA -> UNIVERSE -> FEATURES -> STRATEGIES
-> SIGNALS -> FILTERS -> RISK -> PORTFOLIO -> EXECUTION -> ORDER/FILL/
POSITION) does not map 1:1 onto the live code. The real chain, traced in
core/advisor_loop.py::analyze_symbol(), is:

    AUTHORITY (fail-fast) -> SIGNAL (live_signal_engine)
    -> [DecisionPacket parallel track: enrich]
    -> META-STRATEGY -> RISK GATE (5-condition GlobalRiskGate)
    -> NO-TRADE LAYER -> CONVICTION/AWARENESS -> PORTFOLIO BRAIN
    -> CAPITAL ALLOCATION (CAE) -> MISTAKE MEMORY -> EXECUTIVE OVERRIDE
    -> THREAT RADAR -> ARBITRATOR -> trade_allowed verdict -> EXECUTION

UNIVERSE and FEATURES are not separate stages with dedicated candidate
counters in the current implementation — they happen upstream of
analyze_symbol() without their own telemetry object. Two parallel
tracks currently coexist: the legacy dict pipeline (`blockers`,
`trade_allowed`) that actually drives execution today, and
DecisionPacket/DecisionObservation (ADR-0007's canonical telemetry
contract), instrumented as a comparison/shadow track
(decision_packet_disagreement_rate in core/advisor_loop.py:6274-6295).
This module treats DecisionObservation as canonical for reporting; the
legacy dict remains the actual execution driver until DecisionPacket is
promoted (a decision outside O-01's scope).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, ObservedValue
from observability.operator.registry import MetricDefinition, ModuleDescriptor

PIPELINE_STAGES: Sequence[str] = (
    "authority",
    "signal",
    "meta_strategy",
    "risk_gate",
    "no_trade_layer",
    "conviction_awareness",
    "portfolio_brain",
    "capital_allocation",
    "mistake_memory",
    "executive_override",
    "threat_radar",
    "arbitrator",
    "execution",
)

STAGE_LABELS_FR: Mapping[str, str] = {
    "authority": "Autorité (coupe-circuit)",
    "signal": "Génération de signal",
    "meta_strategy": "Validation méta-stratégie",
    "risk_gate": "Contrôle de risque",
    "no_trade_layer": "Couche no-trade",
    "conviction_awareness": "Conviction / conscience de contexte",
    "portfolio_brain": "Cerveau portefeuille",
    "capital_allocation": "Allocation de capital",
    "mistake_memory": "Mémoire des erreurs",
    "executive_override": "Override exécutif",
    "threat_radar": "Radar de menace",
    "arbitrator": "Arbitrage final",
    "execution": "Exécution",
}


@dataclass(frozen=True)
class StageObservation:
    stage_id: str
    label_fr: str
    status: str  # e.g. "PASSED" | "BLOCKED" | "NOT_REACHED" | "UNKNOWN"
    input_count: ObservedValue
    output_count: ObservedValue
    rejection_count: ObservedValue
    reason: ObservedValue

    def __post_init__(self) -> None:
        if self.stage_id not in PIPELINE_STAGES:
            raise ValueError(f"Unknown pipeline stage id: {self.stage_id!r}")


@dataclass(frozen=True)
class DecisionPipelineSnapshot(DomainSnapshot):
    stages: Sequence[StageObservation] = ()
    trade_allowed: ObservedValue = None  # bool, terminal verdict
    first_blocker: ObservedValue = None  # str


def compose_decision_pipeline_snapshot(
    *,
    observed_at_utc: datetime,
    stages: Sequence[StageObservation],
    trade_allowed: ObservedValue,
    first_blocker: ObservedValue,
    freshness: FreshnessStatus,
    status: str,
    source: str = "observability.decision_observation.DecisionObservation",
    source_version: str = None,
    evidence: Mapping[str, object] = None,
) -> DecisionPipelineSnapshot:
    return DecisionPipelineSnapshot(
        domain="decision_pipeline",
        observed_at_utc=observed_at_utc,
        source=source,
        source_version=source_version,
        freshness=freshness,
        status=status,
        evidence=evidence or {},
        stages=tuple(stages),
        trade_allowed=trade_allowed,
        first_blocker=first_blocker,
    )


METRICS = (
    MetricDefinition(
        metric_id="decision_pipeline.trade_allowed",
        domain="decision_pipeline",
        operator_label_fr="Verdict final",
        technical_name="DecisionObservation.trade_allowed",
        definition_fr="Verdict terminal du pipeline pour ce symbole/cycle: le trade est-il autorisé ?",
        unit="boolean",
        value_type="boolean",
        freshness_source="per-cycle DecisionObservation publication",
        expected_cadence="per advisor loop cycle per symbol",
        polarity="not_applicable",
        evidence_source="observability/decision_observation.py:56-239",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="decision_pipeline.first_blocker",
        domain="decision_pipeline",
        operator_label_fr="Premier bloqueur",
        technical_name="DecisionObservation.first_blocker",
        definition_fr="Première couche du pipeline ayant refusé le trade, dans l'ordre d'évaluation.",
        unit="enum",
        value_type="enum",
        freshness_source="per-cycle DecisionObservation publication",
        expected_cadence="per advisor loop cycle per symbol",
        polarity="not_applicable",
        evidence_source="observability/decision_observation.py",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="decision_pipeline.disagreement_rate",
        domain="decision_pipeline",
        operator_label_fr="Taux de désaccord Packet/Legacy",
        technical_name="advisor_loop._dp_disagreement_count / _dp_compared_count",
        definition_fr="Fraction des décisions où le pipeline DecisionPacket (candidat canonique) diverge du pipeline dict legacy qui pilote encore l'exécution réelle.",
        unit="pct",
        value_type="percentage",
        numerator="décisions où DecisionPacket et le pipeline legacy divergent",
        denominator="décisions comparées dans le cycle",
        freshness_source="advisor loop cycle cadence",
        expected_cadence="per advisor loop cycle",
        polarity="lower_is_better",
        evidence_source="core/advisor_loop.py:6274-6295",
        presentation_priority="diagnostic",
    ),
)

MODULES = (
    ModuleDescriptor(
        module_id="decision_pipeline.decision_observation",
        domain="decision_pipeline",
        purpose="Contrat unifié de télémétrie de décision (ADR-0007)",
        canonical_source="observability/decision_observation.py",
        status="CANONICAL_EXISTING",
        consumers=("DecisionEventBus subscribers: RejectionStore, decision_explainer, RegretScheduler",),
        freshness_source="publication par cycle via DecisionEventBus",
        dependencies=("core.advisor_loop.analyze_symbol (producer of AnalysisResult)",),
        known_debt="Coexiste avec le pipeline dict legacy qui pilote encore réellement l'exécution (core/advisor_loop.py:1488 commentaire).",
    ),
    ModuleDescriptor(
        module_id="decision_pipeline.decision_packet",
        domain="decision_pipeline",
        purpose="Machine à états scellée (hash-chain) pour le cycle de vie d'une décision",
        canonical_source="core/decision_packet.py",
        status="PARTIAL",
        consumers=("governance/decision_trace.py", "observability/decision_observation.py"),
        freshness_source="transitions en temps réel",
        dependencies=(),
        known_debt="Piste candidate/shadow — n'est pas encore le pilote réel de l'exécution; taux de désaccord avec le pipeline legacy suivi mais non résolu.",
    ),
    ModuleDescriptor(
        module_id="decision_pipeline.legacy_dict_pipeline",
        domain="decision_pipeline",
        purpose="Pipeline dict historique (blockers/trade_allowed) — pilote réel de l'exécution",
        canonical_source="core/advisor_loop.py::analyze_symbol()",
        status="CANONICAL_EXISTING",
        consumers=("execution path in core/advisor_loop.py",),
        freshness_source="per cycle",
        dependencies=(),
        known_debt="Pas de compteurs de candidats dédiés pour UNIVERSE/FEATURES; FILTERS et SIGNALS sont fusionnés dans gate/meta/no-trade plutôt que d'être des étapes nommées séparées.",
    ),
    ModuleDescriptor(
        module_id="decision_pipeline.dip_parallel_stack",
        domain="decision_pipeline",
        purpose="Plateforme d'observabilité décisionnelle parallèle (graph causal, timeline, explainability)",
        canonical_source="dip/core/observer.py, dip/modules/*",
        status="PARTIAL",
        consumers=("tools/instrumentation_validator.py", "tools/live_observer_validator.py"),
        freshness_source="n/a — non câblé au pipeline live",
        dependencies=(),
        known_debt="Stack complète et autonome, mais zéro import depuis core/advisor_loop.py ou core/advisor_runtime_adapters.py — ne pas confondre avec observability/*.",
    ),
)
