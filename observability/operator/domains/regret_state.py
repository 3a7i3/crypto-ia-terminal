"""REGRET STATE — mission §13. Consumes the already-certified S-01/v2
architecture (tools/regret_repository.py, observability/regret_scheduler.py);
does not redesign Regret.

Critical semantic rule preserved verbatim from the mission: MISSED_WIN !=
executable missed profit. HORIZON_EVIDENCE malformed/duplicate counters
come from tools/regret_repository.py::diagnostics(); v1 classification is
LEGACY (quant_hedge_ai/agents/intelligence/regret_engine.py, retired
since 2026-07-10 per ADR-0018) and only ever appears as an explicit
fallback path in burnin_api.py, never as a silent substitute for v2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, ObservedValue
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class RegretStateSnapshot(DomainSnapshot):
    v2_active: ObservedValue = None  # bool
    canonical_horizon: ObservedValue = None  # str, e.g. "1h"
    last_event_utc: ObservedValue = None  # datetime — producer liveness only
    last_canonical_evaluated_utc: ObservedValue = None  # datetime — the real freshness clock
    canonical_freshness: FreshnessStatus = FreshnessStatus.UNKNOWN
    pending_candidate_count: ObservedValue = None  # int
    horizon_status_counts: Mapping[str, int] = None  # PENDING/MISSING_PRICE/DROPPED/EVALUATED -> count
    malformed_count: ObservedValue = None  # int
    decision_feedback_enabled: ObservedValue = None  # bool — FEATURE_REGRET_DECISION_FEEDBACK


def compose_regret_state_snapshot(
    *,
    observed_at_utc: datetime,
    v2_active: ObservedValue,
    canonical_horizon: ObservedValue,
    last_event_utc: ObservedValue,
    last_canonical_evaluated_utc: ObservedValue,
    canonical_freshness: FreshnessStatus,
    pending_candidate_count: ObservedValue,
    horizon_status_counts: Mapping[str, int],
    malformed_count: ObservedValue,
    decision_feedback_enabled: ObservedValue,
    status: str,
    source: str = "tools.regret_repository + observability.regret_scheduler (S-01/v2, certified)",
    source_version: str = "regret-v2",
    evidence: Mapping[str, object] = None,
) -> RegretStateSnapshot:
    return RegretStateSnapshot(
        domain="regret_state",
        observed_at_utc=observed_at_utc,
        source=source,
        source_version=source_version,
        freshness=canonical_freshness,
        status=status,
        evidence=evidence or {},
        v2_active=v2_active,
        canonical_horizon=canonical_horizon,
        last_event_utc=last_event_utc,
        last_canonical_evaluated_utc=last_canonical_evaluated_utc,
        canonical_freshness=canonical_freshness,
        pending_candidate_count=pending_candidate_count,
        horizon_status_counts=dict(horizon_status_counts),
        malformed_count=malformed_count,
        decision_feedback_enabled=decision_feedback_enabled,
    )


METRICS = (
    MetricDefinition(
        metric_id="regret_state.canonical_freshness",
        domain="regret_state",
        operator_label_fr="Fraîcheur canonique Regret",
        technical_name="tools.regret_repository.is_fresh()/freshness()",
        definition_fr="Basée strictement sur le dernier événement EVALUATED de l'horizon canonique (1h) — jamais sur le dernier événement écrit, quel que soit son statut.",
        unit="enum",
        value_type="enum",
        freshness_source="tools/regret_repository.py:247-310",
        expected_cadence="MAX_STALE_H",
        polarity="not_applicable",
        evidence_source="tools/regret_repository.py:277-310",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="regret_state.horizon_status_counts",
        domain="regret_state",
        operator_label_fr="Répartition des statuts d'horizon",
        technical_name="tools.regret_repository.diagnostics().horizon_status_counts",
        definition_fr="Comptage par statut d'évidence (PENDING, MISSING_PRICE, DROPPED, EVALUATED) sur l'horizon canonique.",
        unit="count",
        value_type="count",
        freshness_source="regret_horizons_YYYY-MM-DD.jsonl",
        expected_cadence="per RegretScheduler evaluation",
        polarity="not_applicable",
        evidence_source="tools/regret_repository.py:157-204",
        presentation_priority="secondary",
    ),
    MetricDefinition(
        metric_id="regret_state.decision_feedback_enabled",
        domain="regret_state",
        operator_label_fr="Rétroaction décisionnelle Regret",
        technical_name="config.feature_flags.FEATURE_REGRET_DECISION_FEEDBACK",
        definition_fr="Double opt-in constitutionnel (ADR-0007): tant que false, Regret reste strictement passif et n'influence aucune décision de trading.",
        unit="boolean",
        value_type="boolean",
        freshness_source="process config at read time",
        expected_cadence="static per process lifetime",
        polarity="not_applicable",
        evidence_source="config/feature_flags.py (lecture seule, fichier protégé S-02B.1); docs/adr/0007-observabilite-passive-separation.md",
        presentation_priority="primary",
        critical_semantics="true sans ADR signé par l'opérateur constitue une violation d'ADR-0007",
    ),
    MetricDefinition(
        metric_id="regret_state.missed_win_semantic_caveat",
        domain="regret_state",
        operator_label_fr="MISSED_WIN (avertissement scientifique)",
        technical_name="RegretCandidate.regret_type == MISSED_WIN",
        definition_fr="Un mouvement de prix favorable non capturé selon l'évaluation contrefactuelle de l'horizon. NE SIGNIFIE PAS un profit manqué exécutable — aucune garantie de remplissage, de slippage ou de contrainte de risque n'est prise en compte.",
        unit="count",
        value_type="count",
        freshness_source="regret_horizons_YYYY-MM-DD.jsonl",
        expected_cadence="per RegretScheduler evaluation",
        polarity="not_applicable",
        evidence_source="observability/regret_scheduler.py:270-279",
        presentation_priority="primary",
        null_semantics="ZERO (aucun MISSED_WIN sur la fenêtre) différent de UNAVAILABLE (Regret non câblé)",
    ),
)

MODULES = (
    ModuleDescriptor(
        module_id="regret_state.regret_repository",
        domain="regret_state",
        purpose="Couche de lecture canonique du dataset Regret v2 (MC-001/ADR-0018)",
        canonical_source="tools/regret_repository.py",
        status="CANONICAL_EXISTING",
        consumers=("tools/cri_calculator.py", "visualization/api/regret_api.py", "visualization/api/burnin_api.py"),
        freshness_source="self (last_canonical_evaluated_ts)",
        dependencies=("databases/regret/regret_horizons_*.jsonl",),
        known_debt="Aucune pour la sémantique elle-même.",
    ),
    ModuleDescriptor(
        module_id="regret_state.regret_scheduler",
        domain="regret_state",
        purpose="Producteur des évidences HORIZON_EVIDENCE",
        canonical_source="observability/regret_scheduler.py",
        status="CANONICAL_EXISTING",
        consumers=("tools/regret_repository.py",),
        freshness_source="self",
        dependencies=(),
        known_debt="layer_performance()/stats() implémentés correctement mais aucun point d'appel externe trouvé (UNUSED du point de vue observabilité, bien que le producteur HORIZON_EVIDENCE lui-même soit actif).",
    ),
    ModuleDescriptor(
        module_id="regret_state.burnin_api_gap",
        domain="regret_state",
        purpose="Exposition HTTP de l'état Regret à l'opérateur",
        canonical_source="visualization/api/burnin_api.py::BurnInSnapshot",
        status="PARTIAL",
        consumers=("sdos_terminal/api/app.py GET /api/burnin",),
        freshness_source="tools.regret_repository (non propagé)",
        dependencies=("regret_state.regret_repository",),
        known_debt="N'inclut pas freshness/fresh/last_canonical_evaluated_utc/canonical_horizon/validity/pending_candidate_count — ces champs existent seulement côté CLI (tools/cri_calculator.py), pas dans l'API HTTP consommée par le futur O-02.",
    ),
    ModuleDescriptor(
        module_id="regret_state.v1_legacy",
        domain="regret_state",
        purpose="Ancien moteur Regret (pré-v2)",
        canonical_source="quant_hedge_ai/agents/intelligence/regret_engine.py",
        status="LEGACY",
        consumers=("visualization/api/burnin_api.py (fallback explicite, jamais silencieux)",),
        freshness_source="n/a",
        dependencies=(),
        known_debt="Retiré de la certification depuis 2026-07-10 (ADR-0018); conservé pour l'audit historique uniquement.",
    ),
)
