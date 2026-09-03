from datetime import datetime, timezone

import pytest

from observability.operator.contracts import (
    DomainSnapshot,
    FreshnessStatus,
    NullSemantics,
    ObservedValue,
    PercentageMetric,
    not_applicable,
    observed,
    stale,
    unavailable,
    unknown,
)


def test_observed_wraps_present_nonzero_value():
    ov = observed(42)
    assert ov.value == 42
    assert ov.semantics == NullSemantics.PRESENT
    assert ov.is_available


def test_observed_distinguishes_zero_from_unknown():
    zero = observed(0)
    unk = unknown()
    assert zero.semantics == NullSemantics.ZERO
    assert unk.semantics == NullSemantics.UNKNOWN
    assert zero.value == 0
    assert unk.value is None
    assert zero != unk


def test_observed_distinguishes_false_from_unknown():
    false_val = observed(False)
    assert false_val.semantics == NullSemantics.FALSE
    assert false_val.value is False


def test_unavailable_is_not_available():
    assert unavailable().is_available is False
    assert unknown().is_available is False
    assert observed(0).is_available is True


def test_stale_carries_a_value_but_flags_it():
    s = stale(123.4)
    assert s.value == 123.4
    assert s.semantics == NullSemantics.STALE


def test_not_applicable_has_no_value():
    na = not_applicable()
    assert na.value is None
    assert na.semantics == NullSemantics.NOT_APPLICABLE


def test_observed_value_rejects_inconsistent_semantics():
    with pytest.raises(ValueError):
        ObservedValue(value=5, semantics=NullSemantics.UNKNOWN)
    with pytest.raises(ValueError):
        ObservedValue(value=None, semantics=NullSemantics.PRESENT)


def test_observed_value_serializes_deterministically():
    ov = observed(7)
    d = ov.to_dict()
    assert d == {"value": 7, "semantics": "PRESENT"}


def test_percentage_metric_requires_explicit_numerator_denominator_labels():
    pct = PercentageMetric(
        numerator=3,
        denominator=10,
        numerator_label="refus couche risque",
        denominator_label="candidats entrant dans le pipeline de refus",
    )
    assert pct.pct == 30.0
    assert pct.to_dict()["numerator_label"] == "refus couche risque"


def test_percentage_metric_handles_zero_denominator_without_crashing():
    pct = PercentageMetric(numerator=0, denominator=0, numerator_label="a", denominator_label="b")
    assert pct.ratio is None
    assert pct.pct is None


def test_percentage_metric_rejects_numerator_exceeding_denominator():
    with pytest.raises(ValueError):
        PercentageMetric(numerator=11, denominator=10, numerator_label="a", denominator_label="b")


def test_domain_snapshot_requires_known_domain():
    with pytest.raises(ValueError):
        DomainSnapshot(
            domain="not_a_real_domain",
            observed_at_utc=datetime.now(timezone.utc),
            source="test",
            freshness=FreshnessStatus.FRESH,
            status="OK",
        )


def test_domain_snapshot_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError):
        DomainSnapshot(
            domain="system_health",
            observed_at_utc=datetime.now(),  # naive
            source="test",
            freshness=FreshnessStatus.FRESH,
            status="OK",
        )


def test_domain_snapshot_has_schema_version_and_serializes():
    snap = DomainSnapshot(
        domain="system_health",
        observed_at_utc=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
        source="test",
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )
    d = snap.to_dict()
    assert d["schema_version"]
    assert d["domain"] == "system_health"
    assert d["observed_at_utc"] == "2026-09-03T12:00:00+00:00"
    assert d["freshness"] == "FRESH"
