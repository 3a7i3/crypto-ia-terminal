"""S4-a — SA2 (strict, bounded reading) and SA3 (seal verified).

Every malformed input is refused with a stable code; no other exception escapes.
"""
from __future__ import annotations

import json

import pytest

from observability.radar_projection import contract as pc
from observability.radar_projection.verifier import ProjectionRefusal, verify_export
from observability.radar_selection.fixture import canonical, sha256_hex
from tests.radar_projection._exports import export, loads, reseal


def refused(raw) -> str:
    with pytest.raises(ProjectionRefusal) as exc:
        verify_export(raw)
    return exc.value.code


@pytest.fixture(scope="module")
def good() -> bytes:
    return export("r0_syn_04_incoherent")


# ---------------------------------------------------------------- SA2: bytes and JSON
def test_SA2_export_with_and_without_final_newline_is_accepted(good):
    assert verify_export(good)["doc"]["schema_version"] == pc.EVALUATION_SCHEMA
    assert verify_export(good[:-1])["doc"] == verify_export(good)["doc"]


def test_SA2_bytearray_is_accepted(good):
    assert verify_export(bytearray(good))["export_sha256"] == sha256_hex(good)


@pytest.mark.parametrize("value", ["{}", None, 12, {"a": 1}])
def test_SA2_input_must_be_bytes(value):
    assert refused(value) == "INPUT_NOT_BYTES"


def test_SA2_empty_input():
    assert refused(b"") == "INPUT_EMPTY"


def test_SA2_size_is_bounded_before_parsing():
    assert refused(b" " * (pc.MAX_EXPORT_BYTES + 1)) == "INPUT_TOO_LARGE"


def test_SA2_size_bound_is_exactly_the_engine_output_bound_plus_newline():
    raw = b"{" + b" " * (pc.MAX_EXPORT_BYTES - 2) + b"}"
    assert len(raw) == pc.MAX_EXPORT_BYTES
    assert refused(raw) == "EVALUATION_SCHEMA_MISSING"  # read, then refused on content


@pytest.mark.parametrize("raw", [b"\xff\xfe{}", b'{"a":"\xc3\x28"}', b"\xef\xbb\xbf{}", b"{", b"[1,]",
                                 b"{\"a\":1}{\"b\":2}", b"{'a':1}"])
def test_SA2_invalid_utf8_bom_or_malformed_json(raw):
    assert refused(raw) == "INPUT_MALFORMED"


def test_SA2_duplicate_keys_are_refused_at_any_depth(good):
    text = good.decode()
    assert refused(b'{"schema_version":"radar-evaluation/1.2.0","schema_version":"x"}') == "DUPLICATE_KEY"
    nested = text.replace('"market_id":"kraken:spot:BTC/USDT"',
                          '"market_id":"kraken:spot:BTC/USDT","market_id":"mexc:spot:BTC/USDT"', 1)
    assert nested != text
    assert refused(nested.encode()) == "DUPLICATE_KEY"


@pytest.mark.parametrize("token,code", [("NaN", "NONFINITE_NUMBER"), ("Infinity", "NONFINITE_NUMBER"),
                                        ("-Infinity", "NONFINITE_NUMBER"), ("88.0", "FLOAT_NOT_ALLOWED"),
                                        ("1e3", "FLOAT_NOT_ALLOWED")])
def test_SA2_non_finite_and_float_numbers_are_refused(good, token, code):
    text = good.decode().replace('"evaluation_time_ms":', f'"evaluation_time_ms":{token},"x":', 1)
    assert refused(text.encode()) == code


def test_SA2_integer_beyond_interpreter_limit_is_a_typed_refusal():
    assert refused(b'{"a":' + b"9" * 5000 + b"}") == "INPUT_MALFORMED"


def test_SA2_deep_nesting_is_a_typed_refusal():
    assert refused(b"[" * 100_000 + b"]" * 100_000) == "INPUT_MALFORMED"


def test_SA2_lone_surrogate_cannot_be_canonicalised(good):
    d = loads(good)
    text = canonical({**d, "evaluation_sha256": "0" * 64}).decode().replace(
        '"description":"', '"description":"\\ud800', 1)
    assert refused(text.encode()) == "INPUT_MALFORMED"


@pytest.mark.parametrize("raw", [b"[]", b'"radar"', b"12", b"null", b"true"])
def test_SA2_top_level_must_be_an_object(raw):
    assert refused(raw) == "OBJECT_EXPECTED"


def test_SA2_non_canonical_bytes_are_refused_even_with_a_valid_seal(good):
    d = loads(good)
    pretty = json.dumps(d, indent=1, sort_keys=True, ensure_ascii=False).encode()
    assert refused(pretty) == "NOT_CANONICAL"
    unsorted = json.dumps(dict(reversed(list(d.items()))), separators=(",", ":"), ensure_ascii=False).encode()
    assert refused(unsorted) == "NOT_CANONICAL"
    ascii_escaped = json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    assert ascii_escaped != good[:-1]
    assert refused(ascii_escaped) == "NOT_CANONICAL"


@pytest.mark.parametrize("suffix", [b"\n\n", b"\r\n", b" ", b"\t"])
def test_SA2_only_one_final_newline_is_tolerated(good, suffix):
    assert refused(good[:-1] + suffix) == "NOT_CANONICAL"


# ---------------------------------------------------------------- SA3: seal
def test_SA3_seal_is_recomputed_with_the_radar_canonicalisation(good):
    d = loads(good)
    body = {k: v for k, v in d.items() if k != "evaluation_sha256"}
    assert sha256_hex(canonical(body)) == d["evaluation_sha256"]
    assert verify_export(good)["doc"]["evaluation_sha256"] == d["evaluation_sha256"]


def test_SA3_any_content_change_without_reseal_is_refused(good):
    d = loads(good)
    d["markets"][0]["lifecycle"]["recent_data"] = "FRESH"
    assert refused(canonical(d) + b"\n") == "SEAL_MISMATCH"


def test_SA3_a_single_character_change_is_refused(good):
    raw = good.replace(b'"value":"88.00"', b'"value":"89.00"', 1)
    assert raw != good
    assert refused(raw) == "SEAL_MISMATCH"


@pytest.mark.parametrize("seal", [None, "", "ABC", "0" * 63, "0" * 65, "G" * 64, 12])
def test_SA3_seal_format(good, seal):
    d = loads(good)
    d["evaluation_sha256"] = seal
    assert refused(canonical(d) + b"\n") == "SEAL_FORMAT"


def test_SA3_uppercase_seal_is_refused(good):
    d = loads(good)
    d["evaluation_sha256"] = d["evaluation_sha256"].upper()
    assert refused(canonical(d) + b"\n") == "SEAL_FORMAT"


def test_SA3_missing_seal(good):
    d = loads(good)
    del d["evaluation_sha256"]
    assert refused(canonical(d) + b"\n") == "SEAL_FORMAT"


def test_SA3_a_valid_seal_alone_does_not_make_a_valid_export(good):
    # Resealing a tampered document gives a correct SHA-256: the structure still refuses it.
    d = loads(good)
    d["authority"]["execution_authority"] = True
    raw = reseal(d)
    body = {k: v for k, v in loads(raw).items() if k != "evaluation_sha256"}
    assert sha256_hex(canonical(body)) == loads(raw)["evaluation_sha256"]
    assert refused(raw) == "AUTHORITY_INVARIANT"
