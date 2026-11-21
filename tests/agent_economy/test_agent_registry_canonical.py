"""Canonical serialization, strict text rules and the closed error-code set."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pytest

from agent_economy.agent_registry.canonical import (
    ERROR_CODES,
    AgentRegistryError,
    canonical_json_bytes,
    find_float,
    is_pure_int,
    parse_utc_timestamp,
    publication_json_bytes,
    sha256_hex,
    text_violation,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "contracts" / "AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT.md"


def test_canonical_bytes_are_the_certified_algorithm():
    value = {"b": 1, "a": ["é", None, True], "c": {"y": 2, "x": 1}}
    expected = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert canonical_json_bytes(value) == expected
    assert canonical_json_bytes(value) == '{"a":["é",null,true],"b":1,"c":{"x":1,"y":2}}'.encode()


def test_canonical_is_independent_of_key_insertion_order():
    assert canonical_json_bytes({"a": 1, "b": 2}) == canonical_json_bytes({"b": 2, "a": 1})


def test_sha256_is_lowercase_hex_of_canonical_bytes():
    digest = sha256_hex({"a": 1})
    assert digest == hashlib.sha256(b'{"a":1}').hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


def test_publication_bytes_are_the_aw03_form():
    spec = {"b": [1, 2], "a": "é"}
    expected = (
        json.dumps(spec, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    assert publication_json_bytes(spec) == expected
    assert expected.endswith(b"}\n") and b'  "a"' in expected


@pytest.mark.parametrize(
    "value",
    [
        {"a": 1.0},
        {"a": float("nan")},
        {"a": float("inf")},
        {"a": (1, 2)},  # a tuple would be silently turned into a list by json
        {1: "int key"},  # json would silently stringify the key
        {"a": {1, 2}},
        {"a": b"bytes"},
    ],
)
def test_canonicalization_rejects_instead_of_normalizing(value):
    with pytest.raises(AgentRegistryError) as caught:
        canonical_json_bytes(value)
    assert caught.value.code == "CANONICALIZATION_FAILED"
    with pytest.raises(AgentRegistryError):
        publication_json_bytes(value)


def test_lone_surrogate_cannot_be_serialized():
    with pytest.raises(AgentRegistryError):
        canonical_json_bytes({"a": "\ud800"})


def test_bool_and_int_are_distinct_for_integer_fields():
    assert is_pure_int(1) and not is_pure_int(True) and not is_pure_int(1.0)
    assert find_float({"a": [{"b": 1.0}]}) == "$.a[0].b"
    assert find_float({"a": [1, True, "1.0"]}) is None


def test_text_rules_reject_non_nfc_control_and_boundary_whitespace():
    nfd = unicodedata.normalize("NFD", "café")
    assert nfd != "café"
    assert text_violation("café") is None
    assert text_violation(nfd)
    assert text_violation("a\x00b")
    assert text_violation("a\tb")
    assert text_violation("a\x7fb")
    assert text_violation("a\nb")
    assert text_violation("a\nb", allow_newline=True) is None
    assert text_violation("a\r\nb", allow_newline=True)
    assert text_violation(" a") and text_violation("a ") and text_violation("a ")
    assert text_violation("a\ud800b")


def test_timestamps_must_be_real_utc_instants():
    assert parse_utc_timestamp("2026-10-04T00:00:00Z") is not None
    assert parse_utc_timestamp("2026-10-04T00:00:00.123456Z") is not None
    for bad in (
        "2026-02-31T00:00:00Z",
        "2026-10-04T00:00:00",
        "2026-10-04T00:00:00+00:00",
        "2026-10-04 00:00:00Z",
        "2026-10-04T24:00:00Z",
        "2026-10-04T00:00:00.1234567Z",
        "2026-10-04T00:00:00Z\n",
    ):
        assert parse_utc_timestamp(bad) is None, bad


def test_error_codes_are_a_closed_set():
    with pytest.raises(AssertionError):
        AgentRegistryError("NOT_A_CONTRACT_CODE")
    error = AgentRegistryError("IDENTITY_MISMATCH", "x", cause="SPEC_REFERENCE_INVALID")
    assert error.code == "IDENTITY_MISMATCH" and error.cause == "SPEC_REFERENCE_INVALID"


def test_every_contract_failure_code_is_implemented():
    text = CONTRACT.read_text(encoding="utf-8")
    rows = re.findall(r"^\| ((?:AS|AE|AC)-\d\d) \|.*\| `([A-Z_]+)`", text, re.MULTILINE)
    # AS-05 lists its three codes in prose, so its row has no single code.
    expected_ids = {f"AS-{n:02d}" for n in range(1, 14)} - {"AS-05"}
    expected_ids |= {f"AE-{n:02d}" for n in range(1, 12)}
    expected_ids |= {f"AC-{n:02d}" for n in range(1, 7)}
    assert {rule_id for rule_id, _ in rows} == expected_ids
    for rule_id, code in rows:
        assert code in ERROR_CODES or code == "TIMESTAMP_REGRESSION", (rule_id, code)
    for code in (
        "FORBIDDEN_AUTHORITY_REQUESTED",
        "RESERVED_CAPABILITY",
        "UNKNOWN_CAPABILITY",
        "AGENT_SPEC_PROVENANCE_CONFLICT",
        "AGENT_SPEC_ID_COLLISION_OR_CORRUPTION",
    ):
        assert code in ERROR_CODES
