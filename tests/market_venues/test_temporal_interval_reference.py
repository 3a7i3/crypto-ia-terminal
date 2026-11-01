"""Synthetic maths only: no platform, clock probe, price or admission."""

import importlib.util
from pathlib import Path
import sys
import socket

import pytest

path = (
    Path(__file__).resolve().parents[2]
    / "docs/research/market_time_attestation_546/interval_reference.py"
)
spec = importlib.util.spec_from_file_location("interval_reference_546", path)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
Span, Window = m.Span, m.Window


@pytest.mark.parametrize("value", [True, 0.1, float("nan"), "1"])
def test_nanoseconds_require_exact_integers(value):
    with pytest.raises(TypeError):
        Span(value, 2)


def test_reversed_interval_refused():
    with pytest.raises(ValueError):
        Span(2, 1)


def test_offset_sign_quantization_and_lag_are_conservative():
    result = m.event_window(
        1000000,
        offset=Span(-100, 200),
        quantization=Span(0, 999),
        event_to_stamp_lag=Span(10, 20),
        scale="SYNTHETIC_COMMON",
    )
    assert result == Window("SYNTHETIC_COMMON", Span(999780, 1001089))


def test_nine_decimal_precision_survives_without_float_or_datetime():
    t = 1700000000123456789
    result = m.event_window(
        t,
        offset=Span(1, 1),
        quantization=Span(-1, 0),
        event_to_stamp_lag=Span(0, 0),
        scale="SYNTHETIC_COMMON",
    )
    assert result.span == Span(t - 2, t - 1)


@pytest.mark.parametrize(
    "field", ["native_ns", "offset", "quantization", "event_to_stamp_lag", "scale"]
)
def test_any_missing_component_leaves_unknown(field):
    args = dict(
        native_ns=100,
        offset=Span(0, 0),
        quantization=Span(0, 0),
        event_to_stamp_lag=Span(0, 0),
        scale="SYNTHETIC_COMMON",
    )
    args[field] = None
    assert m.event_window(**args) is None


def test_negative_event_to_label_lag_is_refused():
    with pytest.raises(ValueError):
        m.event_window(
            10,
            offset=Span(0, 0),
            quantization=Span(0, 0),
            event_to_stamp_lag=Span(-1, 0),
            scale="SYNTHETIC_COMMON",
        )


@pytest.mark.parametrize("scale", ["", "UNKNOWN", "UNRESOLVED", " UNKNOWN ", None])
def test_unknown_common_scale_is_not_promoted(scale):
    if scale is None:
        assert (
            m.event_window(
                0,
                offset=Span(0, 0),
                quantization=Span(0, 0),
                event_to_stamp_lag=Span(0, 0),
                scale=scale,
            )
            is None
        )
    else:
        with pytest.raises(ValueError):
            Window(scale, Span(0, 0))


def test_chrony_conditional_point_estimate_and_outward_rounding():
    # Conditional application to conserved #542 numbers, not a continuous bound.
    assert m.chrony_point_bound_ns(-1928, 800163, 130041) == 867112
    assert m.chrony_point_bound_ns(0, 0, 1) == 1


def test_unknown_clock_terms_and_rate_never_default_to_zero():
    assert m.chrony_point_bound_ns(0, None, 1) is None
    assert m.grow_bound_ns(867112, 30000000000, None) is None


def test_bound_growth_rounds_outwards_and_uses_explicit_rate():
    assert m.grow_bound_ns(867112, 30000000000, 500) == 882112
    assert m.grow_bound_ns(0, 1, 1) == 1


@pytest.mark.parametrize("args", [(-1, 1, 1), (0, -1, 1), (0, 1, -1), (0, 1, True)])
def test_invalid_growth_inputs_are_refused(args):
    with pytest.raises((TypeError, ValueError)):
        m.grow_bound_ns(*args)


