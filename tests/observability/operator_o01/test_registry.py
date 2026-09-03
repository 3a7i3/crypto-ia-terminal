import pytest

from observability.operator.canonical_registry import (
    DEFAULT_METRIC_REGISTRY,
    DEFAULT_MODULE_REGISTRY,
    build_metric_registry,
    build_module_registry,
)
from observability.operator.contracts import DOMAIN_IDS
from observability.operator.registry import MetricDefinition, MetricRegistry, ModuleDescriptor, ModuleRegistry


def test_metric_registry_rejects_duplicate_ids():
    registry = MetricRegistry()
    m = MetricDefinition(
        metric_id="dup.test",
        domain="system_health",
        operator_label_fr="Test",
        technical_name="x",
        definition_fr="x",
        unit="count",
        value_type="count",
        freshness_source="x",
        expected_cadence="x",
        polarity="neutral",
        evidence_source="x",
        presentation_priority="secondary",
    )
    registry.register(m)
    with pytest.raises(ValueError):
        registry.register(m)


def test_metric_definition_requires_french_label():
    with pytest.raises(ValueError):
        MetricDefinition(
            metric_id="no_label.test",
            domain="system_health",
            operator_label_fr="   ",
            technical_name="x",
            definition_fr="x",
            unit="count",
            value_type="count",
            freshness_source="x",
            expected_cadence="x",
            polarity="neutral",
            evidence_source="x",
            presentation_priority="secondary",
        )


def test_metric_definition_rejects_unknown_domain():
    with pytest.raises(ValueError):
        MetricDefinition(
            metric_id="bad_domain.test",
            domain="not_a_domain",
            operator_label_fr="Test",
            technical_name="x",
            definition_fr="x",
            unit="count",
            value_type="count",
            freshness_source="x",
            expected_cadence="x",
            polarity="neutral",
            evidence_source="x",
            presentation_priority="secondary",
        )


def test_percentage_metric_requires_explicit_numerator_and_denominator():
    with pytest.raises(ValueError):
        MetricDefinition(
            metric_id="pct.no_denominator",
            domain="attrition",
            operator_label_fr="Test",
            technical_name="x",
            definition_fr="x",
            unit="pct",
            value_type="percentage",
            freshness_source="x",
            expected_cadence="x",
            polarity="neutral",
            evidence_source="x",
            presentation_priority="secondary",
        )


def test_module_registry_rejects_duplicate_ids():
    registry = ModuleRegistry()
    m = ModuleDescriptor(
        module_id="dup.module",
        domain="system_health",
        purpose="x",
        canonical_source="x",
        status="CANONICAL_EXISTING",
        consumers=(),
        freshness_source="x",
        dependencies=(),
        known_debt="none",
    )
    registry.register(m)
    with pytest.raises(ValueError):
        registry.register(m)


def test_module_descriptor_rejects_unknown_status():
    with pytest.raises(ValueError):
        ModuleDescriptor(
            module_id="bad_status.module",
            domain="system_health",
            purpose="x",
            canonical_source="x",
            status="NOT_A_REAL_STATUS",
            consumers=(),
            freshness_source="x",
            dependencies=(),
            known_debt="none",
        )


def test_default_metric_registry_builds_without_duplicates_and_has_entries():
    assert len(DEFAULT_METRIC_REGISTRY) > 0
    rebuilt = build_metric_registry()
    assert len(rebuilt) == len(DEFAULT_METRIC_REGISTRY)


def test_default_module_registry_builds_without_duplicates_and_has_entries():
    assert len(DEFAULT_MODULE_REGISTRY) > 0
    rebuilt = build_module_registry()
    assert len(rebuilt) == len(DEFAULT_MODULE_REGISTRY)


def test_every_registered_metric_has_a_french_label_and_known_domain():
    for metric in DEFAULT_METRIC_REGISTRY.all():
        assert metric.operator_label_fr.strip()
        assert metric.domain in DOMAIN_IDS


def test_every_registered_metric_id_is_unique():
    ids = [m.metric_id for m in DEFAULT_METRIC_REGISTRY.all()]
    assert len(ids) == len(set(ids))


def test_every_registered_module_id_is_unique():
    ids = [m.module_id for m in DEFAULT_MODULE_REGISTRY.all()]
    assert len(ids) == len(set(ids))


def test_every_percentage_metric_has_numerator_and_denominator():
    for metric in DEFAULT_METRIC_REGISTRY.all():
        if metric.value_type == "percentage":
            assert metric.numerator, metric.metric_id
            assert metric.denominator, metric.metric_id


def test_every_domain_referenced_by_a_metric_is_a_known_domain():
    for metric in DEFAULT_METRIC_REGISTRY.all():
        assert metric.domain in DOMAIN_IDS
    for module in DEFAULT_MODULE_REGISTRY.all():
        assert module.domain in DOMAIN_IDS


def test_all_11_domains_have_at_least_one_module_entry():
    domains_covered = {m.domain for m in DEFAULT_MODULE_REGISTRY.all()}
    assert domains_covered == set(DOMAIN_IDS)


def test_module_consumers_and_dependencies_are_sequences_not_bare_strings():
    # A single-element tuple without a trailing comma silently collapses to
    # a plain str, which then iterates character-by-character wherever
    # consumers/dependencies are joined for display — this guards against
    # that regression class.
    for module in DEFAULT_MODULE_REGISTRY.all():
        assert not isinstance(module.consumers, str), module.module_id
        assert not isinstance(module.dependencies, str), module.module_id
