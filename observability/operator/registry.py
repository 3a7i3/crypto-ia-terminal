"""Metric and module registries.

These are the programmatic, tested counterpart to
docs/observability/METRIC_DICTIONARY.md and
docs/observability/OBSERVABILITY_MODULE_REGISTRY.md. The markdown files
are the complete, human-curated catalogues (they may describe metrics
that are not yet worth encoding, e.g. FUTURE_PROVIDER ones); this module
holds the subset that ships as a live, uniqueness-checked, French-label-
checked registry so presentation adapters can look metrics up by id
instead of re-deriving definitions (mission §18, §26, §32).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from observability.operator.contracts import DOMAIN_IDS

_NOT_DEFINED = "NOT_DEFINED"


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    domain: str
    operator_label_fr: str
    technical_name: str
    definition_fr: str
    unit: str
    value_type: str  # "count" | "percentage" | "duration_s" | "bytes" | "boolean" | "enum" | "currency_usd"
    freshness_source: str
    expected_cadence: str
    polarity: str  # "higher_is_better" | "lower_is_better" | "neutral" | "not_applicable"
    evidence_source: str
    presentation_priority: str  # "primary" | "secondary" | "diagnostic"
    numerator: Optional[str] = None
    denominator: Optional[str] = None
    null_semantics: str = _NOT_DEFINED
    warning_semantics: str = _NOT_DEFINED
    critical_semantics: str = _NOT_DEFINED

    def __post_init__(self) -> None:
        if self.domain not in DOMAIN_IDS:
            raise ValueError(f"{self.metric_id}: unknown domain {self.domain!r}")
        if not self.operator_label_fr.strip():
            raise ValueError(f"{self.metric_id}: operator_label_fr is required")
        if self.value_type == "percentage" and (not self.numerator or not self.denominator):
            raise ValueError(
                f"{self.metric_id}: percentage metrics require explicit "
                "numerator and denominator labels (mission §9)"
            )


class MetricRegistry:
    """Rejects duplicate metric ids and enforces the invariants above."""

    def __init__(self) -> None:
        self._metrics: Dict[str, MetricDefinition] = {}

    def register(self, metric: MetricDefinition) -> None:
        if metric.metric_id in self._metrics:
            raise ValueError(f"Duplicate metric_id: {metric.metric_id!r}")
        self._metrics[metric.metric_id] = metric

    def register_all(self, metrics: Sequence[MetricDefinition]) -> None:
        for m in metrics:
            self.register(m)

    def get(self, metric_id: str) -> MetricDefinition:
        return self._metrics[metric_id]

    def __contains__(self, metric_id: str) -> bool:
        return metric_id in self._metrics

    def __len__(self) -> int:
        return len(self._metrics)

    def by_domain(self, domain: str) -> Sequence[MetricDefinition]:
        return tuple(m for m in self._metrics.values() if m.domain == domain)

    def all(self) -> Sequence[MetricDefinition]:
        return tuple(self._metrics.values())


_MODULE_STATUSES = frozenset(
    {
        "CANONICAL_EXISTING",
        "CANONICAL_NEW",
        "PARTIAL",
        "PRESENTATION_ONLY",
        "LEGACY",
        "DUPLICATED",
        "UNUSED",
        "FUTURE_PROVIDER",
        "BLOCKED",
    }
)


@dataclass(frozen=True)
class ModuleDescriptor:
    module_id: str
    domain: str
    purpose: str
    canonical_source: str
    status: str
    consumers: Sequence[str]
    freshness_source: str
    dependencies: Sequence[str]
    known_debt: str

    def __post_init__(self) -> None:
        if self.domain not in DOMAIN_IDS:
            raise ValueError(f"{self.module_id}: unknown domain {self.domain!r}")
        if self.status not in _MODULE_STATUSES:
            raise ValueError(f"{self.module_id}: unknown status {self.status!r}")


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: Dict[str, ModuleDescriptor] = {}

    def register(self, module: ModuleDescriptor) -> None:
        if module.module_id in self._modules:
            raise ValueError(f"Duplicate module_id: {module.module_id!r}")
        self._modules[module.module_id] = module

    def register_all(self, modules: Sequence[ModuleDescriptor]) -> None:
        for m in modules:
            self.register(m)

    def get(self, module_id: str) -> ModuleDescriptor:
        return self._modules[module_id]

    def __contains__(self, module_id: str) -> bool:
        return module_id in self._modules

    def __len__(self) -> int:
        return len(self._modules)

    def all(self) -> Sequence[ModuleDescriptor]:
        return tuple(self._modules.values())
