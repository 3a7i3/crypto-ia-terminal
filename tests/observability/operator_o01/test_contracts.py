from dataclasses import dataclass
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


# --- Final contract-hardening pass: the full ObservedValue canonical
# invariant matrix (independent review, final canonicality mission §1-3).
# Each NullSemantics member must validate its own shape directly on the
# dataclass, not only via the observed()/unknown()/... factory helpers,
# so a caller constructing ObservedValue directly can never represent an
# internally contradictory state. ---


@pytest.mark.parametrize("bad_value", [5, 1, -1, 0.5], ids=["int5", "int1", "int-1", "float0.5"])
def test_zero_rejects_nonzero_numeric_values(bad_value):
    with pytest.raises(ValueError):
        ObservedValue(value=bad_value, semantics=NullSemantics.ZERO)


def test_zero_rejects_bool_true_even_though_not_numerically_zero():
    with pytest.raises(ValueError):
        ObservedValue(value=True, semantics=NullSemantics.ZERO)


def test_zero_rejects_bool_false_despite_false_equalling_zero_numerically():
    # bool False == 0 numerically, but ZERO must never accept a bool —
    # that ambiguity belongs to NullSemantics.FALSE instead.
    with pytest.raises(ValueError):
        ObservedValue(value=False, semantics=NullSemantics.ZERO)


def test_zero_accepts_genuine_numeric_zero():
    assert ObservedValue(value=0, semantics=NullSemantics.ZERO).value == 0
    assert ObservedValue(value=0.0, semantics=NullSemantics.ZERO).value == 0.0


def test_false_rejects_true():
    with pytest.raises(ValueError):
        ObservedValue(value=True, semantics=NullSemantics.FALSE)


def test_false_rejects_zero_despite_equality_with_false():
    # Identity-based, not equality-based: 0 == False in Python, but a
    # caller reporting FALSE means the boolean, not the integer.
    with pytest.raises(ValueError):
        ObservedValue(value=0, semantics=NullSemantics.FALSE)


def test_false_accepts_exactly_false():
    assert ObservedValue(value=False, semantics=NullSemantics.FALSE).value is False


@pytest.mark.parametrize(
    "bad_value",
    [None, 0, False, "", [], {}],
    ids=["none", "zero", "false", "empty_str", "empty_list", "empty_dict"],
)
def test_present_rejects_none_zero_false_and_empty_values(bad_value):
    with pytest.raises(ValueError):
        ObservedValue(value=bad_value, semantics=NullSemantics.PRESENT)


@pytest.mark.parametrize("good_value", [True, 42, -1, "x", [1], {"a": 1}, 0.5])
def test_present_accepts_genuine_nonzero_nonfalse_nonempty_values(good_value):
    assert ObservedValue(value=good_value, semantics=NullSemantics.PRESENT).value == good_value


def test_stale_rejects_none():
    with pytest.raises(ValueError):
        ObservedValue(value=None, semantics=NullSemantics.STALE)


@pytest.mark.parametrize("real_but_falsy_value", [0, False, "", []], ids=["zero", "false", "empty_str", "empty_list"])
def test_stale_allows_last_known_value_even_if_falsy_or_empty(real_but_falsy_value):
    # STALE is a freshness condition overriding current availability, not
    # an absence of data — it must preserve the actual underlying value
    # even when that value is 0/False/empty.
    ov = ObservedValue(value=real_but_falsy_value, semantics=NullSemantics.STALE)
    assert ov.value == real_but_falsy_value


def test_stale_helper_preserves_falsy_values():
    assert stale(0).value == 0
    assert stale(False).value is False


# --- Factory mapping proof: observed() must route to the semantics the
# invariant matrix above expects. ---


def test_factory_mapping_matches_canonical_semantics():
    assert observed(0).semantics == NullSemantics.ZERO
    assert observed(False).semantics == NullSemantics.FALSE
    assert observed("").semantics == NullSemantics.EMPTY
    assert observed([]).semantics == NullSemantics.EMPTY
    assert observed(42).semantics == NullSemantics.PRESENT
    assert observed(True).semantics == NullSemantics.PRESENT


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


# --- Final contract-hardening pass: deterministic set/frozenset
# serialization (independent review, final canonicality mission §4-5).
# Python's set iteration order depends on hash seeding and insertion
# history, not on scientific content — to_jsonable() must not let that
# leak into the canonical snapshot contract. Lists/tuples are untouched:
# their order is meaningful and must be preserved exactly. ---


def test_to_jsonable_set_has_deterministic_canonical_order():
    assert to_jsonable({"b", "a", "c"}) == ["a", "b", "c"]


def test_to_jsonable_frozenset_has_the_same_canonical_order_as_the_equivalent_set():
    assert to_jsonable(frozenset({"b", "a", "c"})) == to_jsonable({"c", "b", "a"})


def test_to_jsonable_set_order_is_independent_of_insertion_order():
    set_a = set()
    set_a.add("z")
    set_a.add("a")
    set_a.add("m")
    set_b = set()
    set_b.add("m")
    set_b.add("z")
    set_b.add("a")
    assert set_a == set_b  # same set, different construction order
    assert to_jsonable(set_a) == to_jsonable(set_b)


def test_to_jsonable_set_of_heterogeneous_jsonable_types_does_not_crash_and_is_deterministic():
    heterogeneous = {1, "a", 2.5, True}
    first = to_jsonable(heterogeneous)
    second = to_jsonable(set(heterogeneous))  # rebuilt, same elements
    assert first == second
    assert isinstance(first, list)


def test_to_jsonable_does_not_sort_lists_or_tuples():
    assert to_jsonable(["b", "a", "c"]) == ["b", "a", "c"]
    assert to_jsonable(("z", "y", "x")) == ["z", "y", "x"]


def test_to_jsonable_set_nested_inside_observed_value_is_deterministic():
    ov_a = observed(frozenset({"risk_gate", "meta_strategy", "no_trade"}))
    ov_b = observed(frozenset({"no_trade", "risk_gate", "meta_strategy"}))
    assert to_jsonable(ov_a) == to_jsonable(ov_b)


def test_to_jsonable_set_nested_inside_mapping_is_deterministic():
    evidence_a = {"blockers": {"gate", "meta", "notrade"}}
    evidence_b = {"blockers": {"notrade", "gate", "meta"}}
    assert to_jsonable(evidence_a) == to_jsonable(evidence_b)


def test_to_jsonable_set_nested_inside_plain_dataclass_is_deterministic():
    @dataclass(frozen=True)
    class _HoldsASet:
        tags: frozenset

    a = _HoldsASet(tags=frozenset({"c", "a", "b"}))
    b = _HoldsASet(tags=frozenset({"b", "c", "a"}))
    assert to_jsonable(a) == to_jsonable(b)


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
