import copy
import json
from datetime import timedelta
from decimal import Decimal

import pytest

from observability.market_stress.publication import build_publication
from observability.market_stress.schema import validate_publication
from tests.market_stress.support import NOW, observation, pilot

KW = dict(as_of=NOW, max_age_ms=5000, max_skew_ms=500, history_tolerance_ms=60_000, evidence_kind="SYNTHETIC")


def build(obs=None, bindings=None):
    b, o = pilot()
    return build_publication(bindings or b, o if obs is None else obs, **KW)


def leg(doc, venue, kind, quote="USDT"):
    for u in doc["underlyings"]:
        for x in u["legs"]:
            if x["venue"] == venue and x["instrument"]["market_kind"] == kind and x["instrument"]["quote_asset_id"] == quote:
                return x
    raise KeyError((venue, kind))


def test_pilot_is_valid_and_closed():
    doc = build()
    assert validate_publication(doc)
    assert doc["authority"] == "OBSERVATIONAL_TELEMETRY" and doc["execution_authority"] is False
    assert doc["source_counts"] == {"expected": 6, "supplied": 6, "available": 6}
    assert [u["quote_asset_id"] for u in doc["underlyings"]] == ["USDT", "USD"]  # USD and USDT never merged
    json.dumps(doc, allow_nan=False)


def test_derivative_metrics_are_exact():
    doc = build()
    perp = leg(doc, "mexc", "PERPETUAL_LINEAR")
    assert perp["premium_to_index"]["bps"] == "12.997401"  # (100150 - 100020) / 100020
    assert perp["basis_vs_spot"]["status"] == "AVAILABLE" and perp["basis_vs_spot"]["against_venue"] == "mexc"
    assert perp["basis_vs_spot"]["bps"] == "15.000000"
    f = perp["funding"]
    assert f["rate"] == "0.0001000000" and f["rate_8h_equivalent"] == "0.0001000000"
    assert f["annualized_simple_pct"] == "10.950000"
    assert perp["open_interest"]["notional_quote"] == "150225000.00000000"


def test_further_venue_uses_the_default_spot_reference_and_other_interval_is_normalised():
    doc = build()
    other = leg(doc, "exchange_c", "PERPETUAL_LINEAR")
    assert other["basis_vs_spot"]["against_venue"] == "mexc"
    assert other["basis_vs_spot"]["bps"] == "17.000000"
    quarterly = leg(doc, "exchange_c", "FUTURE_LINEAR")
    assert quarterly["basis_vs_spot"]["annualized_pct"] is not None
    assert quarterly["funding"]["reason"] == "NOT_APPLICABLE"  # dated futures carry no funding


def test_inverse_contract_in_quote_units_and_negative_funding():
    doc = build()
    inverse = leg(doc, "kraken", "PERPETUAL_INVERSE", "USD")
    assert inverse["funding"]["rate"] == "-0.0000500000"
    assert inverse["open_interest"]["notional_quote"] == "80000000.00000000"
    assert inverse["basis_vs_spot"]["against_venue"] == "kraken"


def test_windows_report_signs_without_interpretation():
    doc = build()
    perp = leg(doc, "mexc", "PERPETUAL_LINEAR")
    assert [w["window_s"] for w in perp["windows"]] == [3600, 14400, 86400]
    # fixture history: 24 h and 4 h ago both lower; 1 h ago higher on both price and open interest
    assert [(w["status"], w["price_sign"], w["oi_sign"]) for w in perp["windows"]] == [
        ("AVAILABLE", "DOWN", "DOWN"), ("AVAILABLE", "UP", "UP"), ("AVAILABLE", "UP", "UP")]
    assert perp["windows"][2]["price_change_bps"] == "309.278351"  # 100150 vs 97145.5 (24 h)
    spot = leg(doc, "mexc", "SPOT")
    assert all(w["oi_sign"] is None and w["oi_change_pct"] is None for w in spot["windows"])


def test_window_without_a_sample_is_unavailable_not_zero():
    b, o = pilot()
    o[1] = observation(b[1], price="100150", index="100020", funding="0.0001", oi="1500", hist=False)
    perp = leg(build(o, b), "mexc", "PERPETUAL_LINEAR")
    assert all(w["status"] == "NOT_AVAILABLE" and w["reason"] == "NO_SAMPLE_AT_WINDOW_START" and w["price_change_bps"] is None
               for w in perp["windows"])


def test_missing_and_stale_legs_stay_visible():
    b, o = pilot()
    stale = observation(b[2], price="100170", index="100030", funding="0.0003", oi="900", age_ms=60_000)
    doc = build([*o[:2], stale, *o[3:]], b)
    assert leg(doc, "exchange_c", "PERPETUAL_LINEAR")["reason"] == "STALE"
    assert leg(doc, "exchange_c", "PERPETUAL_LINEAR")["price"] is None
    doc = build(o[:4], b)
    assert leg(doc, "kraken", "SPOT", "USD")["reason"] == "SOURCE_NOT_SUPPLIED"
    assert doc["source_counts"] == {"expected": 6, "supplied": 4, "available": 4}
    total = doc["underlyings"][1]["open_interest_total"]
    assert total["status"] == "NOT_AVAILABLE" and total["reason"] == "PARTIAL_COVERAGE" and total["notional_quote"] is None
    assert total["coverage"] == {"expected": 1, "available": 0, "missing": ["kraken:PI_XBTUSD"]}


