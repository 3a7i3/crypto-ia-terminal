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
    to_jsonable,
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


# --- Blocker A remediation: EMPTY must carry the real empty value ---
# (independent review, O01_REMEDIATION_REQUIRED §2). EMPTY means the
# source was successfully observed and is genuinely empty — a different
# state from UNKNOWN/UNAVAILABLE/NOT_APPLICABLE, which carry no value at
# all because no observation happened.


@pytest.mark.parametrize(
    "empty_value",
    ["", [], (), {}, set(), frozenset()],
    ids=["str", "list", "tuple", "dict", "set", "frozenset"],
)
def test_observed_of_empty_collection_succeeds_and_is_empty(empty_value):
    ov = observed(empty_value)
    assert ov.semantics == NullSemantics.EMPTY
    assert ov.value == empty_value
    assert ov.value is not None


def test_empty_observed_value_constructs_directly_with_its_empty_value():
    ov = ObservedValue(value=[], semantics=NullSemantics.EMPTY)
    assert ov.value == []
    assert ov.semantics == NullSemantics.EMPTY


@pytest.mark.parametrize(
    "empty_value",
    ["", [], (), {}, set()],
    ids=["str", "list", "tuple", "dict", "set"],
)
def test_empty_is_available_and_distinguishable_from_absent_states(empty_value):
    empty_ov = ObservedValue(value=empty_value, semantics=NullSemantics.EMPTY)
    assert empty_ov.is_available is True
    assert empty_ov != unknown()
    assert empty_ov != unavailable()
    assert empty_ov != not_applicable()
    assert empty_ov != observed(0)  # ZERO
    assert empty_ov != observed(False)  # FALSE


def test_empty_semantics_rejects_none_value():
    with pytest.raises(ValueError):
        ObservedValue(value=None, semantics=NullSemantics.EMPTY)


@pytest.mark.parametrize(
    "non_empty_value",
    ["non-empty", [1], (1,), {"a": 1}, {1}],
    ids=["str", "list", "tuple", "dict", "set"],
)
def test_empty_semantics_rejects_non_empty_value(non_empty_value):
    with pytest.raises(ValueError):
        ObservedValue(value=non_empty_value, semantics=NullSemantics.EMPTY)


def test_empty_semantics_rejects_unsized_value():
    with pytest.raises(ValueError):
        ObservedValue(value=42, semantics=NullSemantics.EMPTY)


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


def test_to_jsonable_handles_primitives_enum_and_datetime():
    assert to_jsonable(None) is None
    assert to_jsonable("x") == "x"
    assert to_jsonable(3) == 3
    assert to_jsonable(3.5) == 3.5
    assert to_jsonable(True) is True
    assert to_jsonable(NullSemantics.ZERO) == "ZERO"
    assert to_jsonable(FreshnessStatus.STALE) == "STALE"
    dt = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    assert to_jsonable(dt) == "2026-09-03T12:00:00+00:00"


def test_to_jsonable_handles_nested_mapping_and_sequence():
    nested = {"a": [1, observed(0), {"b": (unknown(), "c")}]}
    result = to_jsonable(nested)
    assert result == {"a": [1, {"value": 0, "semantics": "ZERO"}, {"b": [{"value": None, "semantics": "UNKNOWN"}, "c"]}]}


def test_to_jsonable_uses_percentage_metric_to_dict_including_derived_pct():
    pct = PercentageMetric(numerator=1, denominator=4, numerator_label="a", denominator_label="b")
    result = to_jsonable(pct)
    assert result == {"numerator": 1, "denominator": 4, "numerator_label": "a", "denominator_label": "b", "pct": 25.0}


def test_to_jsonable_rejects_unserializable_type():
    class Unserializable:
        pass

    with pytest.raises(TypeError):
        to_jsonable(Unserializable())


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
