"""ADAPTIVE LEARNING STATE — mission §14. Interface only, does not touch
the protected files it describes (quant_hedge_ai/agents/intelligence/
mistake_memory.py, quant_hedge_ai/ai_evolution/strategy_memory.py,
quant_hedge_ai/ai_evolution/strategy_ranker.py, tracker_system/meta_learner.py,
tracker_system/meta_memory.py, config/feature_flags.py, core/advisor_loop.py,
tracker_system/autonomous/auto_decision_engine.py) — reconciled O-01R,
POST-S02B.1 (PR #111).

PRE-S02 FORENSIC FINDING:
Written before S-02B.1 (PR #111) landed, O-01 recorded MistakeMemory.
check_before_trade() and MetaLearner.find_best()/learn() as DECISION-ACTIVE
in core/advisor_loop.py, independent of any feature flag, with no
RECOMMENDED vs APPLIED distinction anywhere (the recommendation *was* the
applied value, same code path) — status="BLOCKED" for every real subsystem
module below, framed as an unresolved architectural gap for S-02B.1 to
close.

REMEDIATED BY:
S-02B.1 / PR #111 — merged into main before O-01 (PR #117), and now the
governing implementation this domain observes.

POST-S02 CURRENT STATE:
`config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK` (default False,
fail-closed on a broken/missing import — see `adaptive_decision_feedback_
enabled()`) is the single master switch that can turn a MistakeMemory /
MetaLearner+MetaMemory / StrategyMemoryStore / StrategyRanker
recommendation into a live effect on a decision. With the flag off (the
permanent default under ADR-0007 absent a signed ADR):
  - MistakeMemory.check_before_trade(count_as_applied_block=...) is called
    by core/advisor_loop.py with `count_as_applied_block=
    FEATURE_ADAPTIVE_DECISION_FEEDBACK` — a match increments
    `would_match_count` (always) but `trigger_count`/the actual block only
    when the flag is true. `would_match_count >= trigger_count` always
    holds; would_match stays observable regardless of the flag.
  - MetaLearner/MetaMemory's find_best()/learn() keep observing and
    learning unconditionally; core/advisor_loop.py only lets a
    recommendation shape a live TP/SL/trailing/exit parameter when the
    flag is true (see advisor_loop.py:1976, 2061-2067, 3985-3990,
    4422-4427).
  - StrategyMemoryStore.load_by_regime(regime, record_usage=...) is called
    with `record_usage=FEATURE_ADAPTIVE_DECISION_FEEDBACK` — a passive
    read no longer mutates usage/application state unless the flag is on.
  - StrategyRanker.best_sharpe() and StrategyRanker's sizing statistics
    continue to observe/rank unconditionally; live memory_sharpe /
    capital-allocation influence is gated the same way.
  - SystemController's ADJUST_TP / ADJUST_SL / APPLY_META are adaptive
    authority: `_PASSIVE_GATED_ACTIONS` in
    tracker_system/autonomous/auto_decision_engine.py gates their
    APPLICATION (not their generation) on the same flag.
  - STOP_TRADING / RESUME_TRADING / REDUCE_RISK are explicitly excluded
    from `_PASSIVE_GATED_ACTIONS` — safety/recovery/risk authority,
    always fully authoritative independent of the adaptive flag. This
    domain must never classify them as adaptive feedback.

RECOMMENDED != APPLIED is now a real, code-enforced distinction for these
subsystems (learning/observation always active; application gated), not
an unresolved gap — this domain's field names below (recommendation_count,
applied_count, recommendation_equals_applied, decision_feedback_enabled)
already anticipated it and are unchanged by this reconciliation.

KNOWN DEBT preserved (not fixed by O-01R, not silently dropped):
  - S02_PROVENANCE_DEBT: FEATURE_ADAPTIVE_DECISION_FEEDBACK plus
    would_match_count/trigger_count and record_usage give minimal
    provenance (was this recommendation applied or only observed), but
    deeper per-recommendation versioning/audit trail (which exact
    recommendation, which config version, at what confidence) remains
    deferred — recommendation_count/applied_count below stay UNKNOWN
    until a dedicated counter surface exists in the protected modules.
  - S02_SYSTEMCONTROLLER_GUARD_ORDER_DEBT: ActionExecutor applies
    SystemController actions internally before core/advisor_loop.py's
    later confidence/cooldown checks run; accepted as non-blocking,
    ordering intentionally left unchanged by this reconciliation.

Regret (FEATURE_REGRET_DECISION_FEEDBACK / FEATURE_AUTO_CALIBRATION,
RegretEngine.get_threshold_delta() -> GlobalRiskGate.apply_regret_delta())
is a separate governance path, out of scope here and untouched.
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
    source: str = "S02B1_GOVERNED — governed by config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK (S-02B.1/PR #111); interface only, no protected-file import coupling",
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
        technical_name="mistake_memory.check_before_trade(count_as_applied_block=FEATURE_ADAPTIVE_DECISION_FEEDBACK) / meta_learner.find_best()+learn() / strategy_memory.load_by_regime(record_usage=FEATURE_ADAPTIVE_DECISION_FEEDBACK)",
        definition_fr="Indique si ce sous-système d'apprentissage adaptatif influence déjà une décision de trading en temps réel (par opposition à une simple observation/recommandation passive). POST-S02B.1 : gouverné par config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK (défaut False, fail-closed) ; apprentissage/observation restent actifs indépendamment du flag.",
        unit="boolean",
        value_type="boolean",
        freshness_source="FUTURE_PROVIDER — nécessite une lecture directe du flag effectif (adaptive_decision_feedback_enabled()) au moment de la décision, non encore exposée par un compteur dédié",
        expected_cadence="FUTURE_PROVIDER",
        polarity="not_applicable",
        evidence_source="core/advisor_loop.py:77-79,687-691 (résolution du flag), :1497,1526,1745-1763,1839,1976,2061-2067,3985-3990,4422-4427,4718-4750 (points de gate) — lecture seule, aucune modification ; tracker_system/autonomous/auto_decision_engine.py:19-23 (_PASSIVE_GATED_ACTIONS)",
        presentation_priority="primary",
        null_semantics="UNKNOWN tant qu'aucun compteur dédié n'expose la valeur effective du flag au moment de chaque décision — S02_PROVENANCE_DEBT",
        warning_semantics="true alors que FEATURE_ADAPTIVE_DECISION_FEEDBACK=false doit être signalé à l'opérateur comme incohérence à investiguer (le flag est la seule autorité d'application POST-S02B.1)",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.recommendation_equals_applied",
        domain="adaptive_learning",
        operator_label_fr="Recommandation = Action appliquée",
        technical_name="FEATURE_ADAPTIVE_DECISION_FEEDBACK",
        definition_fr="Distinction RECOMMENDED vs APPLIED. POST-S02B.1, cette distinction existe réellement en code pour mistake_memory/strategy_memory/meta_learner/strategy_ranker : la recommandation (would_match_count, find_best(), best_sharpe(), load_by_regime) reste toujours calculée, mais son application à une décision live est gouvernée par FEATURE_ADAPTIVE_DECISION_FEEDBACK (défaut False). recommendation_equals_applied=true seulement quand le flag est actif.",
        unit="boolean",
        value_type="boolean",
        freshness_source="FUTURE_PROVIDER — nécessite exposition directe de adaptive_decision_feedback_enabled() comme métrique dédiée",
        expected_cadence="FUTURE_PROVIDER",
        polarity="not_applicable",
        evidence_source="config/feature_flags.py:64-86 (FEATURE_ADAPTIVE_DECISION_FEEDBACK, adaptive_decision_feedback_enabled()) ; quant_hedge_ai/agents/intelligence/mistake_memory.py:198-245 (count_as_applied_block) ; quant_hedge_ai/ai_evolution/strategy_memory.py:80-112 (record_usage)",
        presentation_priority="primary",
        null_semantics="UNKNOWN — S02_PROVENANCE_DEBT : le flag effectif gouverne l'application mais aucun compteur par-recommandation n'existe encore",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.recommendation_count",
        domain="adaptive_learning",
        operator_label_fr="Nombre de recommandations",
        technical_name="would_match_count (mistake_memory) / find_best() calls (meta_learner) / load_by_regime() calls (strategy_memory) / best_sharpe() calls (strategy_ranker)",
        definition_fr="Nombre de recommandations produites par le sous-système sur la fenêtre observée, que le flag d'application soit actif ou non.",
        unit="count",
        value_type="count",
        freshness_source="FUTURE_PROVIDER — S02_PROVENANCE_DEBT : per-recommendation versioning/compteur agrégé non encore exposé",
        expected_cadence="FUTURE_PROVIDER",
        polarity="not_applicable",
        evidence_source="quant_hedge_ai/agents/intelligence/mistake_memory.py:91,232 (would_match_count) — au-delà de ce champ, aucun compteur persistant agrégé confirmé pour strategy_memory/meta_learner/strategy_ranker au-delà de stats()/summary() ponctuels",
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
        status="PARTIAL",
        consumers=("core/advisor_loop.py:1642-1670 (_cb_mistake_memory circuit breaker, count_as_applied_block=FEATURE_ADAPTIVE_DECISION_FEEDBACK)",),
        freshness_source="databases mistake_memory.jsonl ts field",
        dependencies=("config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        known_debt="POST-S02B.1 (PR #111) : apprentissage/observation toujours actifs ; blocage réel d'un trade gouverné par FEATURE_ADAPTIVE_DECISION_FEEDBACK (défaut False, fail-closed) via count_as_applied_block — would_match_count reste observable même flag=false (would_match_count >= trigger_count toujours). S02_PROVENANCE_DEBT : stats()/explain_last_mistakes() restent la seule surface observable, pas de recommendation_count/applied_count agrégés dédiés.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.strategy_memory",
        domain="adaptive_learning",
        purpose="Sélection/blacklist de stratégies par régime",
        canonical_source="quant_hedge_ai/ai_evolution/strategy_memory.py (fichier protégé S-02B.1, lecture seule)",
        status="PARTIAL",
        consumers=("core/advisor_loop.py:4157 (load_by_regime, record_usage=FEATURE_ADAPTIVE_DECISION_FEEDBACK)",),
        freshness_source="databases/ai_evolution/strategy_memory.json mtime",
        dependencies=("config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        known_debt="POST-S02B.1 (PR #111) : load_by_regime() accepte record_usage (S-02B.1) — un appel passif/contrefactuel (recommandation observée mais non appliquée quand FEATURE_ADAPTIVE_DECISION_FEEDBACK=false) ne mute plus usage_count. Aucune méthode stats()/summary() ; un observateur externe doit toujours lire le JSON brut — S02_PROVENANCE_DEBT.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.meta_learner",
        domain="adaptive_learning",
        purpose="Sélection de paramètres de sortie (exit_type/tp/sl) par contexte appris",
        canonical_source="tracker_system/meta_learner.py + tracker_system/meta_memory.py (fichiers protégés S-02B.1, lecture seule)",
        status="PARTIAL",
        consumers=("core/advisor_loop.py:1404-1418,1976,2061-2067,3985-3990 (find_best, gouverné par FEATURE_ADAPTIVE_DECISION_FEEDBACK), :4690-4729,4718-4750 (learn, apprentissage toujours actif ; application loguée séparément si flag=false)",),
        freshness_source="dernière entrée meta_memory",
        dependencies=("config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        known_debt="POST-S02B.1 (PR #111) : find_best() reste toujours calculé/appris (learn() inconditionnel) ; son application comme paramètre de sortie live est gouvernée par FEATURE_ADAPTIVE_DECISION_FEEDBACK. RECOMMENDED != APPLIED désormais réel en code. S02_PROVENANCE_DEBT : summary()/len() restent la seule surface observable agrégée, pas de compteur recommendation_count/applied_count dédié.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.strategy_ranker",
        domain="adaptive_learning",
        purpose="Classement de stratégies par performance (Sharpe) et statistiques de sizing par régime",
        canonical_source="quant_hedge_ai/ai_evolution/strategy_ranker.py (fichier protégé S-02B.1, lecture seule)",
        status="PARTIAL",
        consumers=("core/advisor_loop.py (best_sharpe et statistiques de sizing consommées par le dimensionnement de capital)",),
        freshness_source="dernière mise à jour du ranking par StrategyRanker",
        dependencies=("config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        known_debt="POST-S02B.1 (PR #111) : classement/observation toujours actifs (best_sharpe() et statistiques de sizing calculés inconditionnellement) ; influence live sur memory_sharpe / capital-allocation gouvernée par FEATURE_ADAPTIVE_DECISION_FEEDBACK — même frontière que mistake_memory/strategy_memory/meta_learner. S02_PROVENANCE_DEBT : pas de compteur recommendation_count/applied_count dédié.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.system_controller_adaptive",
        domain="adaptive_learning",
        purpose="Actions d'optimisation adaptative (ADJUST_TP, ADJUST_SL, APPLY_META) — application gouvernée, à distinguer des actions de sécurité",
        canonical_source="tracker_system/autonomous/auto_decision_engine.py (fichier protégé S-02B.1, lecture seule)",
        status="PARTIAL",
        consumers=("AutoDecisionEngine._PASSIVE_GATED_ACTIONS (ADJUST_TP, ADJUST_SL, APPLY_META) — application gouvernée par FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        freshness_source="dernière décision produite par AutoDecisionEngine",
        dependencies=("config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        known_debt="POST-S02B.1 (PR #111) : génération de la décision toujours active ; seule l'APPLICATION est gouvernée par le flag maître (tracker_system/autonomous/auto_decision_engine.py:19-23). S02_SYSTEMCONTROLLER_GUARD_ORDER_DEBT : l'ordre d'application interne d'ActionExecutor précède les vérifications tardives de confiance/cooldown d'advisor_loop.py ; accepté comme non-bloquant, ordre non modifié par O-01R.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.system_controller_safety",
        domain="adaptive_learning",
        purpose="Actions de sécurité/récupération/risque (STOP_TRADING, RESUME_TRADING, REDUCE_RISK) — hors du périmètre de gouvernance adaptative",
        canonical_source="tracker_system/autonomous/auto_decision_engine.py (fichier protégé S-02B.1, lecture seule)",
        status="CANONICAL_EXISTING",
        consumers=("AutoDecisionEngine — STOP_TRADING/RESUME_TRADING/REDUCE_RISK, explicitement hors de _PASSIVE_GATED_ACTIONS",),
        freshness_source="dernière décision produite par AutoDecisionEngine",
        dependencies=(),
        known_debt="Ne PAS classer comme feedback adaptatif : ces actions restent pleinement autoritaires indépendamment de FEATURE_ADAPTIVE_DECISION_FEEDBACK (tracker_system/autonomous/auto_decision_engine.py:19-23, commentaire explicite). Documenté ici uniquement pour clarifier la frontière avec system_controller_adaptive ci-dessus ; aucune dette connue propre à ce périmètre.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.regret_decision_feedback_precedent",
        domain="adaptive_learning",
        purpose="Précédent de gouvernance double opt-in pour un chemin d'apprentissage adaptatif séparé (Regret)",
        canonical_source="config/feature_flags.py::FEATURE_AUTO_CALIBRATION, FEATURE_REGRET_DECISION_FEEDBACK (fichier protégé, lecture seule)",
        status="CANONICAL_EXISTING",
        consumers=("RegretEngine.get_threshold_delta() -> GlobalRiskGate.apply_regret_delta()",),
        freshness_source="process config",
        dependencies=(),
        known_debt="POST-S02B.1 : ce n'est plus le seul chemin gouverné — FEATURE_ADAPTIVE_DECISION_FEEDBACK (S-02B.1) gouverne désormais mistake_memory/strategy_memory/meta_learner/strategy_ranker/system_controller_adaptive séparément. Les deux flags restent des gouvernances distinctes et ne doivent jamais être fusionnées (Regret hors périmètre de cette reconciliation).",
    ),
)
