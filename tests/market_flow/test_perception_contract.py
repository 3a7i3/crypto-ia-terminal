"""CH1-01 perception contract V1: closed records, quality vocabulary, native-state mapping.

Synthetic, offline. Nothing here is provider output or runtime proof.
"""

import copy
import json

import pytest

from observability.market_flow import perception as pc

SHA = "a" * 64


def raw_event(**over):
    doc = {
        "schema_version": "1", "session_id": "S-SYNTH-1", "venue": "kraken", "market_type": "SPOT",
        "native_symbol": "BTC/USDT", "channel": "book", "kind": "BOOK_UPDATE", "receipt_seq": "7",
        "receive_utc_ns": "1795000000123456789", "receive_mono_ns": "5000000001",
        "native_time": "2026-11-20T07:06:33.123456Z", "native_sequence": None,
        "offset_bytes": "1024", "length_bytes": "311", "payload_sha256": SHA,
    }
    doc.update(over)
    return doc


def trade(**over):
    doc = {"schema_version": "1", "receipt_seq": "8", "item_index": "0", "trade_id": None,
           "price": "61917.6", "quantity": "0.0021", "aggressor_side": "UNKNOWN", "side_basis": "UNKNOWN"}
    doc.update(over)
    return doc


def depth(**over):
    doc = {"schema_version": "1", "receipt_seq": "9", "item_index": "0", "operation": "UPDATE",
           "bids": [["61917.6", "0"]], "asks": [["61918.1", "0.5"]], "checksum": "3164358270",
           "native_sequence": None}
    doc.update(over)
    return doc


def book(**over):
    doc = {"schema_version": "1", "as_of_receipt_seq": "12", "last_book_receipt_seq": "9",
           "subscribed_depth": "10", "bids": [["61917.6", "1.2"], ["61917.5", "0.3"]],
           "asks": [["61918.1", "0.5"], ["61918.4", "2"]], "native_state": "VALID", "native_reason": None}
    doc.update(over)
    return doc


def q(state="VERIFIED", reason=None, seq=None):
    return {"state": state, "reason": reason, "evidence_receipt_seq": seq}


def report(**over):
    doc = {"schema_version": "1", "as_of_receipt_seq": "12", "evidence_kind": "HISTORICAL",
           "book_integrity": q(seq="9"), "book_freshness": q("UNKNOWN", "FRESHNESS_UNKNOWN"),
           "trade_coverage": q("UNKNOWN", "TRADE_CHANNEL_NOT_CAPTURED"),
           "event_time_quality": q("UNRESOLVED", "CLOCK_ATTESTATION_INSUFFICIENT")}
    doc.update(over)
    return doc


BUILDERS = {"RAW_EVENT": raw_event, "NORMALIZED_TRADE": trade, "DEPTH_UPDATE": depth,
            "BOOK_STATE": book, "QUALITY_REPORT": report}


def refused(record_type, doc, code):
    with pytest.raises(pc.PerceptionRefusal) as err:
        pc.validate_record(record_type, doc)
    assert str(err.value).split(":")[0] == code, str(err.value)


# ------------------------------------------------------------------ closed records


@pytest.mark.parametrize("record_type", sorted(BUILDERS))
def test_valid_records_pass_and_keys_are_exactly_the_contract(record_type):
    doc = BUILDERS[record_type]()
    assert pc.validate_record(record_type, doc) is doc
    assert set(doc) == pc.RECORD_KEYS[record_type]


@pytest.mark.parametrize("record_type", sorted(BUILDERS))
def test_every_key_is_mandatory_and_unknown_keys_are_refused(record_type):
    for key in pc.RECORD_KEYS[record_type]:
        doc = BUILDERS[record_type]()
        del doc[key]
        refused(record_type, doc, "MISSING_KEY")
    refused(record_type, {**BUILDERS[record_type](), "extra": "1"}, "UNKNOWN_KEY")


