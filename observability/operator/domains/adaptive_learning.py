"""ADAPTIVE LEARNING STATE — mission §14. Interface only — read-only,
does not touch the protected S-02B.1 files (mistake_memory.py,
strategy_memory.py, strategy_ranker.py, meta_learner.py, meta_memory.py,
tracker_system/autonomous/auto_decision_engine.py, config/feature_flags.py,
core/advisor_loop.py).

PRE-S-02 FINDING (O-01 forensic inventory, 2026-09-03): MistakeMemory.
check_before_trade() and MetaLearner.find_best()/learn() were found to be
decision-active in core/advisor_loop.py without any FEATURE_* governance
flag — ADR-0007's FEATURE_AUTO_CALIBRATION/FEATURE_REGRET_DECISION_FEEDBACK
gated only the Regret-threshold auto-calibration path. RECOMMENDED vs
APPLIED was not distinguished anywhere for these subsystems.

POST-S-02 CURRENT STATE (remediated by S-02B.1, PR #111, merged into main
at commit b5054c8bbdc4ba743baa855060b90e1a9a224e86): a single master flag,
``config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK`` (default
``False``, fail-closed, re-read live via
``adaptive_decision_feedback_enabled()`` — never cached), now gates the
*application* of every adaptive-learning recommendation to a live
decision, across six call sites independently verified by re-reading the
post-merge code (not by trusting the S-02B.1 PR description):

- ``MistakeMemory.check_before_trade()`` — a match always increments the
  rule's ``would_match_count`` (counterfactual); it only also increments
  ``trigger_count`` (applied veto) when the caller passes
  ``count_as_applied_block=FEATURE_ADAPTIVE_DECISION_FEEDBACK``
  (core/advisor_loop.py:1745,1757). The actual trade-continuation gate,
  ``_mm_ok`` (core/advisor_loop.py:2064-2069), is unconditionally true
  whenever the flag is false — a MistakeMemory match can no longer by
  itself fail ``trade_allowed``.
- ``MetaLearner.find_best()`` — always called and always produces a
  recommendation; ``resolve_meta_learner_exit_params()``
  (core/advisor_loop.py:136-159) only lets that recommendation reach the
  live TP/SL/trailing params when the flag is true, and returns an
  explicit ``applied: bool`` so recommendation and application are no
  longer the same value on the same code path.
- ``StrategyMemoryStore.load_by_regime(..., record_usage=...)`` — passive
  reads (``record_usage=FEATURE_ADAPTIVE_DECISION_FEEDBACK``,
  core/advisor_loop.py:1514) never mutate ``usage_count``, and the read
  Sharpe never reaches ``memory_sharpe`` (personality/score selection)
  when passive — logged instead as an explicit "recommandation
  contrefactuelle (mode passif, non appliquée)".
- ``StrategyRanker.best_sharpe()`` — identical gating pattern
  (core/advisor_loop.py:1495-1511): reaches ``memory_sharpe`` only when
  the flag is true.
- ``StrategyRanker`` → ``CapitalAllocationEngine`` sizing —
  ``capital_engine.stats_from_ranker(...)`` only reaches
  ``order_size_usd`` when the flag is true; passive mode falls back to
  the engine's pre-existing neutral defaults, zero behavioral change
  (core/advisor_loop.py:1833-1848).
- ``SystemController``/``ActionExecutor`` — ``ADJUST_TP``/``ADJUST_SL``/
  ``APPLY_META`` are gated (``_PASSIVE_GATED_ACTIONS``,
  tracker_system/autonomous/auto_decision_engine.py:23,271-352): a
  passive decision is still generated and logged ("recommended, not
  applied") but never mutates ``self.config``, and ``executed=False`` is
  returned. ``STOP_TRADING``/``RESUME_TRADING``/``REDUCE_RISK`` are
  **not** in that gated set — they always mutate config and the state
  machine regardless of the flag. ``APPLY_META`` is additionally
  independently confirmed unreachable today:
  ``core/advisor_loop.py:4672`` guards the call with
  ``hasattr(meta_learner, "suggest")``, and no ``suggest()`` method exists
  anywhere on ``MetaLearner`` — so ``meta_suggestion`` is always ``None``
  and the ``if meta_suggestion:`` branch that would emit an
  ``APPLY_META`` decision never fires. Gated anyway, correct-by-design.

**SAFETY AUTHORITY != ADAPTIVE AUTHORITY.** ``STOP_TRADING``/
``RESUME_TRADING``/``REDUCE_RISK`` are risk/recovery authority and are
never described as passive learning by this domain, regardless of the
adaptive-decision-feedback flag's value.

**Regret is a separate constitutional domain**, governed by its own
``FEATURE_REGRET_DECISION_FEEDBACK``/``FEATURE_AUTO_CALIBRATION`` pair —
never collapsed with ``FEATURE_ADAPTIVE_DECISION_FEEDBACK`` here.

Known, recorded debt this domain preserves rather than redesigns
(S-02B.1's own terms, not O-01's):

- ``S02_PROVENANCE_DEBT`` — every gated subsystem now exposes a
  ``state_provenance()`` method (``{subsystem, source_path, state_mtime,
  <volumetric counts>}``) sufficient to distinguish "recommendation
  produced from memory state X vs. state Y", but no deeper
  per-recommendation versioning exists yet.
- ``S02_SYSTEMCONTROLLER_GUARD_ORDER_DEBT`` — documented verbatim on
  ``AutoDecisionOrchestrator.run_decision_cycle()``:
  decide -> validate -> execute runs before
  ``core/advisor_loop.py``'s own ``_SC_MIN_CONFIDENCE``/cooldown guards
  are evaluated, so those guards are not true pre-guards for
  ``ActionExecutor``-internal effects. No longer a live adaptive-authority
  bypass now that the three adaptive actions are passive by default; left
  for a dedicated forensic mission, execution order unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, ObservedValue
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class SubsystemLearningState:
    subsystem_id: str  # e.g. "mistake_memory", "strategy_memory", "meta_learner", "strategy_ranker", "system_controller_safety", "system_controller_adaptive"
    is_observation_active: ObservedValue
    is_learning_active: ObservedValue
    is_decision_active: ObservedValue  # whether this subsystem's output currently reaches a live decision
    recommendation_count: ObservedValue
    applied_count: ObservedValue
    recommendation_equals_applied: ObservedValue  # bool — false wherever S-02B.1's recommendation/application split exists
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
    source: str = "config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK + per-subsystem state_provenance()",
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
        metric_id="adaptive_learning.decision_feedback_enabled",
        domain="adaptive_learning",
        operator_label_fr="Rétroaction décisionnelle adaptative",
        technical_name="config.feature_flags.adaptive_decision_feedback_enabled()",
        definition_fr="Flag maître (S-02B.1, LEARNING != AUTHORITY) : tant que false (défaut, fail-closed), MistakeMemory/MetaLearner/StrategyMemoryStore/StrategyRanker/SystemController-adaptatif restent des recommandations contrefactuelles jamais appliquées à une décision live. Distinct de FEATURE_REGRET_DECISION_FEEDBACK (domaine constitutionnel séparé).",
        unit="boolean",
        value_type="boolean",
        freshness_source="process config, re-résolu à chaque appel (jamais mis en cache)",
        expected_cadence="static per process lifetime unless .env changes",
        polarity="not_applicable",
        evidence_source="config/feature_flags.py:56-86 (lecture seule, fichier protégé S-02B.1)",
        presentation_priority="primary",
        critical_semantics="true hors fenêtre de stabilisation autorisée doit être signalé à l'opérateur",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.is_decision_active",
        domain="adaptive_learning",
        operator_label_fr="Sous-système décisionnel-actif",
        technical_name="six points de contrôle gated identiquement par FEATURE_ADAPTIVE_DECISION_FEEDBACK",
        definition_fr="Indique si ce sous-système d'apprentissage adaptatif influence actuellement une décision de trading en temps réel. Vaut exactement decision_feedback_enabled pour les cinq sous-systèmes adaptatifs (mistake_memory, meta_learner, strategy_memory, strategy_ranker, system_controller_adaptive) ; vaut toujours vrai pour system_controller_safety (autorité de sécurité, non gated).",
        unit="boolean",
        value_type="boolean",
        freshness_source="dérivé de adaptive_learning.decision_feedback_enabled",
        expected_cadence="per advisor loop cycle",
        polarity="not_applicable",
        evidence_source="core/advisor_loop.py:2064-2069 (mistake_memory), :152 (meta_learner), :1497-1527 (strategy_memory/strategy_ranker), :1839 (CAE sizing); tracker_system/autonomous/auto_decision_engine.py:23,271-274 (system_controller)",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.recommendation_equals_applied",
        domain="adaptive_learning",
        operator_label_fr="Recommandation = Action appliquée",
        technical_name="S-02B.1 recommendation/application split",
        definition_fr="PRE-S-02 : vrai pour mistake_memory/meta_learner (même valeur, même chemin de code, aucune séparation). POST-S-02 (remédié par S-02B.1) : faux pour les six points de contrôle gated — chacun distingue désormais explicitement une recommandation contrefactuelle (would_match_count, applied=False, log 'recommandation contrefactuelle') d'une application réelle.",
        unit="boolean",
        value_type="boolean",
        freshness_source="static structural property of the current codebase",
        expected_cadence="n/a — structural, not time-varying",
        polarity="lower_is_better",
        evidence_source="quant_hedge_ai/agents/intelligence/mistake_memory.py:229-254 (would_match_count vs trigger_count); core/advisor_loop.py:136-159 (resolve_meta_learner_exit_params returns applied); tracker_system/autonomous/auto_decision_engine.py:260-360 (executed = not passive)",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.recommendation_count",
        domain="adaptive_learning",
        operator_label_fr="Nombre de recommandations",
        technical_name="per-rule/per-call counters, no subsystem-level aggregate",
        definition_fr="Nombre de recommandations (contrefactuelles ou appliquées) produites par le sous-système. Des compteurs existent au niveau de la règle (BlockRule.would_match_count pour mistake_memory) ou par appel (le applied bool retourné par resolve_meta_learner_exit_params), mais aucune méthode n'agrège encore ces compteurs au niveau du sous-système entier.",
        unit="count",
        value_type="count",
        freshness_source="PARTIAL — voir definition_fr",
        expected_cadence="FUTURE_PROVIDER pour l'agrégat sous-système ; AVAILABLE au niveau règle/appel",
        polarity="not_applicable",
        evidence_source="quant_hedge_ai/agents/intelligence/mistake_memory.py:88-91 (BlockRule.would_match_count, par règle, pas de somme exposée)",
        presentation_priority="diagnostic",
        null_semantics="UNKNOWN au niveau agrégat sous-système ; PRESENT au niveau règle individuelle",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.applied_count",
        domain="adaptive_learning",
        operator_label_fr="Nombre d'actions appliquées",
        technical_name="per-rule/per-call counters, no subsystem-level aggregate",
        definition_fr="Nombre de recommandations effectivement appliquées à une décision live. Même limite que recommendation_count : BlockRule.trigger_count existe par règle, aucun agrégat sous-système.",
        unit="count",
        value_type="count",
        freshness_source="PARTIAL — voir definition_fr",
        expected_cadence="FUTURE_PROVIDER pour l'agrégat sous-système ; AVAILABLE au niveau règle/appel",
        polarity="not_applicable",
        evidence_source="quant_hedge_ai/agents/intelligence/mistake_memory.py:88 (BlockRule.trigger_count)",
        presentation_priority="diagnostic",
        null_semantics="UNKNOWN au niveau agrégat sous-système ; PRESENT au niveau règle individuelle",
    ),
    MetricDefinition(
        metric_id="adaptive_learning.memory_state_provenance",
        domain="adaptive_learning",
        operator_label_fr="Provenance de l'état mémoire",
        technical_name="<subsystem>.state_provenance()",
        definition_fr="{subsystem, source_path, state_mtime, compteurs volumétriques} — permet de distinguer une recommandation produite depuis l'état mémoire X d'une autre produite depuis l'état Y. Ne remplace pas un versioning complet par recommandation (S02_PROVENANCE_DEBT).",
        unit="object",
        value_type="enum",
        freshness_source="state_mtime dans la valeur elle-même",
        expected_cadence="on demand",
        polarity="not_applicable",
        evidence_source="mistake_memory.py:608-627, strategy_memory.py:138-154, strategy_ranker.py:292-303, meta_learner.py:156-158, meta_memory.py:62",
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
        consumers=("core/advisor_loop.py:1730-1782 (_cb_mistake_memory circuit breaker), :2064-2069 (_mm_ok gate)",),
        freshness_source="databases mistake_memory.jsonl ts field; state_provenance().state_mtime",
        dependencies=("config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        known_debt="PRE-S-02 : décisionnel-actif sans flag de gouvernance (finding original O-01, remédié par S-02B.1/PR #111). POST-S-02 : véto réellement appliqué gated par FEATURE_ADAPTIVE_DECISION_FEEDBACK (_mm_ok, advisor_loop.py:2064-2069) ; would_match_count/trigger_count distinguent recommandation et application par règle ; state_provenance() disponible. Reste : pas d'agrégat recommendation_count/applied_count au niveau sous-système (S02_PROVENANCE_DEBT).",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.strategy_memory",
        domain="adaptive_learning",
        purpose="Sélection de stratégies par régime (usage_count, ranking, blacklist)",
        canonical_source="quant_hedge_ai/ai_evolution/strategy_memory.py (fichier protégé S-02B.1, lecture seule)",
        status="PARTIAL",
        consumers=("core/advisor_loop.py:1512-1527 (load_by_regime, record_usage=FEATURE_ADAPTIVE_DECISION_FEEDBACK)",),
        freshness_source="databases/ai_evolution/strategy_memory.json mtime; state_provenance()",
        dependencies=("config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        known_debt="PRE-S-02 : mutait usage_count et influençait la sélection sans garde (finding original O-01, remédié par S-02B.1/PR #111). POST-S-02 : record_usage et l'atteinte de memory_sharpe sont tous deux gated par le même flag — une lecture passive n'écrit ni n'influence plus rien ; state_provenance() disponible. Toujours pas de stats()/summary() — lecture JSON brute nécessaire pour un état agrégé.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.strategy_ranker",
        domain="adaptive_learning",
        purpose="Classement de stratégies par Sharpe (best_sharpe) + statistiques de sizing pour CapitalAllocationEngine",
        canonical_source="quant_hedge_ai/ai_evolution/strategy_ranker.py (fichier protégé S-02B.1, lecture seule)",
        status="PARTIAL",
        consumers=("core/advisor_loop.py:1495-1511 (best_sharpe -> memory_sharpe), :1834-1848 (stats_from_ranker -> capital_engine.allocate)",),
        freshness_source="state_provenance().state_mtime",
        dependencies=("config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        known_debt="Non couvert par l'inventaire O-01 original (ajouté lors de l'intégration POST-S-02). best_sharpe() et stats_from_ranker() gated identiquement par FEATURE_ADAPTIVE_DECISION_FEEDBACK ; record_trade() (écriture) reste séparé, non gated par ce flag. Divergence pos_manager/MexcSim déjà documentée dans portfolio_state.portfolio_brain_duplicated fait que ranker.record_trade() n'est parfois jamais atteint pour certains trades — gap distinct, non lié au flag adaptatif.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.meta_learner",
        domain="adaptive_learning",
        purpose="Sélection de paramètres de sortie (tp/sl/trailing) par contexte appris",
        canonical_source="tracker_system/meta_learner.py + tracker_system/meta_memory.py (fichiers protégés S-02B.1, lecture seule)",
        status="PARTIAL",
        consumers=("core/advisor_loop.py:1457 (find_best, toujours appelé), :3989 (resolve_meta_learner_exit_params), :4897 (learn, tous les 5 trades, toujours actif)",),
        freshness_source="dernière entrée meta_memory; state_provenance()",
        dependencies=("config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        known_debt="PRE-S-02 : find_best() appliqué directement comme paramètre de sortie live, aucune séparation recommandation/application (finding original O-01, remédié par S-02B.1/PR #111). POST-S-02 : resolve_meta_learner_exit_params() retourne applied=bool explicite ; passif -> repli sur les valeurs de personnalité, comportement legacy inchangé. Apprentissage (learn()) reste toujours actif, indépendant du flag. summary()/len() restent la seule surface de synthèse lisible par un humain.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.system_controller_safety",
        domain="adaptive_learning",
        purpose="STOP_TRADING / RESUME_TRADING / REDUCE_RISK — autorité de sécurité/récupération/risque",
        canonical_source="tracker_system/autonomous/auto_decision_engine.py::ActionExecutor.execute() (fichier protégé S-02B.1, lecture seule)",
        status="CANONICAL_EXISTING",
        consumers=("core/advisor_loop.py::_sc_run_cycle",),
        freshness_source="per decision cycle",
        dependencies=(),
        known_debt="SAFETY AUTHORITY, jamais gated par FEATURE_ADAPTIVE_DECISION_FEEDBACK (auto_decision_engine.py:20-23, 311-333) — ne jamais décrire ces trois actions comme de l'apprentissage passif. Sujet à S02_SYSTEMCONTROLLER_GUARD_ORDER_DEBT (voir system_controller_adaptive ci-dessous) : les gardes _SC_MIN_CONFIDENCE/cooldown d'advisor_loop.py s'évaluent après, pas avant, les effets internes d'ActionExecutor.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.system_controller_adaptive",
        domain="adaptive_learning",
        purpose="ADJUST_TP / ADJUST_SL / APPLY_META — optimisation adaptative/méta-apprentissage",
        canonical_source="tracker_system/autonomous/auto_decision_engine.py::ActionExecutor.execute(), AutoDecisionOrchestrator.run_decision_cycle() (fichier protégé S-02B.1, lecture seule)",
        status="PARTIAL",
        consumers=("core/advisor_loop.py::_sc_run_cycle",),
        freshness_source="per decision cycle; logs/system_controller_decisions.jsonl",
        dependencies=("config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK",),
        known_debt="ADAPTIVE AUTHORITY, gated (_PASSIVE_GATED_ACTIONS, auto_decision_engine.py:23,271-274) : passif -> decision générée et journalisée ('recommended, not applied') mais self.config non muté, executed=False. APPLY_META de surcroît confirmé inatteignable aujourd'hui : meta_learner.suggest() n'existe pas, hasattr()-gardé dans advisor_loop.py:4672-4675, meta_suggestion toujours None. S02_SYSTEMCONTROLLER_GUARD_ORDER_DEBT (documenté verbatim sur run_decision_cycle()) : decide->validate->execute s'exécute avant les gardes _SC_MIN_CONFIDENCE/cooldown d'advisor_loop.py — non bloquant depuis que ces trois actions sont passives par défaut, non redesigné ici.",
    ),
    ModuleDescriptor(
        module_id="adaptive_learning.regret_decision_feedback_precedent",
        domain="adaptive_learning",
        purpose="Précédent de gouvernance double opt-in pour le domaine Regret — constitutionnellement distinct de l'apprentissage adaptatif",
        canonical_source="config/feature_flags.py::FEATURE_AUTO_CALIBRATION, FEATURE_REGRET_DECISION_FEEDBACK (fichier protégé, lecture seule)",
        status="CANONICAL_EXISTING",
        consumers=("RegretEngine.get_threshold_delta() -> GlobalRiskGate.apply_regret_delta()",),
        freshness_source="process config",
        dependencies=(),
        known_debt="Scope confirmé restreint à ce chemin Regret unique — jamais collapsé avec FEATURE_ADAPTIVE_DECISION_FEEDBACK (S-02B.1), qui gouverne mistake_memory/meta_learner/strategy_memory/strategy_ranker/system_controller-adaptatif séparément. Les deux domaines partagent le même principe constitutionnel (LEARNING != AUTHORITY) mais restent deux flags indépendants.",
    ),
)
