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
already anticipated it.

METRIC-SEMANTICS FIX (this reconciliation pass): `decision_feedback_enabled`,
`is_decision_active` and `recommendation_equals_applied` are three distinct
concepts and must never be computed as functions of one another:
  - `decision_feedback_enabled` is AUTHORITY/PERMISSION state only — it
    reflects `adaptive_decision_feedback_enabled()` and answers "is an
    application path currently authorized", nothing more. It is never used
    to infer whether any specific recommendation was applied.
  - `is_decision_active` is EFFECTIVE APPLICATION / DECISION INFLUENCE for
    the observation window represented — did this subsystem actually
    influence the effective decision. The flag being true only *permits*
    that; it does not *prove* it (no proof a recommendation existed,
    survived remaining conditions, was selected, changed effective state,
    or was logged as applied). Absent a dedicated per-event counter in the
    protected modules, this field stays UNKNOWN/FUTURE_PROVIDER regardless
    of the flag's runtime value — it must NEVER be defined as
    `is_decision_active == decision_feedback_enabled`.
  - `recommendation_equals_applied` is a STRUCTURAL property of these five
    gated adaptive subsystems (mistake_memory, strategy_memory, meta_learner,
    strategy_ranker, system_controller_adaptive), not a per-event runtime
    equality check: PRE-S02 the recommendation *was* the applied value on
    the same code path (recommendation_equals_applied was structurally
    true); POST-S02 the architecture explicitly separates recommendation
    from application via `FEATURE_ADAPTIVE_DECISION_FEEDBACK` gating the
    latter only. That separation existing at all is what this field
    reports, so it is a fixed, structural `False` for every one of these
    five subsystems, independent of whether the flag currently reads true
    or false — flipping the flag toggles *application*, not the
    *architectural fact that recommendation and application are now two
    distinct steps*. It must NEVER be computed as
    `recommendation_equals_applied == decision_feedback_enabled` or as any
    other function of the flag's runtime truthiness.

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

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from observability.operator.contracts import (
    DomainSnapshot,
    FreshnessStatus,
    ObservedValue,
)
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class SubsystemLearningState:
    subsystem_id: str  # e.g. "mistake_memory", "strategy_memory", "meta_learner"
    is_observation_active: ObservedValue
    is_learning_active: ObservedValue
    is_decision_active: ObservedValue  # distinct from the two above — this subsystem gates/shapes live trades today
    recommendation_count: ObservedValue
    applied_count: ObservedValue
    recommendation_equals_applied: ObservedValue  # bool — structural property; False post-S02 for gated adaptive subsystems, independent of decision_feedback_enabled's runtime value
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
    source_version: str | None = None,
    evidence: Mapping[str, object] | None = None,
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
        metric_id="adaptive_learning.decision_feedback_enabled",
        domain="adaptive_learning",
        operator_label_fr="Rétroaction décisionnelle adaptative autorisée",
        technical_name="config.feature_flags.adaptive_decision_feedback_enabled()",
        definition_fr="AUTORITÉ/PERMISSION uniquement : indique si config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK (défaut False, fail-closed) est effectivement actif pour ce process. Ne prouve rien sur une recommandation en particulier — ce n'est pas une preuve d'application, seulement l'autorisation qu'un chemin d'application existe. Ne jamais utiliser cette valeur pour déduire is_decision_active ou recommendation_equals_applied.",
        unit="boolean",
        value_type="boolean",
        freshness_source="process config, re-résolu à chaque appel (jamais mis en cache) — AVAILABLE",
        expected_cadence="static per process lifetime unless .env changes",
        polarity="not_applicable",
        evidence_source="config/feature_flags.py:64-86 (FEATURE_ADAPTIVE_DECISION_FEEDBACK, adaptive_decision_feedback_enabled()) — lecture seule, aucune modification",
        presentation_priority="primary",
        null_semantics="NOT_DEFINED — le flag est toujours lisible, cette métrique n'a pas de cas UNKNOWN",
        warning_semantics="true hors fenêtre de stabilisation autorisée (voir CLAUDE.md) doit être signalé à l'opérateur",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.is_decision_active",
        domain="adaptive_learning",
        operator_label_fr="Sous-système décisionnel-actif",
        technical_name="mistake_memory.check_before_trade(count_as_applied_block=FEATURE_ADAPTIVE_DECISION_FEEDBACK) / meta_learner.find_best()+learn() / strategy_memory.load_by_regime(record_usage=FEATURE_ADAPTIVE_DECISION_FEEDBACK)",
        definition_fr="EFFECTIVE APPLICATION / INFLUENCE DÉCISIONNELLE : indique si ce sous-système a réellement influencé la décision effective pour l'observation représentée — pas simplement si le flag l'y autorise. decision_feedback_enabled=true autorise un chemin d'application ; il ne prouve pas qu'une recommandation a existé, a survécu aux conditions restantes, a été sélectionnée, a changé l'état effectif, ou a été journalée comme appliquée. En l'absence de preuve par-événement dans les modules protégés, cette valeur reste UNKNOWN/FUTURE_PROVIDER — jamais déduite comme is_decision_active == decision_feedback_enabled.",
        unit="boolean",
        value_type="boolean",
        freshness_source="FUTURE_PROVIDER — nécessite une preuve par-événement (pas seulement la lecture du flag) au moment de la décision, non encore exposée par un compteur dédié",
        expected_cadence="FUTURE_PROVIDER",
        polarity="not_applicable",
        evidence_source="core/advisor_loop.py:77-79,687-691 (résolution du flag), :1497,1526,1745-1763,1839,1976,2061-2067,3985-3990,4422-4427,4718-4750 (points de gate) — lecture seule, aucune modification ; tracker_system/autonomous/auto_decision_engine.py:19-23 (_PASSIVE_GATED_ACTIONS)",
        presentation_priority="primary",
        null_semantics="UNKNOWN tant qu'aucun compteur dédié n'expose une preuve d'application par-événement — S02_PROVENANCE_DEBT. NE PAS combler ce UNKNOWN en substituant la valeur de decision_feedback_enabled : enabled != used.",
        warning_semantics="true alors que decision_feedback_enabled=false doit être signalé à l'opérateur comme incohérence à investiguer immédiatement (le flag est la seule autorité d'application POST-S02B.1, donc cette combinaison ne devrait structurellement jamais survenir)",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.recommendation_equals_applied",
        domain="adaptive_learning",
        operator_label_fr="Recommandation = Action appliquée",
        technical_name="S02B1_STRUCTURAL_SPLIT — propriété structurelle, pas une égalité runtime avec le flag",
        definition_fr="PROPRIÉTÉ STRUCTURELLE des cinq sous-systèmes adaptatifs gated (mistake_memory, strategy_memory, meta_learner, strategy_ranker, system_controller_adaptive), pas une vérification d'égalité par événement. PRE-S02B.1, la valeur retournée par ces sous-systèmes ÉTAIT la valeur appliquée (même chemin de code) : recommendation_equals_applied était structurellement vrai. POST-S02B.1, la recommandation (would_match_count, find_best(), best_sharpe(), load_by_regime) reste toujours calculée, mais son application est désormais un pas distinct gouverné par FEATURE_ADAPTIVE_DECISION_FEEDBACK. C'est cette séparation architecturale — le fait qu'elle existe, indépendamment de la valeur courante du flag — que ce champ rapporte : recommendation_equals_applied=False de façon fixe pour ces cinq sous-systèmes, que le flag lise true ou false. NE JAMAIS calculer cette valeur comme recommendation_equals_applied == decision_feedback_enabled ni comme une fonction quelconque de la vérité runtime du flag.",
        unit="boolean",
        value_type="boolean",
        freshness_source="AVAILABLE — propriété structurelle du code actuel, ne varie pas avec le flag ni dans le temps",
        expected_cadence="n/a — structurel, pas un compteur temporel",
        polarity="lower_is_better",
        evidence_source="config/feature_flags.py:64-86 (FEATURE_ADAPTIVE_DECISION_FEEDBACK, adaptive_decision_feedback_enabled()) ; quant_hedge_ai/agents/intelligence/mistake_memory.py:198-245 (count_as_applied_block, would_match_count/trigger_count désormais distincts) ; quant_hedge_ai/ai_evolution/strategy_memory.py:80-112 (record_usage)",
        presentation_priority="primary",
        null_semantics="NOT_DEFINED — la propriété structurelle est toujours déterminable (False pour ces cinq sous-systèmes), pas de cas UNKNOWN",
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
    MetricDefinition(
        metric_id="adaptive_learning.applied_count",
        domain="adaptive_learning",
        operator_label_fr="Nombre d'actions appliquées",
        technical_name="trigger_count (mistake_memory) — pas d'agrégat sous-système confirmé pour les autres sous-systèmes",
        definition_fr="Nombre de recommandations effectivement appliquées à une décision live sur la fenêtre observée (distinct de recommendation_count, jamais inféré depuis decision_feedback_enabled). mistake_memory.BlockRule.trigger_count existe par règle mais aucune méthode n'agrège encore ce compteur au niveau du sous-système entier ; aucun compteur équivalent confirmé pour strategy_memory/meta_learner/strategy_ranker/system_controller_adaptive au-delà de leurs points de gate individuels.",
        unit="count",
        value_type="count",
        freshness_source="FUTURE_PROVIDER — S02_PROVENANCE_DEBT : agrégat sous-système non encore exposé",
        expected_cadence="FUTURE_PROVIDER",
        polarity="not_applicable",
        evidence_source="quant_hedge_ai/agents/intelligence/mistake_memory.py:88,234 (BlockRule.trigger_count, par règle, pas de somme exposée)",
        presentation_priority="diagnostic",
        null_semantics="UNKNOWN",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.memory_state_provenance",
        domain="adaptive_learning",
        operator_label_fr="Provenance de l'état mémoire",
        technical_name="<subsystem>.state_provenance()",
        definition_fr="Objet {subsystem, source_path, state_mtime, compteurs volumétriques} exposé par chacun des cinq sous-systèmes adaptatifs, permettant de distinguer une recommandation produite depuis l'état mémoire X d'une autre produite depuis l'état Y. Ne remplace pas un versioning complet par recommandation (S02_PROVENANCE_DEBT) — c'est une provenance de l'état mémoire agrégé, pas une preuve d'application par-événement (ne pas confondre avec is_decision_active).",
        unit="object",
        value_type="enum",
        freshness_source="state_mtime dans la valeur elle-même — AVAILABLE (méthode state_provenance() confirmée présente sur les cinq modules protégés)",
        expected_cadence="on demand",
        polarity="not_applicable",
        evidence_source="quant_hedge_ai/agents/intelligence/mistake_memory.py:608 ; quant_hedge_ai/ai_evolution/strategy_memory.py:138 ; quant_hedge_ai/ai_evolution/strategy_ranker.py:292 ; tracker_system/meta_learner.py:156 ; tracker_system/meta_memory.py:62 — lecture seule, aucune modification",
        presentation_priority="diagnostic",
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