@pytest.mark.parametrize("record_type", sorted(BUILDERS))
def test_schema_version_is_the_string_one(record_type):
    for bad in ("2", 1, None):
        refused(record_type, BUILDERS[record_type](schema_version=bad), "SCHEMA_VERSION_REFUSED")


def test_undeclared_record_type_is_refused():
    with pytest.raises(pc.PerceptionRefusal, match="RECORD_TYPE_REFUSED"):
        pc.validate_record("BOOK", book())


def test_strict_json_refuses_duplicates_fractions_and_nonfinite():
    assert pc.strict_loads(b'{"a":"1.5","b":7}') == {"a": "1.5", "b": 7}
    for raw, code in ((b'{"a":"1","a":"2"}', "DUPLICATE_KEY"), (b'{"a":1.5}', "JSON_NUMBER_FRACTION_REFUSED"),
                      (b'{"a":NaN}', "NONFINITE_JSON"), (b'{"a":Infinity}', "NONFINITE_JSON"),
                      (b"\xff", "INVALID_JSON"), (b"", "BOUNDED_BYTES_REQUIRED")):
        with pytest.raises(pc.PerceptionRefusal, match=code):
            pc.strict_loads(raw)


def test_round_trip_through_strict_json_keeps_values_exact():
    for record_type, build in BUILDERS.items():
        doc = build()
        again = pc.strict_loads(json.dumps(doc).encode())
        assert pc.validate_record(record_type, again) == doc


# ------------------------------------------------------------------ nullables and numbers


def test_nullables_accept_null_and_null_is_never_zero():
    pc.validate_record("RAW_EVENT", raw_event(channel=None, native_time=None, native_sequence=None))
    pc.validate_record("NORMALIZED_TRADE", trade(trade_id=None))
    pc.validate_record("DEPTH_UPDATE", depth(checksum=None, native_sequence=None))
    pc.validate_record("BOOK_STATE", book(last_book_receipt_seq=None, bids=None, asks=None,
                                          native_state="NOT_INITIALIZED"))
    # Non-nullable keys refuse null instead of reading it as 0.
    refused("RAW_EVENT", raw_event(receipt_seq=None), "UNSIGNED_INTEGER_STRING_REQUIRED")
    refused("NORMALIZED_TRADE", trade(price=None), "DECIMAL_STRING_REQUIRED")
    refused("BOOK_STATE", book(subscribed_depth=None), "UNSIGNED_INTEGER_STRING_REQUIRED")


@pytest.mark.parametrize("bad", [7, "-1", "01", "1.0", "1e3", " 1", "١", True, "9" * 31])
def test_counters_and_times_are_unsigned_integer_strings(bad):
    refused("RAW_EVENT", raw_event(receive_utc_ns=bad), "UNSIGNED_INTEGER_STRING_REQUIRED")


def test_large_nanosecond_times_keep_their_value_as_strings():
    big = "123456789012345678901234567890"  # beyond 2**53 and 2**64
    pc.validate_record("RAW_EVENT", raw_event(receive_utc_ns=big, receive_mono_ns=big))


@pytest.mark.parametrize("bad", ["1e3", "1E-2", "-1", "+1", ".5", "5.", "NaN", "Infinity", "١", 1, None])
def test_prices_and_quantities_are_finite_decimal_strings_without_exponent(bad):
    refused("NORMALIZED_TRADE", trade(price=bad), "DECIMAL_STRING_REQUIRED")
    refused("DEPTH_UPDATE", depth(asks=[["61918.1", bad]]), "DECIMAL_STRING_REQUIRED")


def test_positivity_rules():
    refused("NORMALIZED_TRADE", trade(price="0"), "POSITIVE_REQUIRED")
    refused("NORMALIZED_TRADE", trade(quantity="0.000"), "POSITIVE_REQUIRED")
    refused("DEPTH_UPDATE", depth(bids=[["0", "1"]]), "POSITIVE_REQUIRED")
    pc.validate_record("DEPTH_UPDATE", depth(bids=[["61917.6", "0"]]))  # zero size removes a level
    refused("BOOK_STATE", book(subscribed_depth="0"), "POSITIVE_REQUIRED")


