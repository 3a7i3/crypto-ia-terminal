"""DISK / I-O — mission §15. Uses DA-01 (scripts/claude-disk-attribution.py)
as the scientific reference architecture.

One snapshot shows allocation. Two comparable snapshots (matching
catalog_sha256/schema_version, per disk_growth pack) show growth — this
module never claims historical growth attribution from a single
snapshot. Both DA-01 and the disk_growth sibling pack are on-demand,
workflow_dispatch-triggered forensic audits today, not continuous
monitors; the only continuously-active disk check in the repository
(observation/market_observer.py::free_disk_gb()) is a private write-guard
for one writer, not a reported operator metric — a real gap this module
documents rather than silently fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, ObservedValue
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class StorageBucket:
    name: str
    allocated_bytes: int
    logical_bytes: int
    regular_file_count: int


@dataclass(frozen=True)
class DiskIOSnapshot(DomainSnapshot):
    total_bytes: ObservedValue = None
    used_bytes: ObservedValue = None
    free_bytes: ObservedValue = None
    utilization_pct: ObservedValue = None
    attributed_bytes: ObservedValue = None
    residual_bytes: ObservedValue = None  # used_bytes - sum(bucket.allocated_bytes); UNKNOWN without a fresh DA-01 pack
    buckets: Sequence[StorageBucket] = ()
    last_attribution_snapshot_utc: ObservedValue = None
    growth_comparable: ObservedValue = None  # bool — true only if two snapshots share catalog_sha256/schema_version


def compose_disk_io_snapshot(
    *,
    observed_at_utc: datetime,
    total_bytes: ObservedValue,
    used_bytes: ObservedValue,
    free_bytes: ObservedValue,
    utilization_pct: ObservedValue,
    attributed_bytes: ObservedValue,
    residual_bytes: ObservedValue,
    buckets: Sequence[StorageBucket],
    last_attribution_snapshot_utc: ObservedValue,
    growth_comparable: ObservedValue,
    freshness: FreshnessStatus,
    status: str,
    source: str = "scripts/claude-disk-attribution.py (DA-01)",
    source_version: str = None,
    evidence: Mapping[str, object] = None,
) -> DiskIOSnapshot:
    return DiskIOSnapshot(
        domain="disk_io",
        observed_at_utc=observed_at_utc,
        source=source,
        source_version=source_version,
        freshness=freshness,
        status=status,
        evidence=evidence or {},
        total_bytes=total_bytes,
        used_bytes=used_bytes,
        free_bytes=free_bytes,
        utilization_pct=utilization_pct,
        attributed_bytes=attributed_bytes,
        residual_bytes=residual_bytes,
        buckets=tuple(buckets),
        last_attribution_snapshot_utc=last_attribution_snapshot_utc,
        growth_comparable=growth_comparable,
    )


METRICS = (
    MetricDefinition(
        metric_id="disk_io.utilization_pct",
        domain="disk_io",
        operator_label_fr="Utilisation disque",
        technical_name="DA-01 filesystem_observation().used_basis_points",
        definition_fr="Pourcentage d'espace utilisé sur le système de fichiers racine, tel qu'observé lors du dernier audit DA-01.",
        unit="pct",
        value_type="percentage",
        numerator="used_bytes",
        denominator="total_bytes",
        freshness_source="dernier run DA-01 (workflow_dispatch manuel, non planifié)",
        expected_cadence="on-demand only",
        polarity="lower_is_better",
        evidence_source="scripts/claude-disk-attribution.py:43-60",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="disk_io.residual_bytes",
        domain="disk_io",
        operator_label_fr="Octets résiduels non attribués",
        technical_name="filesystem used delta - somme(bucket allocated deltas)",
        definition_fr="Croissance non attribuée à un bucket connu (blocs de répertoire, métadonnées fs, fichiers supprimés mais ouverts). Un résiduel important ne doit jamais être silencieusement assigné à l'application.",
        unit="bytes",
        value_type="bytes",
        freshness_source="nécessite deux snapshots DA-01 comparables (catalog_sha256/schema_version identiques)",
        expected_cadence="on-demand only",
        polarity="lower_is_better",
        evidence_source="docs/runbooks/DISK_ATTRIBUTION_AUDIT_PACK.md:41-49",
        presentation_priority="secondary",
        null_semantics="UNKNOWN avec un seul snapshot — la croissance ne peut jamais être déduite d'un unique relevé",
    ),
    MetricDefinition(
        metric_id="disk_io.market_observer_write_guard",
        domain="disk_io",
        operator_label_fr="Garde d'espace disque (écriture pouls marché)",
        technical_name="observation.market_observer.free_disk_gb()",
        definition_fr="Vérification d'espace libre avant chaque écriture de tick de marché; l'écriture est sautée si l'espace libre est sous OBS_MIN_FREE_DISK_GB. Garde privée d'un seul writer, pas une métrique disque opérateur générale.",
        unit="gb",
        value_type="bytes",
        freshness_source="checked at each write attempt",
        expected_cadence="continuous (per market_observer tick)",
        polarity="higher_is_better",
        evidence_source="observation/market_observer.py:86-90,204-215",
        presentation_priority="diagnostic",
    ),
)

MODULES = (
    ModuleDescriptor(
        module_id="disk_io.da01_attribution",
        domain="disk_io",
        purpose="Pack d'attribution disque en lecture seule, déclenché manuellement",
        canonical_source="scripts/claude-disk-attribution.py",
        status="CANONICAL_EXISTING",
        consumers=("audit_results/da01-first-attribution.json", ".github/workflows/vps-audit.yml"),
        freshness_source="self, on workflow_dispatch",
        dependencies=(),
        known_debt="On-demand uniquement, jamais planifié — pas de continuité entre deux audits.",
    ),
    ModuleDescriptor(
        module_id="disk_io.disk_growth_pack",
        domain="disk_io",
        purpose="Baseline immuable pour dériver la croissance de databases/ et logs/ entre deux snapshots",
        canonical_source="scripts/claude-disk-growth.py",
        status="CANONICAL_EXISTING",
        consumers=(".github/workflows/vps-audit.yml",),
        freshness_source="self, on workflow_dispatch",
        dependencies=(),
        known_debt="growth_computed toujours false au niveau du pack — la croissance doit être dérivée en diffant deux enveloppes hors du pack lui-même.",
    ),
    ModuleDescriptor(
        module_id="disk_io.system_snapshot_gap",
        domain="disk_io",
        purpose="Champ d'utilisation disque dans le snapshot opérateur continu",
        canonical_source="FUTURE_PROVIDER — observability.system_snapshot.SystemSnapshot / observability.metrics_collector.MetricsSnapshot ne portent aucun champ disque",
        status="FUTURE_PROVIDER",
        consumers=(),
        freshness_source="n/a",
        dependencies=("disk_io.da01_attribution",),
        known_debt="Écart identifié par la passe forensique: aucune structure opérateur continue ne porte de champ disque; seul market_observer.free_disk_gb() vérifie l'espace, en garde privée non rapportée.",
    ),
)
