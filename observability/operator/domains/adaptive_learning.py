"""ADAPTIVE LEARNING STATE — mission §14. Interface only — designed to
consume S-02 semantics later, does not depend on unmerged S-02 work and
does not touch the protected S-02B.1 files
(quant_hedge_ai/agents/intelligence/mistake_memory.py,
quant_hedge_ai/ai_evolution/strategy_memory.py,
tracker_system/meta_learner.py, tracker_system/meta_memory.py).

Critical forensic finding this domain must carry, not paper over:
MistakeMemory.check_before_trade() and MetaLearner.find_best()/learn()
are DECISION-ACTIVE in core/advisor_loop.py today (they gate/shape live
trades), independent of any feature flag — ADR-0007's FEATURE_AUTO_
CALIBRATION / FEATURE_REGRET_DECISION_FEEDBACK gate the regret-threshold
auto-calibration path only, not these three components. RECOMMENDED vs
APPLIED is not distinguished anywhere for them (the recommendation *is*
the applied value, same code path). This is an architectural fact to
surface to the operator and to S-02B.1, not something O-01 fixes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, ObservedValue
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class SubsystemLearningState:
    subsystem_id: str  # e.g. "mistake_memory", "strategy_memory", "meta_learner"
    is_observation_active: ObservedValue
    is_learning_active: ObservedValue
    is_decision_active: ObservedValue  # distinct from the two above — this subsystem gates/shapes live trades today
    recommendation_count: ObservedValue
    applied_count: ObservedValue
    recommendation_equals_applied: ObservedValue  # bool — true where no RECOMMENDED/APPLIED split exists yet
    decision_feedback_enabled: ObservedValue
    memory_state_provenance: ObservedValue
    last_update_utc: ObservedValue


@dataclass(frozen=True)
class AdaptiveLearningStateSnapshot(DomainSnapshot):
    subsystems: Mapping[str, SubsystemLearningState] = None


def compose_adaptive_learning_state_snapshot(
    *,
    observed_at_utc: datetime,
    subsystems: Mapping[str, SubsystemLearningState],
    freshness: FreshnessStatus,
    status: str,
    source: str = "S02_DEPENDENCY — interface only, no protected-file coupling",
    source_version: str = None,
    evidence: Mapping[str, object] = None,
) -> AdaptiveLearningStateSnapshot:
    return AdaptiveLearningStateSnapshot(
        domain="adaptive_learning",
        observed_at_utc=observed_at_utc,
        source=source,
        source_version=source_version,
        freshness=freshness,
        status=status,
        evidence=evidence or {},
        subsystems=dict(subsystems),
    )


METRICS = (
    MetricDefinition(
        metric_id="adaptive_learning.is_decision_active",
        domain="adaptive_learning",
        operator_label_fr="Sous-système décisionnel-actif",
        technical_name="mistake_memory.check_before_trade() / meta_learner.find_best()+learn() (lecture forensique)",
        definition_fr="Indique si ce sous-système d'apprentissage adaptatif influence déjà une décision de trading en temps réel (par opposition à une simple observation/recommandation passive).",
        unit="boolean",
        value_type="boolean",
        freshness_source="FUTURE_PROVIDER — nécessite instrumentation dans les fichiers protégés S-02B.1",
        expected_cadence="FUTURE_PROVIDER",
        polarity="not_applicable",
        evidence_source="core/advisor_loop.py:1642-1670 (mistake_memory), :1404-1418,4690-4729 (meta_learner) — lecture seule, aucune modification",
        presentation_priority="primary",
        null_semantics="UNKNOWN tant qu'aucun champ dédié n'existe dans les modules protégés — cette valeur est aujourd'hui déduite forensiquement, pas lue depuis un champ observable",
        warning_semantics="true pour un sous-système sans flag de gouvernance explicite doit être signalé à l'opérateur comme écart potentiel à ADR-0007",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.recommendation_equals_applied",
        domain="adaptive_learning",
        operator_label_fr="Recommandation = Action appliquée",
        technical_name="S02_DEPENDENCY",
        definition_fr="Distinction RECOMMENDED vs APPLIED. Aujourd'hui absente pour mistake_memory/strategy_memory/meta_learner: la valeur retournée par le sous-système EST la valeur appliquée, sur le même chemin de code — pas de journal contrefactuel séparé.",
        unit="boolean",
        value_type="boolean",
        freshness_source="FUTURE_PROVIDER",
        expected_cadence="FUTURE_PROVIDER",
        polarity="not_applicable",
        evidence_source="core/advisor_loop.py:1408-1418,1669-1670 — confirmé par lecture forensique, non instrumenté",
        presentation_priority="primary",
        null_semantics="UNKNOWN — nécessite un champ dédié dans les modules protégés (S02_DEPENDENCY)",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.recommendation_count",
        domain="adaptive_learning",
        operator_label_fr="Nombre de recommandations",
        technical_name="S02_DEPENDENCY",
        definition_fr="Nombre de recommandations produites par le sous-système sur la fenêtre observée.",
        unit="count",
        value_type="count",
        freshness_source="FUTURE_PROVIDER",
        expected_cadence="FUTURE_PROVIDER",
        polarity="not_applicable",
        evidence_source="Aucun compteur persistant confirmé pour mistake_memory/strategy_memory/meta_learner au-delà de stats()/summary() ponctuels",
        presentation_priority="diagnostic",
        null_semantics="UNKNOWN",
    ),
)

MODULES = (
    ModuleDescriptor(
        module_id="adaptive_learning.mistake_memory",
        domain="adaptive_learning",
        purpose="Blocage de trade basé sur des règles apprises d'erreurs passées",
        canonical_source="quant_hedge_ai/agents/intelligence/mistake_memory.py (fichier protégé S-02B.1, lecture seule)",
        status="BLOCKED",
        consumers=("core/advisor_loop.py:1642-1670 (_cb_mistake_memory circuit breaker)",),
        freshness_source="databases mistake_memory.jsonl ts field",
        dependencies=(),
        known_debt="Décisionnel-actif dès aujourd'hui (bloque des trades), sans flag de gouvernance explicite type FEATURE_AUTO_CALIBRATION; stats()/explain_last_mistakes() sont la seule surface observable actuelle, pas de is_learning_active/recommendation_count/applied_count.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.strategy_memory",
        domain="adaptive_learning",
        purpose="Sélection/blacklist de stratégies par régime",
        canonical_source="quant_hedge_ai/ai_evolution/strategy_memory.py (fichier protégé S-02B.1, lecture seule)",
        status="BLOCKED",
        consumers=("core/advisor_loop.py:4157 (load_by_regime, décisionnel — classe/sélectionne les stratégies candidates)",),
        freshness_source="databases/ai_evolution/strategy_memory.json mtime",
        dependencies=(),
        known_debt="Aucune méthode stats()/summary(); un observateur externe doit lire le JSON brut. Décisionnel-actif (mute usage_count et influence la sélection).",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.meta_learner",
        domain="adaptive_learning",
        purpose="Sélection de paramètres de sortie (exit_type/tp/sl) par contexte appris",
        canonical_source="tracker_system/meta_learner.py + tracker_system/meta_memory.py (fichiers protégés S-02B.1, lecture seule)",
        status="BLOCKED",
        consumers=("core/advisor_loop.py:1404-1418 (find_best, décisionnel), :4690-4729 (learn, tous les 5 trades)",),
        freshness_source="dernière entrée meta_memory",
        dependencies=(),
        known_debt="find_best() est appliqué directement comme paramètre de sortie live — aucune séparation recommandation/application. summary()/len() sont la seule surface observable.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.regret_decision_feedback_precedent",
        domain="adaptive_learning",
        purpose="Seul précédent de gouvernance double opt-in pour un chemin d'apprentissage adaptatif",
        canonical_source="config/feature_flags.py::FEATURE_AUTO_CALIBRATION, FEATURE_REGRET_DECISION_FEEDBACK (fichier protégé, lecture seule)",
        status="CANONICAL_EXISTING",
        consumers=("RegretEngine.get_threshold_delta() -> GlobalRiskGate.apply_regret_delta()",),
        freshness_source="process config",
        dependencies=(),
        known_debt="Scope d'ADR-0007 confirmé restreint à ce chemin unique — ne couvre pas mistake_memory/strategy_memory/meta_learner malgré leur nature également adaptative.",
    ),
)