def test_native_time_keeps_its_original_form():
    pc.validate_record("RAW_EVENT", raw_event(native_time=1795000000123))
    pc.validate_record("RAW_EVENT", raw_event(native_time="1795000000.123"))
    for bad in (True, ["x"], {"t": 1}):
        refused("RAW_EVENT", raw_event(native_time=bad), "NATIVE_TIME_ORIGINAL_FORM_REQUIRED")


def test_raw_event_sha256_and_text_fields():
    refused("RAW_EVENT", raw_event(payload_sha256="A" * 64), "SHA256_HEX_REQUIRED")
    refused("RAW_EVENT", raw_event(payload_sha256="a" * 63), "SHA256_HEX_REQUIRED")
    refused("RAW_EVENT", raw_event(venue=""), "TEXT_REQUIRED")
    refused("RAW_EVENT", raw_event(native_symbol="BTC\nUSDT"), "TEXT_REQUIRED")


# ------------------------------------------------------------------ trades and depth


def test_aggressor_side_and_basis_are_unknown_together():
    pc.validate_record("NORMALIZED_TRADE", trade(aggressor_side="BUY", side_basis="TAKER"))
    pc.validate_record("NORMALIZED_TRADE", trade(aggressor_side="SELL", side_basis="MAKER_INVERTED"))
    refused("NORMALIZED_TRADE", trade(aggressor_side="BUY", side_basis="UNKNOWN"), "AGGRESSOR_BASIS_INCONSISTENT")
    refused("NORMALIZED_TRADE", trade(aggressor_side="UNKNOWN", side_basis="TAKER"), "AGGRESSOR_BASIS_INCONSISTENT")
    refused("NORMALIZED_TRADE", trade(aggressor_side="buy", side_basis="TAKER"), "VALUE_NOT_ALLOWED")


def test_depth_levels_are_pairs_of_strings():
    for bad in ([["1"]], [["1", "2", "3"]], [("1", "2")], "1,2", None):
        with pytest.raises(pc.PerceptionRefusal):
            pc.validate_record("DEPTH_UPDATE", depth(bids=bad))
    refused("DEPTH_UPDATE", depth(operation="DELTA"), "VALUE_NOT_ALLOWED")
    pc.validate_record("DEPTH_UPDATE", depth(operation="SNAPSHOT", bids=[], asks=[]))


# ------------------------------------------------------------------ book state


def test_book_sides_are_null_together():
    refused("BOOK_STATE", book(bids=None), "BOOK_SIDES_NULL_TOGETHER")


def test_published_book_is_sorted_bounded_and_without_zero():
    refused("BOOK_STATE", book(bids=[["61917.5", "1"], ["61917.6", "1"]]), "SIDE_NOT_STRICTLY_SORTED")
    refused("BOOK_STATE", book(asks=[["61918.4", "1"], ["61918.1", "1"]]), "SIDE_NOT_STRICTLY_SORTED")
    refused("BOOK_STATE", book(asks=[["61918.1", "1"], ["61918.10", "1"]]), "SIDE_NOT_STRICTLY_SORTED")
    refused("BOOK_STATE", book(subscribed_depth="1"), "DEPTH_EXCEEDED")
    refused("BOOK_STATE", book(bids=[["61917.6", "0"]]), "POSITIVE_REQUIRED")
    refused("BOOK_STATE", book(bids=[]), "VERIFIED_BOOK_REQUIRES_SIDES_AND_RECEIPT")
    refused("BOOK_STATE", book(bids=None, asks=None), "VERIFIED_BOOK_REQUIRES_SIDES_AND_RECEIPT")
    refused("BOOK_STATE", book(last_book_receipt_seq=None), "VERIFIED_BOOK_REQUIRES_SIDES_AND_RECEIPT")
    refused("BOOK_STATE", book(last_book_receipt_seq="0"), "VERIFIED_BOOK_REQUIRES_SIDES_AND_RECEIPT")


