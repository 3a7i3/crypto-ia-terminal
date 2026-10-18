import hashlib
import json

import pytest

from sentinel_activity.canonical import LedgerError, canonical_bytes, digest, strict_loads
from sentinel_activity.contracts import validate_candidate
from tests.sentinel_activity.builders import candidate


def test_golden_canonical_bytes_independent_reference():
    value = {"z": [None, True, 42], "a": "é"}
    expected = b'{"a":"\xc3\xa9","z":[null,true,42]}'
    assert canonical_bytes(value) == expected
    assert digest(value) == hashlib.sha256(expected).hexdigest()
    # Compare independent reference JSON settings, not the implementation helper.
    assert canonical_bytes(value) == json.dumps(value, sort_keys=True, ensure_ascii=False,
                                               separators=(",", ":")).encode()


@pytest.mark.parametrize("raw,code", [
    ('{"a":1,"a":2}', "DUPLICATE_KEY"), ('{"a":NaN}', "NUMERIC_AMBIGUITY"),
    ('{"a":Infinity}', "NUMERIC_AMBIGUITY"), ('{"a":1.0}', "NUMERIC_AMBIGUITY"),
    ('{', "INVALID_JSON"), (b'"\xff"', "INVALID_JSON"),
])
def test_invalid_json(raw, code):
    with pytest.raises(LedgerError, match=code):
        strict_loads(raw)


@pytest.mark.parametrize("value,code", [
    ({1: "x"}, "SCHEMA_VIOLATION"), ((1,), "SCHEMA_VIOLATION"),
    ("e\u0301", "TEXT_NOT_CANONICAL"), ("\ud800", "TEXT_NOT_CANONICAL"),
    ("x\u202ey", "TEXT_NOT_CANONICAL"), ("x\ny", "TEXT_NOT_CANONICAL"),
    (2**63, "NUMERIC_AMBIGUITY"), ([[]] * 101, "BUDGET_EXCEEDED"),
])
def test_strict_values(value, code):
    with pytest.raises(LedgerError, match=code):
        canonical_bytes(value)


@pytest.mark.parametrize("key,value", [
    ("schema_version", "sentinel-event/999"), ("event_type", "UNKNOWN"),
    ("actor_kind", []), ("source_kind", {}), ("event_id", "../escape"),
    ("occurred_at_utc", "2026-02-31T00:00:00Z"), ("occurred_at_utc", "2026-10-18T00:00:00"),
    ("summary", "x" * 301), ("reason_declared", "x" * 1001),
    ("evidence_refs", ["fixture:z", "fixture:a"]), ("evidence_refs", ["fixture:a"] * 2),
    ("evidence_refs", ["https://untrusted.invalid/?credential=abc"]),
    ("authorization_ref", "anything"), ("quest_id", "fixture-q"),
])
def test_closed_event_contract(key, value):
    event = candidate()
    event[key] = value
    with pytest.raises(LedgerError):
        validate_candidate(event)


def test_unknown_fields_and_mutable_input():
    event = candidate()
    frozen = validate_candidate(event)
    event["payload"]["code"] = "CHANGED"
    assert frozen["payload"]["code"] == "FIXTURE_OBSERVATION"
    event["sequence"] = 1
    with pytest.raises(LedgerError):
        validate_candidate(event)


@pytest.mark.parametrize("number", [True, False, 1.0, "1", 0, -1])
def test_revision_is_pure_positive_integer(number):
    event = candidate(event_type="QUEST_ACCEPTED", quest="fixture-q",
                      payload={"expected_revision": number})
    with pytest.raises(LedgerError):
        validate_candidate(event)


def test_nested_secret_rejected_without_echo():
    event = candidate()
    secret = "ghp_" + "A" * 30
    event["summary"] = secret
    with pytest.raises(LedgerError) as error:
        validate_candidate(event)
    assert error.value.code == "SECRET_REJECTED"
    assert secret not in str(error.value)


def test_unknown_cost_stays_null_and_no_free_payload():
    event = candidate()
    assert validate_candidate(event)["payload"]["cost"] is None
    event["payload"]["cost"] = 0
    with pytest.raises(LedgerError):
        validate_candidate(event)