def test_total_open_interest_requires_full_coverage():
    doc = build()
    total = doc["underlyings"][0]["open_interest_total"]
    assert total["status"] == "AVAILABLE" and total["coverage"]["available"] == 3
    # BASE 1500 x 100150 + 900 x 100170 + CONTRACTS-less BASE 400 x 101500
    assert Decimal(total["notional_quote"]) == Decimal("150225000") + Decimal("90153000") + Decimal("40600000")


def test_contracts_need_a_contract_size():
    b, o = pilot()
    o[1] = observation(b[1], price="100150", index="100020", funding="0.0001", oi="1500", unit="CONTRACTS")
    perp = leg(build(o, b), "mexc", "PERPETUAL_LINEAR")
    assert perp["open_interest"]["value"] == "1500" and perp["open_interest"]["notional_quote"] is None
    assert perp["open_interest"]["reason"] == "CONTRACT_SIZE_UNKNOWN"
    o[1] = observation(b[1], price="100150", index="100020", funding="0.0001", oi="1500", unit="CONTRACTS", contract="0.001")
    assert leg(build(o, b), "mexc", "PERPETUAL_LINEAR")["open_interest"]["notional_quote"] == "150225.00000000"


def test_unknown_funding_interval_is_refused_not_assumed():
    b, o = pilot()
    bad = observation(b[1], price="100150", index="100020", funding="0.0001", oi="1500")
    bad = type(bad)(**{**bad.__dict__, "funding_interval_s": None})
    o[1] = bad
    assert leg(build(o, b), "mexc", "PERPETUAL_LINEAR")["funding"]["reason"] == "FUNDING_INTERVAL_UNKNOWN"


def test_different_clock_blocks_basis_and_pairs():
    b, o = pilot()
    o[2] = observation(b[2], price="100170", index="100030", funding="0.0003", oi="900", clock="OTHER_CLOCK")
    doc = build(o, b)
    assert leg(doc, "exchange_c", "PERPETUAL_LINEAR")["basis_vs_spot"]["reason"] == "OBSERVER_CLOCKS_NOT_ALIGNED"
    pair = [p for p in doc["underlyings"][0]["pairs"] if (p["reference_venue"], p["other_venue"]) == ("mexc", "exchange_c")]
    assert pair[0]["status"] == "NOT_AVAILABLE" and pair[0]["reason"] == "OBSERVER_CLOCKS_NOT_ALIGNED"


def test_cross_venue_pair_gap_and_funding_difference():
    doc = build()
    pair = next(p for p in doc["underlyings"][0]["pairs"]
                if (p["reference_venue"], p["other_venue"]) == ("mexc", "exchange_c") and p["status"] == "AVAILABLE")
    assert Decimal(pair["price_gap_bps"]).quantize(Decimal("0.001")) == Decimal("1.997")
    assert pair["funding_8h_difference"] == "0.0002000000"


def test_roster_is_independent_of_observations():
    b, o = pilot()
    with pytest.raises(ValueError):
        build_publication(b, [*o, o[0]], **KW)
    with pytest.raises(ValueError):
        build_publication(b[:2], o, **KW)
    with pytest.raises(ValueError):
        build_publication([b[0], b[0]], [], **KW)
    with pytest.raises(ValueError):
        build_publication([], [], **KW)


def test_limits_are_explicit():
    b, o = pilot()
    with pytest.raises(ValueError):
        build_publication(b, o, as_of=NOW, max_age_ms=None, max_skew_ms=1, history_tolerance_ms=1, evidence_kind="SYNTHETIC")
    with pytest.raises(ValueError):
        build_publication(b, o, **{**KW, "evidence_kind": "GUESS"})


def test_valid_until_is_the_earliest_admitted_expiry():
    doc = build()
    # exchange_c perp is the oldest observation at 60 ms; the freshest-first rule would be wrong
    assert doc["valid_until_utc"] == (NOW - timedelta(milliseconds=200) + timedelta(milliseconds=5000)).isoformat().replace("+00:00", "Z")
    assert build([], pilot()[0])["valid_until_utc"] is None


def test_schema_rejects_tampering():
    doc = build()
    assert validate_publication(doc)
    cases = []
    for path, value in [
        (("execution_authority",), True), (("authority",), "ADVISOR"), (("extra",), 1),
        (("underlyings", 0, "legs", 1, "funding", "annualized_simple_pct"), "NaN"),
        (("underlyings", 0, "legs", 0, "status"), "NOT_AVAILABLE"),
        (("underlyings", 0, "open_interest_total", "notional_quote"), "1"),
        (("source_counts", "available"), 5),
        (("parameters", "windows_s"), [60]),
        (("underlyings", 0, "legs", 1, "timing", "histogram", "counts", 0), 9),
        (("underlyings", 0, "legs", 1, "timing", "scan", 0, "radius_ms"), 7),
    ]:
        bad = copy.deepcopy(doc)
        cursor = bad
        for step in path[:-1]:
            cursor = cursor[step]
        cursor[path[-1]] = value
        cases.append(validate_publication(bad))
    assert cases == [False] * len(cases)
    for k in ("price", "funding", "windows"):
        bad = copy.deepcopy(doc)
        del bad["underlyings"][0]["legs"][1][k]
        assert not validate_publication(bad)