@pytest.mark.parametrize("ask", ["61917.6", "61917.60", "61900"])
def test_crossed_or_locked_book_is_refused(ask):
    refused("BOOK_STATE", book(asks=[[ask, "1"]]), "CROSSED_OR_LOCKED_BOOK")


def test_book_receipt_bound():
    refused("BOOK_STATE", book(last_book_receipt_seq="13"), "RECEIPT_AFTER_AS_OF")
    pc.validate_record("BOOK_STATE", book(last_book_receipt_seq="12"))


# ------------------------------------------------------------------ quality report


def test_quality_states_are_the_contract_vocabulary():
    assert pc.QUALITY_STATES == {"VERIFIED", "DEGRADED", "RESYNCING", "INVALID", "UNKNOWN",
                                 "NOT_AVAILABLE", "UNRESOLVED"}
    refused("QUALITY_REPORT", report(book_integrity=q("LIVE", "X")), "VALUE_NOT_ALLOWED")
    refused("QUALITY_REPORT", report(book_integrity=q("VALID", None)), "VALUE_NOT_ALLOWED")


@pytest.mark.parametrize("state", sorted(pc.QUALITY_STATES - {"VERIFIED"}))
def test_every_state_other_than_verified_carries_a_reason(state):
    refused("QUALITY_REPORT", report(trade_coverage=q(state, None)), "REASON_REQUIRED")
    pc.validate_record("QUALITY_REPORT", report(trade_coverage=q(state, "SOME_REASON")))


def test_quality_result_shape_and_bound():
    refused("QUALITY_REPORT", report(book_integrity={"state": "VERIFIED", "reason": None}), "MISSING_KEY")
    refused("QUALITY_REPORT", report(book_integrity=q(seq="13")), "RECEIPT_AFTER_AS_OF")
    refused("QUALITY_REPORT", report(book_integrity=q("INVALID", "lower case")), "CODE_REQUIRED")


def test_evidence_kind_is_synthetic_or_historical_never_live():
    pc.validate_record("QUALITY_REPORT", report(evidence_kind="SYNTHETIC"))
    for bad in ("LIVE", "PAPER", None):
        refused("QUALITY_REPORT", report(evidence_kind=bad), "VALUE_NOT_ALLOWED")


def test_validators_never_mutate_their_input():
    for record_type, build in BUILDERS.items():
        doc = build()
        before = copy.deepcopy(doc)
        pc.validate_record(record_type, doc)
        assert doc == before


# ------------------------------------------------------------------ native-state mapping


def proj(origin, state, reason=None, **kw):
    return pc.project_native_state(origin, state, reason, **kw)


def states(p):
    return {dim: (r["state"], r["reason"]) for dim, r in p["projections"].items()}


def test_every_native_state_of_both_origins_has_a_projection():
    assert pc.BBO_NATIVE_STATES == {"VALID", "UNCHANGED_VERIFIED", "FRESHNESS_UNKNOWN", "CONTINUITY_LOST",
                                    "BOOK_INVALID", "NOT_INITIALIZED", "SOURCE_UNAVAILABLE"}
    assert pc.FLUX_L2_NATIVE_STATES == {"NO_SNAPSHOT", "INVALID", "LIVE"}
    for origin, natives in pc.ORIGINS.items():
        for native in natives:
            p = proj(origin, native)
            assert p["projections"] and set(p["projections"]) <= set(pc.QUALITY_DIMENSIONS)
            for result in p["projections"].values():
                pc.validate_quality_result(result)


def test_native_states_match_the_existing_engines():
    from observability.radar_composite import bbo_book

    assert set(bbo_book.SOURCE_STATES) <= pc.BBO_NATIVE_STATES
    assert {bbo_book.NOT_INITIALIZED, bbo_book.CONTINUITY_LOST} <= pc.BBO_NATIVE_STATES


def test_bbo_valid_and_unchanged_are_verified_and_keep_their_distinction():
    a, b = proj("BBO", "VALID"), proj("BBO", "UNCHANGED_VERIFIED")
    assert states(a) == states(b) == {"book_integrity": ("VERIFIED", None)}
    assert (a["native_state"], b["native_state"]) == ("VALID", "UNCHANGED_VERIFIED")
    assert "book_freshness" not in a["projections"]  # freshness is not asserted by these states