def test_age_uses_both_uncertainty_sides_and_preserves_negative():
    assert m.age_window(
        Window("SYNTHETIC_COMMON", Span(90, 110)),
        Window("SYNTHETIC_COMMON", Span(100, 120)),
    ) == Span(-30, 10)


@pytest.mark.parametrize(
    "age,status",
    [
        (None, "UNRESOLVED"),
        (Span(-10, -1), "FUTURE"),
        (Span(-1, 3), "FUTURE_NOT_EXCLUDED"),
        (Span(6, 9), "STALE"),
        (Span(0, 6), "STALE_NOT_EXCLUDED"),
        (Span(0, 5), "WITHIN_ASSUMPTIONS"),
    ],
)
def test_age_classification_requires_all_possible_times_within_budget(age, status):
    assert m.classify_age(age, max_age_ns=5) == status


def test_overlap_does_not_prove_small_worst_case_separation():
    a = Window("SYNTHETIC_COMMON", Span(-1000, 1000))
    b = Window("SYNTHETIC_COMMON", Span(-1000, 1000))
    gap = m.separation_window(a, b)
    assert gap == Span(0, 2000)
    assert m.classify_separation(gap, max_gap_ns=10) == "GAP_NOT_EXCLUDED"


def test_disjoint_and_point_event_separations():
    assert m.separation_window(
        Window("SYNTHETIC_COMMON", Span(0, 10)),
        Window("SYNTHETIC_COMMON", Span(30, 40)),
    ) == Span(20, 40)
    same = Window("SYNTHETIC_COMMON", Span(7, 7))
    assert m.separation_window(same, same) == Span(0, 0)


@pytest.mark.parametrize("fn", [m.age_window, m.separation_window])
def test_different_scales_are_never_aliased_and_unknown_stays_unknown(fn):
    with pytest.raises(ValueError):
        fn(Window("SYNTHETIC_A", Span(0, 1)), Window("SYNTHETIC_B", Span(0, 1)))
    assert fn(None, Window("SYNTHETIC_A", Span(0, 1))) is None


@pytest.mark.parametrize(
    "gap,limit,status",
    [
        (None, 1, "UNRESOLVED"),
        (Span(0, 10), 10, "WITHIN_ASSUMPTIONS"),
        (Span(11, 20), 10, "EXCEEDS_ASSUMPTIONS"),
        (Span(0, 11), 10, "GAP_NOT_EXCLUDED"),
    ],
)
def test_gap_budget_is_explicit_and_inclusive(gap, limit, status):
    assert m.classify_separation(gap, max_gap_ns=limit) == status


def test_no_implicit_quality_policy_and_no_negative_policy():
    with pytest.raises(TypeError):
        m.classify_age(Span(0, 0))
    with pytest.raises(ValueError):
        m.classify_separation(Span(0, 0), max_gap_ns=-1)


@pytest.fixture(autouse=True)
def refuse_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("NO_NETWORK_IN_REFERENCE_TESTS")

    monkeypatch.setattr(socket, "create_connection", refused)
    monkeypatch.setattr(socket, "getaddrinfo", refused)


def test_event_bounds_match_exhaustive_integer_domain_extrema():
    times = [
        100 + q - o - lag
        for q in range(-2, 3)
        for o in range(-3, 5)
        for lag in range(4)
    ]
    result = m.event_window(
        100,
        offset=Span(-3, 4),
        quantization=Span(-2, 2),
        event_to_stamp_lag=Span(0, 3),
        scale="SYNTHETIC_COMMON",
    )
    assert result.span == Span(min(times), max(times))


def test_pair_bounds_match_exhaustive_integer_domain_extrema():
    distances = [abs(a - b) for a in range(-3, 6) for b in range(2, 8)]
    result = m.separation_window(
        Window("SYNTHETIC_COMMON", Span(-3, 5)), Window("SYNTHETIC_COMMON", Span(2, 7))
    )
    assert result == Span(min(distances), max(distances))
