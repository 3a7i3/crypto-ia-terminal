"""Aggregates every domain's METRICS/MODULES into the canonical, tested
registries. Import this module to get the live registry; do not
construct a second one — that would itself be exactly the kind of
duplicate source of truth this mission exists to prevent (mission §26).
"""

from __future__ import annotations

from observability.operator.domains import (
    adaptive_learning,
    attrition,
    data_freshness,
    decision_pipeline,
    disk_io,
    execution_state,
    market_state,
    operator_summary,
    portfolio_state,
    regret_state,
    system_health,
)
from observability.operator.registry import MetricRegistry, ModuleRegistry

_DOMAIN_MODULES = (
    system_health,
    market_state,
    decision_pipeline,
    attrition,
    portfolio_state,
    execution_state,
    data_freshness,
    regret_state,
    adaptive_learning,
    disk_io,
    operator_summary,
)


def build_metric_registry() -> MetricRegistry:
    registry = MetricRegistry()
    for module in _DOMAIN_MODULES:
        registry.register_all(getattr(module, "METRICS", ()))
    return registry


def build_module_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    for module in _DOMAIN_MODULES:
        registry.register_all(getattr(module, "MODULES", ()))
    return registry


DEFAULT_METRIC_REGISTRY = build_metric_registry()
DEFAULT_MODULE_REGISTRY = build_module_registry()