def test_bbo_freshness_unknown_needs_reconstruction_evidence_for_integrity():
    assert states(proj("BBO", "FRESHNESS_UNKNOWN")) == {
        "book_integrity": ("UNKNOWN", "RECONSTRUCTION_EVIDENCE_NOT_SUPPLIED"),
        "book_freshness": ("UNKNOWN", "FRESHNESS_UNKNOWN")}
    p = proj("BBO", "FRESHNESS_UNKNOWN", reconstruction_integrity="VERIFIED", evidence_receipt_seq="40")
    assert states(p)["book_integrity"] == ("VERIFIED", None)
    assert p["projections"]["book_integrity"]["evidence_receipt_seq"] == "40"


def test_bbo_continuity_lost_is_invalid_then_resyncing_once_recovery_is_engaged():
    assert states(proj("BBO", "CONTINUITY_LOST", "VERSION_GAP")) == {"book_integrity": ("INVALID", "VERSION_GAP")}
    assert states(proj("BBO", "CONTINUITY_LOST", "VERSION_GAP", resync_engaged=True)) == {
        "book_integrity": ("RESYNCING", "VERSION_GAP")}


def test_bbo_invalid_not_initialized_and_source_unavailable():
    assert states(proj("BBO", "BOOK_INVALID")) == {"book_integrity": ("INVALID", "BOOK_INVALID")}
    assert states(proj("BBO", "NOT_INITIALIZED")) == {"book_integrity": ("NOT_AVAILABLE", "NOT_INITIALIZED")}
    assert states(proj("BBO", "NOT_INITIALIZED", snapshot_expected=True)) == {
        "book_integrity": ("RESYNCING", "NOT_INITIALIZED")}
    assert states(proj("BBO", "SOURCE_UNAVAILABLE")) == {
        "book_integrity": ("NOT_AVAILABLE", "SOURCE_UNAVAILABLE"),
        "book_freshness": ("NOT_AVAILABLE", "SOURCE_UNAVAILABLE")}


def test_flux_l2_mapping_and_live_is_only_a_candidate():
    assert states(proj("FLUX_L2", "NO_SNAPSHOT")) == {"book_integrity": ("NOT_AVAILABLE", "NO_SNAPSHOT")}
    assert states(proj("FLUX_L2", "NO_SNAPSHOT", snapshot_expected=True)) == {
        "book_integrity": ("RESYNCING", "NO_SNAPSHOT")}
    assert states(proj("FLUX_L2", "INVALID", "SEQUENCE_GAP")) == {"book_integrity": ("INVALID", "SEQUENCE_GAP")}
    assert states(proj("FLUX_L2", "LIVE")) == {"book_integrity": ("UNKNOWN", "RECONSTRUCTION_EVIDENCE_NOT_ADMITTED")}
    assert states(proj("FLUX_L2", "LIVE", reconstruction_integrity="VERIFIED")) == {
        "book_integrity": ("VERIFIED", None)}
    assert "book_freshness" not in proj("FLUX_L2", "LIVE", reconstruction_integrity="VERIFIED")["projections"]


def test_native_code_and_reason_stay_attached_and_free_text_falls_back_to_the_code():
    p = proj("FLUX_L2", "INVALID", "crossed or locked (free text)")
    assert p["native_reason"] == "crossed or locked (free text)"
    assert states(p) == {"book_integrity": ("INVALID", "INVALID")}


