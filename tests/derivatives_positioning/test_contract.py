import copy

import pytest

from observability.derivatives_positioning.contract import ContractError, normalize
from tests.derivatives_positioning.support import T0, obs_a, obs_b, without_source_time
from datetime import timedelta


def code_of(doc):
    with pytest.raises(ContractError) as exc:
        normalize(doc)
    return exc.value.code


def test_valid_observation_keeps_native_units_and_provenance():
    n = normalize(obs_a())
    m = n.document["measures"]
    assert m["open_interest"] == {"status": "AVAILABLE", "value": "1250000", "unit": "CONTRACTS",
                                  "contract_size_base": "0.0001"}
    assert m["funding_rate"]["interval_s"] == 28800
    assert n.document["provenance"]["mapping_id"] == "SYNTHETIC-A-BTC_USDT"
    assert n.source_time_ms is not None and n.received_at_ms > n.source_time_ms


def test_partial_result_needs_an_explicit_reason_per_field():
    doc = obs_b()
    assert normalize(doc).document["measures"]["spot_reference"] == {
        "status": "NOT_AVAILABLE", "reason": "SPOT_REFERENCE_NOT_QUALIFIED"}
    silent = copy.deepcopy(doc)
    del silent["measures"]["index_price"]
    assert code_of(silent) == "MEASURE_MISSING"
    empty = copy.deepcopy(doc)
    empty["measures"]["index_price"] = {}
    assert code_of(empty) == "MEASURE_WITHOUT_VALUE_OR_REASON"
    lower = copy.deepcopy(doc)
    lower["measures"]["index_price"] = {"unavailable": "n/a"}
    assert code_of(lower) == "INVALID_UNAVAILABLE_REASON"


@pytest.mark.parametrize("path,value,code", [
    (("measures", "mark_price"), {"value": 65000.5}, "FLOAT_NOT_EXACT"),
    (("measures", "mark_price"), {"value": "-1"}, "INVALID_DECIMAL"),
    (("measures", "open_interest"), {"value": "10", "unit": "CONTRACTS"}, "CONTRACT_SIZE_REQUIRED"),
    (("measures", "open_interest"), {"value": "10", "unit": "LOTS"}, "OPEN_INTEREST_UNIT_UNKNOWN"),
    (("measures", "open_interest"), {"value": "10", "unit": "BASE", "contract_size_base": "1"},
     "CONTRACT_SIZE_ONLY_FOR_CONTRACTS"),
    (("measures", "funding_rate"), {"value": "0.0001", "interval_attested_by": "x"}, "FUNDING_INTERVAL_NOT_ATTESTED"),
    (("measures", "funding_rate"), {"value": "0.0001", "interval_s": 28800}, "FUNDING_INTERVAL_NOT_ATTESTED"),
    (("measures", "spot_reference"), {"value": "1", "qualification": "GUESSED", "venue": "exchange_a",
                                      "native_symbol": "X", "qualification_ref": "r"}, "SPOT_REFERENCE_NOT_QUALIFIED"),
    (("source_time_utc",), "2026-11-21T12:00:00", "TIMESTAMP_WITHOUT_TIMEZONE"),
    (("contract_type",), "SPOT", "INVALID_CONTRACT_TYPE"),
    (("venue",), "Exchange A", "INVALID_VENUE_ID"),
    (("contract_version",), "0.9.0", "UNSUPPORTED_CONTRACT_VERSION"),
    (("surprise",), 1, "UNKNOWN_FIELD"),
])
def test_contract_violations_are_typed(path, value, code):
    doc = obs_a()
    target = doc
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    assert code_of(doc) == code


def test_receipt_time_and_collector_run_are_outside_identity_and_content():
    first = normalize(obs_a())
    replay = normalize(obs_a(received_delay_s=3600, run="run-2"))
    assert replay.observation_key == first.observation_key
    assert replay.content_sha256 == first.content_sha256
    assert replay.received_at_ms != first.received_at_ms


def test_equal_decimals_have_one_canonical_form():
    a, b = obs_a(mark="65000.50"), obs_a(mark="65000.5")
    b["provenance"]["payload_sha256"] = a["provenance"]["payload_sha256"]
    assert normalize(a).content_sha256 == normalize(b).content_sha256


def test_identity_without_source_time_uses_payload_and_capture_id():
    base = obs_a()
    a = normalize(without_source_time(base, received=T0))
    a_later = normalize(without_source_time(base, received=T0 + timedelta(minutes=7)))
    assert a.observation_key == a_later.observation_key  # replay: same payload, later receipt
    c1 = normalize(without_source_time(base, received=T0, capture_id="slot-1"))
    c2 = normalize(without_source_time(base, received=T0, capture_id="slot-2"))
    assert c1.observation_key != c2.observation_key  # collector separates two polls of an unchanged payload
    no_payload = without_source_time(base, received=T0)
    no_payload["provenance"]["payload_sha256"] = None
    assert code_of(no_payload) == "IDENTITY_UNRESOLVED"


def test_different_content_same_identity_differs_only_by_content_digest():
    a, b = normalize(obs_a()), normalize(obs_a(oi="1250001"))
    assert a.observation_key == b.observation_key and a.content_sha256 != b.content_sha256
