"""OPERATOR SUMMARY (Synthèse opérateur) — mission §16.

A pure composition layer. It never recalculates a canonical scientific
truth — it only reads the status/freshness fields already present on the
other 10 domain snapshots and maps them into explicit component
statuses plus a short list of "needs attention" items. No opaque global
score: every field here traces back to a named domain's own status.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Mapping, Optional, Sequence

from observability.operator.contracts import DOMAIN_STATUSES, DomainSnapshot, FreshnessStatus, utcnow
from observability.operator.domains.adaptive_learning import AdaptiveLearningStateSnapshot
from observability.operator.domains.attrition import AttritionSnapshot
from observability.operator.domains.data_freshness import DataFreshnessSnapshot
from observability.operator.domains.decision_pipeline import DecisionPipelineSnapshot
from observability.operator.domains.disk_io import DiskIOSnapshot
from observability.operator.domains.execution_state import ExecutionStateSnapshot
from observability.operator.domains.market_state import MarketStateSnapshot
from observability.operator.domains.portfolio_state import PortfolioStateSnapshot
from observability.operator.domains.regret_state import RegretStateSnapshot
from observability.operator.domains.system_health import SystemHealthSnapshot
from observability.operator.registry import ModuleDescriptor


@dataclass(frozen=True)
class ComponentStatus:
    domain: str
    question_fr: str
    status: str  # copied verbatim from the source snapshot's own .status — never recomputed
    freshness: FreshnessStatus  # copied verbatim from the source snapshot's own .freshness
    needs_attention: bool


@dataclass(frozen=True)
class OperatorSummary(DomainSnapshot):
    components: Sequence[ComponentStatus] = ()
    attention_items: Sequence[str] = ()


_QUESTIONS_FR: Mapping[str, str] = {
    "system_health": "La machine est-elle vivante et scientifiquement saine ?",
    "market_state": "Les données de marché sont-elles fraîches ?",
    "decision_pipeline": "Le pipeline décisionnel progresse-t-il ?",
    "attrition": "Où se situe le bloqueur dominant ?",
    "portfolio_state": "Le portefeuille est-il observable ?",
    "execution_state": "L'exécution est-elle saine ?",
    "regret_state": "Regret est-il scientifiquement frais ?",
    "adaptive_learning": "L'apprentissage adaptatif est-il passif ou décisionnel-actif ?",
    "disk_io": "Le stockage est-il sain ?",
    "data_freshness": "Les jeux de données critiques sont-ils frais ?",
}

_DEGRADED_FRESHNESS = frozenset({FreshnessStatus.DEGRADED, FreshnessStatus.STALE, FreshnessStatus.UNKNOWN})

# The only DomainSnapshot.status (contracts.DOMAIN_STATUSES) member that
# means "no attention needed" (mission remediation §5). Because
# DOMAIN_STATUSES is a closed vocabulary enforced by
# DomainSnapshot.__post_init__, this membership check can never silently
# misclassify an unrecognized-but-healthy status string (e.g. a
# hypothetical ACTIVE/NOMINAL) as needing attention — every status a
# domain can legally report is accounted for, which
# test_registry.py::test_healthy_statuses_partition_domain_statuses proves
# exhaustively rather than by convention.
_HEALTHY_STATUSES = frozenset({"OK"})
assert _HEALTHY_STATUSES <= DOMAIN_STATUSES, "_HEALTHY_STATUSES must be drawn from contracts.DOMAIN_STATUSES"

# Freshness aggregation severity, most severe first (mission remediation
# §4). UNKNOWN outranks STALE: not knowing whether a domain is fresh is
# strictly less actionable for an operator than a domain confirmed stale.
# STALE outranks DEGRADED, DEGRADED outranks FRESH. NOT_APPLICABLE is
# deliberately absent — it means "freshness does not apply here" and must
# never contribute a severity, so it is filtered out before this ordering
# is consulted (see _aggregate_freshness).
_FRESHNESS_SEVERITY: Sequence[FreshnessStatus] = (
    FreshnessStatus.UNKNOWN,
    FreshnessStatus.STALE,
    FreshnessStatus.DEGRADED,
    FreshnessStatus.FRESH,
)


def _aggregate_freshness(freshness_values: Sequence[FreshnessStatus]) -> FreshnessStatus:
    """Most-severe-wins aggregation over _FRESHNESS_SEVERITY.

    NOT_APPLICABLE components are filtered out first: mixing one into an
    otherwise-FRESH collection must not degrade it (mission remediation
    §4). If every component is NOT_APPLICABLE — or there are no
    components at all — there is nothing to report freshness on, so the
    aggregate is NOT_APPLICABLE; that is not the same as (and must never
    be invented as) FRESH.
    """
    applicable = [f for f in freshness_values if f != FreshnessStatus.NOT_APPLICABLE]
    if not applicable:
        return FreshnessStatus.NOT_APPLICABLE
    for level in _FRESHNESS_SEVERITY:
        if level in applicable:
            return level
    return FreshnessStatus.UNKNOWN  # unreachable: _FRESHNESS_SEVERITY covers every remaining member


def _component_from_snapshot(domain: str, snapshot: Optional[DomainSnapshot]) -> ComponentStatus:
    if snapshot is None:
        return ComponentStatus(
            domain=domain,
            question_fr=_QUESTIONS_FR[domain],
            status="UNAVAILABLE",
            freshness=FreshnessStatus.UNKNOWN,
            needs_attention=True,
        )
    needs_attention = snapshot.freshness in _DEGRADED_FRESHNESS or snapshot.status not in _HEALTHY_STATUSES
    return ComponentStatus(
        domain=domain,
        question_fr=_QUESTIONS_FR[domain],
        status=snapshot.status,
        freshness=snapshot.freshness,
        needs_attention=needs_attention,
    )


def compose_operator_summary(
    *,
    observed_at_utc: Optional[datetime] = None,
    system_health: Optional[SystemHealthSnapshot] = None,
    market_state: Optional[MarketStateSnapshot] = None,
    decision_pipeline: Optional[DecisionPipelineSnapshot] = None,
    attrition: Optional[AttritionSnapshot] = None,
    portfolio_state: Optional[PortfolioStateSnapshot] = None,
    execution_state: Optional[ExecutionStateSnapshot] = None,
    regret_state: Optional[RegretStateSnapshot] = None,
    adaptive_learning: Optional[AdaptiveLearningStateSnapshot] = None,
    disk_io: Optional[DiskIOSnapshot] = None,
    data_freshness: Optional[DataFreshnessSnapshot] = None,
) -> OperatorSummary:
    """Compose from already-built domain snapshots only. Never mutates or
    recomputes any field on the inputs (mission §31 test requirement)."""
    inputs: Mapping[str, Optional[DomainSnapshot]] = {
        "system_health": system_health,
        "market_state": market_state,
        "decision_pipeline": decision_pipeline,
        "attrition": attrition,
        "portfolio_state": portfolio_state,
        "execution_state": execution_state,
        "regret_state": regret_state,
        "adaptive_learning": adaptive_learning,
        "disk_io": disk_io,
        "data_freshness": data_freshness,
    }
    components: List[ComponentStatus] = [
        _component_from_snapshot(domain, snap) for domain, snap in inputs.items()
    ]
    attention_items = tuple(
        f"{c.domain}: {c.status} (fraîcheur={c.freshness.value})" for c in components if c.needs_attention
    )
    overall_status = "ATTENTION_REQUIRED" if attention_items else "OK"
    overall_freshness = _aggregate_freshness([c.freshness for c in components])
    return OperatorSummary(
        domain="operator_summary",
        observed_at_utc=observed_at_utc or utcnow(),
        source="observability.operator.domains.operator_summary (composition only, no independent computation)",
        source_version=None,
        freshness=overall_freshness,
        status=overall_status,
        evidence={},
        components=tuple(components),
        attention_items=attention_items,
    )


MODULES = (
    ModuleDescriptor(
        module_id="operator_summary.composer",
        domain="operator_summary",
        purpose="Composition pure des 10 domaines en une synthèse opérateur, sans recalcul scientifique indépendant",
        canonical_source="observability/operator/domains/operator_summary.py",
        status="CANONICAL_NEW",
        consumers=("future Telegram/dashboard/API presentation adapters (O-02+)",),
        freshness_source="agrégation par sévérité (UNKNOWN > STALE > DEGRADED > FRESH, NOT_APPLICABLE filtré) des snapshots composés — voir _aggregate_freshness",
        dependencies=("les 10 autres domaines observability.operator",),
        known_debt="Aucun score opaque — chaque champ reste traçable à un domaine nommé et à son propre status/freshness. Vocabulaire de statut fermé (contracts.DOMAIN_STATUSES) : seul OK est considéré sain, sans liste d'exclusion devinée.",
    ),
)