def test_mapping_refuses_unknown_inputs():
    for args, kw, code in ((("MEXC", "VALID"), {}, "ORIGIN_REFUSED"),
                           (("BBO", "LIVE"), {}, "NATIVE_STATE_REFUSED"),
                           (("FLUX_L2", "VALID"), {}, "NATIVE_STATE_REFUSED"),
                           (("BBO", "VALID", ""), {}, "NATIVE_REASON_REFUSED"),
                           (("BBO", "VALID"), {"reconstruction_integrity": "OK"}, "RECONSTRUCTION_INTEGRITY_REFUSED"),
                           (("BBO", "VALID"), {"resync_engaged": 1}, "FLAG_REFUSED")):
        with pytest.raises(pc.PerceptionRefusal, match=code):
            pc.project_native_state(*args, **kw)
    with pytest.raises(pc.PerceptionRefusal, match="UNSIGNED_INTEGER_STRING_REQUIRED"):
        pc.project_native_state("BBO", "VALID", evidence_receipt_seq=3)


def test_projection_is_deterministic():
    runs = {json.dumps(proj(o, s, reason="R", evidence_receipt_seq="1"), sort_keys=True)
            for o, natives in pc.ORIGINS.items() for s in natives for _ in range(2)}
    assert len(runs) == sum(len(n) for n in pc.ORIGINS.values())


@pytest.mark.parametrize("identity", [
    ("mexc", "SPOT", "BTC/USDT", "BTC", "USDT"),
    ("kraken", "PERP", "BTC/USDT", "BTC", "USDT"),
    ("kraken", "SPOT", "BTC/USDT", "BTC", "USD"),
    ("kraken", "SPOT", "BTC/USDT", "ETH", "USDT"),
    ("kraken", "SPOT", "BTC/BTC", "BTC", "BTC"),
])
def test_kraken_spot_identity_requires_coherent_market(identity):
    with pytest.raises(pc.PerceptionRefusal, match="KRAKEN_SPOT_IDENTITY_MISMATCH"):
        pc.validate_kraken_spot_identity(*identity)


def test_kraken_spot_units_and_independent_manifest_reference():
    assert pc.validate_kraken_spot_identity("kraken", "SPOT", "BTC/USDT", "BTC", "USDT") == {
        "quantity_unit": "BTC", "price_quote_unit": "USDT",
    }
    corpus = "BBO-BTC-20261120T070632Z"
    admitted = "9ee3185daaf05faf646686466d6faf18374ba54ade5ae30a1bf883b3f58da910"
    pc.require_admitted_kraken_manifest(corpus, admitted)
    for corpus_id, digest in ((corpus, "0" * 64), ("other", admitted)):
        with pytest.raises(pc.PerceptionRefusal, match="HISTORICAL_MANIFEST_NOT_ADMITTED"):
            pc.require_admitted_kraken_manifest(corpus_id, digest)


def test_kraken_spot_unit_declarations_agree_with_derived_units():
    identity = ("kraken", "SPOT", "BTC/USDT", "BTC", "USDT")
    units = {"quantity_unit": "BTC", "price_quote_unit": "USDT"}
    assert pc.validate_kraken_spot_identity(*identity, unit_declarations=(
        ("instrument", {**units, "price_unit": "USDT/BTC"}),
    )) == units
    assert pc.validate_kraken_spot_identity(*identity) == units


@pytest.mark.parametrize("field,value,reason", [
    ("quantity_unit", "CONTRACTS", "KRAKEN_UNIT_MISMATCH"),
    ("quantity_unit", "ETH", "KRAKEN_UNIT_MISMATCH"),
    ("price_unit", "USD/BTC", "KRAKEN_UNIT_MISMATCH"),
    ("price_quote_unit", "USD", "KRAKEN_UNIT_MISMATCH"),
    ("quantity_unit", None, "KRAKEN_UNIT_MALFORMED"),
    ("price_unit", [], "KRAKEN_UNIT_MALFORMED"),
    ("amount_unit", "BTC", "KRAKEN_UNIT_FIELD_UNKNOWN"),
])
def test_kraken_spot_refuses_unrecognized_or_conflicting_unit_fields(field, value, reason):
    with pytest.raises(pc.PerceptionRefusal, match=rf"^{reason}:instrument\.{field}$"):
        pc.validate_kraken_spot_identity("kraken", "SPOT", "BTC/USDT", "BTC", "USDT",
                                        unit_declarations=(("instrument", {field: value}),))
