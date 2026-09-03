"""SYSTEM HEALTH (Santé système) — mission §6.

Distinguishes BOOT HEALTH (process alive — watchdog_vps.py pgrep,
HealthSnapshot booleans in observability/system_snapshot.py) from
SCIENTIFIC HEALTH (the composite score in observability/health_score.py,
derived from MetricsSnapshot). A process being alive does not imply the
scientific data it produces is valid.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, ObservedValue
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class SystemHealthSnapshot(DomainSnapshot):
    boot_alive: ObservedValue = None  # bool — process-liveness tier
    health_score: ObservedValue = None  # float 0-100 — scientific-health tier
    health_level: ObservedValue = None  # str: PERFECT|HEALTHY|DEGRADED|CRITICAL
    exchange_connectivity_healthy: ObservedValue = None  # bool
    exchange_latency_ms: ObservedValue = None  # float
    module_statuses: Mapping[str, str] = None  # module_id -> HEALTHY|DEGRADED|UNHEALTHY|UNKNOWN
    degraded_reasons: Sequence[str] = ()


def compose_system_health_snapshot(
    *,
    observed_at_utc: datetime,
    boot_alive: ObservedValue,
    health_score: ObservedValue,
    health_level: ObservedValue,
    exchange_connectivity_healthy: ObservedValue,
    exchange_latency_ms: ObservedValue,
    module_statuses: Mapping[str, str],
    freshness: FreshnessStatus,
    status: str,
    degraded_reasons: Sequence[str] = (),
    source: str = "watchdog_vps.py + observability.health_score + supervision.exchange_monitor",
    source_version: str = None,
    evidence: Mapping[str, object] = None,
) -> SystemHealthSnapshot:
    return SystemHealthSnapshot(
        domain="system_health",
        observed_at_utc=observed_at_utc,
        source=source,
        source_version=source_version,
        freshness=freshness,
        status=status,
        evidence=evidence or {},
        boot_alive=boot_alive,
        health_score=health_score,
        health_level=health_level,
        exchange_connectivity_healthy=exchange_connectivity_healthy,
        exchange_latency_ms=exchange_latency_ms,
        module_statuses=dict(module_statuses),
        degraded_reasons=tuple(degraded_reasons),
    )


METRICS = (
    MetricDefinition(
        metric_id="system_health.boot_alive",
        domain="system_health",
        operator_label_fr="Processus actif",
        technical_name="watchdog_vps.py pgrep(core/advisor_loop.py)",
        definition_fr="Le processus principal du moteur est en cours d'exécution. N'implique pas que les données produites sont scientifiquement valides.",
        unit="boolean",
        value_type="boolean",
        freshness_source="watchdog poll cadence (watchdog_vps.py)",
        expected_cadence="continuous (watchdog loop)",
        polarity="higher_is_better",
        evidence_source="watchdog_vps.py:56-120; scripts/systemd/crypto-watchdog.service",
        presentation_priority="primary",
        null_semantics="UNAVAILABLE si le watchdog lui-même est injoignable",
    ),
    MetricDefinition(
        metric_id="system_health.health_score",
        domain="system_health",
        operator_label_fr="Score de santé scientifique",
        technical_name="observability.health_score.HealthScore.compute()",
        definition_fr="Score composite pondéré (mémoire 25%, fiabilité 25%, connectivité exchange 20%, trading 20%, performance 10%) calculé à partir de MetricsSnapshot.",
        unit="score_0_100",
        value_type="score",
        freshness_source="MetricsSnapshot flush cadence (core/advisor_loop.py:6746-6757)",
        expected_cadence="per advisor loop cycle",
        polarity="higher_is_better",
        evidence_source="observability/health_score.py:52-72; core/advisor_loop.py:6749-6750",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="system_health.exchange_connectivity_healthy",
        domain="system_health",
        operator_label_fr="Connectivité exchange",
        technical_name="supervision.exchange_monitor.ExchangeMonitor.snapshot().healthy",
        definition_fr="L'exchange actif répond aux pings de connectivité du superviseur.",
        unit="boolean",
        value_type="boolean",
        freshness_source="ExchangeMonitor background thread",
        expected_cadence="continuous",
        polarity="higher_is_better",
        evidence_source="supervision/exchange_monitor.py:93-224",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="system_health.exchange_latency_ms",
        domain="system_health",
        operator_label_fr="Latence exchange",
        technical_name="ExchangeMonitor.snapshot().avg_latency_ms",
        definition_fr="Latence moyenne observée sur les appels de connectivité vers l'exchange actif.",
        unit="ms",
        value_type="duration_ms",
        freshness_source="ExchangeMonitor background thread",
        expected_cadence="continuous",
        polarity="lower_is_better",
        evidence_source="supervision/exchange_monitor.py:132-143",
        presentation_priority="secondary",
    ),
)

MODULES = (
    ModuleDescriptor(
        module_id="system_health.module_registry",
        domain="system_health",
        purpose="Registre central de statut par module (HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN)",
        canonical_source="system/module_registry.py",
        status="CANONICAL_EXISTING",
        consumers=("system/kernel.py", "core/advisor_loop.py", "health/health_registry.py"),
        freshness_source="module heartbeat/registration calls",
        dependencies=(),
        known_debt="Aucun contrat unifié BOOT vs SCIENTIFIC health; distinction reste implicite dans le code appelant.",
    ),
    ModuleDescriptor(
        module_id="system_health.health_score",
        domain="system_health",
        purpose="Score composite de santé scientifique",
        canonical_source="observability/health_score.py",
        status="CANONICAL_EXISTING",
        consumers=("core/advisor_loop.py:6749-6750", "system/burn_in.py"),
        freshness_source="MetricsSnapshot cadence",
        dependencies=("observability.metrics_collector.MetricsSnapshot",),
        known_debt="Aucune",
    ),
    ModuleDescriptor(
        module_id="system_health.watchdog_root",
        domain="system_health",
        purpose="Watchdog de survie processus (boot health)",
        canonical_source="watchdog_vps.py",
        status="CANONICAL_EXISTING",
        consumers=("scripts/systemd/crypto-watchdog.service",),
        freshness_source="watchdog poll loop",
        dependencies=(),
        known_debt="Duplication connue: infra/monitoring/watchdog_vps.py existe (implémentation différente, non déployée par systemd) et doit être traitée comme LEGACY.",
    ),
    ModuleDescriptor(
        module_id="system_health.watchdog_infra_duplicate",
        domain="system_health",
        purpose="Second watchdog non déployé (implémentation concurrente)",
        canonical_source="infra/monitoring/watchdog_vps.py",
        status="DUPLICATED",
        consumers=("tests/test_stability_accelerated.py",),
        freshness_source="n/a — non déployé",
        dependencies=(),
        known_debt="Non référencé par aucun fichier systemd; seul le watchdog racine est déployé. Ne pas traiter comme source canonique.",
    ),
    ModuleDescriptor(
        module_id="system_health.health_registry_unused",
        domain="system_health",
        purpose="Runner générique de health checks par module",
        canonical_source="health/health_registry.py",
        status="UNUSED",
        consumers=(),
        freshness_source="n/a",
        dependencies=(),
        known_debt="Bien conçu mais zéro point d'import en dehors du fichier lui-même; jamais câblé au kernel ou à advisor_loop. Candidat à réactivation plutôt qu'à reconstruction.",
    ),
    ModuleDescriptor(
        module_id="system_health.recovery_manager_unused",
        domain="system_health",
        purpose="Stratégies de recovery automatique sur changement de statut module",
        canonical_source="health/recovery_manager.py",
        status="UNUSED",
        consumers=(),
        freshness_source="n/a",
        dependencies=("system.module_registry",),
        known_debt="S'enregistre sur module_registry.on_status_change() à l'import, mais n'est lui-même jamais importé ailleurs — l'enregistrement ne s'exécute donc jamais en pratique.",
    ),
    ModuleDescriptor(
        module_id="system_health.system_snapshot_bus_dead",
        domain="system_health",
        purpose="Bus d'événements pour SystemSnapshot",
        canonical_source="observability/system_snapshot_event_bus.py",
        status="PARTIAL",
        consumers=(),
        freshness_source="publish() appelé à chaque cycle notify",
        dependencies=("observability.system_snapshot",),
        known_debt="publish() est appelé (core/advisor_loop.py:7030,7613) mais aucun .subscribe() externe n'existe dans le dépôt — publication sans consommateur.",
    ),
    ModuleDescriptor(
        module_id="system_health.daily_analyzer_snapshot_collision",
        domain="system_health",
        purpose="Second SystemSnapshot (vocabulaire GREEN/YELLOW/RED) sans lien avec le runtime live",
        canonical_source="infra/monitoring/daily_analyzer.py",
        status="LEGACY",
        consumers=("core/bootstrap_integration.py", "scripts/final_validation.py"),
        freshness_source="n/a",
        dependencies=(),
        known_debt="Collision de nom avec observability.system_snapshot.SystemSnapshot (le seul canonique pour le runtime live); non câblé à advisor_loop.py ni à un service systemd.",
    ),
)
