"""Canonical Operator Observability Architecture (mission O-01).

This package defines passive, deterministic contracts that compose
canonical operator-facing observations out of *already existing*
in-memory objects produced elsewhere in the codebase (system_snapshot,
DecisionObservation, RejectionStore, RegretRepository, DA-01 disk packs,
etc.).

Constitutional constraints (see docs/observability/OPERATOR_OBSERVABILITY_ARCHITECTURE.md):

- Source of truth != presentation layer. Nothing here recalculates a
  canonical metric that already has an owner elsewhere; adapters wrap
  and re-express existing values.
- No network calls, no filesystem writes, no background threads, no
  import-time side effects anywhere in this package.
- Nothing here feeds a trading decision (ADR-0007 passivity).
"""

from observability.operator.contracts import (
    DomainSnapshot,
    FreshnessStatus,
    NullSemantics,
    ObservedValue,
    PercentageMetric,
)
from observability.operator.freshness import classify_freshness
from observability.operator.registry import (
    MetricDefinition,
    MetricRegistry,
    ModuleDescriptor,
    ModuleRegistry,
)

__all__ = [
    "DomainSnapshot",
    "FreshnessStatus",
    "NullSemantics",
    "ObservedValue",
    "PercentageMetric",
    "classify_freshness",
    "MetricDefinition",
    "MetricRegistry",
    "ModuleDescriptor",
    "ModuleRegistry",
]
