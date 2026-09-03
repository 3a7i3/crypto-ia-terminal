"""DATA FRESHNESS (Fraîcheur des données) — mission §12.

No canonical FRESH/DEGRADED/STALE/UNKNOWN vocabulary existed anywhere in
the codebase before this mission (confirmed by forensic search — the
only precedents were narrow and domain-scoped: IncidentType.DATA_STALE
in pieuvre/incidents/models.py, AdmissionBlocker.REJECTED_STALE in
paper_trading/admission_types.py, and the regret pipeline's "canonical
horizon" freshness concept in tools/regret_repository.py, which is about
canonical-vs-recent, not fresh-vs-stale). This module's
FreshnessStatus/classify_freshness (see contracts.py, freshness.py) is
the first general-purpose formalization; per-source datasets keep
registering their own thresholds here rather than inheriting one global
"snapshot age" (mission §28).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Optional

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, ObservedValue
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class DatasetFreshness:
    dataset_id: str
    source_dataset: str
    source_producer: str
    last_event_utc: ObservedValue
    last_valid_event_utc: ObservedValue
    age_seconds: ObservedValue
    expected_cadence_s: Optional[float]
    freshness_threshold_s: Optional[float]
    stale_threshold_s: Optional[float]
    freshness_status: FreshnessStatus


@dataclass(frozen=True)
class DataFreshnessSnapshot(DomainSnapshot):
    datasets: Mapping[str, DatasetFreshness] = None  # dataset_id -> DatasetFreshness


def compose_data_freshness_snapshot(
    *,
    observed_at_utc: datetime,
    datasets: Mapping[str, DatasetFreshness],
    freshness: FreshnessStatus,
    status: str,
    source: str = "per-dataset canonical producers (regret_repository, market_observer, wallet_sync, ...)",
    source_version: str = None,
    evidence: Mapping[str, object] = None,
) -> DataFreshnessSnapshot:
    return DataFreshnessSnapshot(
        domain="data_freshness",
        observed_at_utc=observed_at_utc,
        source=source,
        source_version=source_version,
        freshness=freshness,
        status=status,
        evidence=evidence or {},
        datasets=dict(datasets),
    )


METRICS = (
    MetricDefinition(
        metric_id="data_freshness.regret_canonical_freshness",
        domain="data_freshness",
        operator_label_fr="Fraîcheur canonique Regret",
        technical_name="tools.regret_repository.freshness()",
        definition_fr="Age du dernier événement HORIZON_EVIDENCE évalué (EVALUATED) sur l'horizon canonique (1h). Distincte de 'dernier événement écrit' — un PENDING/DROPPED récent n'avance jamais cette horloge.",
        unit="seconds",
        value_type="duration_s",
        freshness_source="tools/regret_repository.py:247-310",
        expected_cadence="MAX_STALE_H (env-configured)",
        polarity="lower_is_better",
        evidence_source="tools/regret_repository.py:247-310",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="data_freshness.market_pulse_age",
        domain="data_freshness",
        operator_label_fr="Fraîcheur du pouls marché",
        technical_name="observation.market_observer latest_tick.json mtime",
        definition_fr="Age du dernier tick de marché écrit par le collecteur de pouls découplé.",
        unit="seconds",
        value_type="duration_s",
        freshness_source="crypto-market-observer.timer cadence (15 min)",
        expected_cadence="900s",
        polarity="lower_is_better",
        evidence_source="observation/market_observer.py:252-273",
        presentation_priority="secondary",
    ),
)

MODULES = (
    ModuleDescriptor(
        module_id="data_freshness.regret_repository_freshness",
        domain="data_freshness",
        purpose="Horloge de fraîcheur canonique pour le pipeline Regret v2",
        canonical_source="tools/regret_repository.py",
        status="CANONICAL_EXISTING",
        consumers=("tools/cri_calculator.py",),
        freshness_source="self",
        dependencies=(),
        known_debt="Non exposé via l'API HTTP burnin_api.py aujourd'hui (BurnInSnapshot omet freshness/fresh/validity) — gap identifié par la passe forensique.",
    ),
    ModuleDescriptor(
        module_id="data_freshness.vocabulary_gap",
        domain="data_freshness",
        purpose="Vocabulaire général FRESH/DEGRADED/STALE/UNKNOWN",
        canonical_source="observability/operator/contracts.py::FreshnessStatus (nouveau, O-01)",
        status="CANONICAL_NEW",
        consumers=("all observability/operator/domains/*",),
        freshness_source="n/a — enum",
        dependencies=(),
        known_debt="Premier vocabulaire unifié du dépôt; les précédents (DATA_STALE, REJECTED_STALE, horizon canonique) restent des concepts scopés à leur domaine et ne sont pas rétroactivement migrés par O-01.",
    ),
)
