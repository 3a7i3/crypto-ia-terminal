"""Purely synthetic D1-E evidence: failures, unknowns, custody limits and rotation."""
import hashlib
import json
from copy import deepcopy

import pytest

from research_data.stress_d1_durability import verify_durability_chains
from research_data.stress_d1_evidence_contract import EvidenceIntegrityError


BOUNDARY = {
    "paper_epoch_id": "SYNTHETIC-EPOCH", "code_sha": "a" * 40,
    "config_sha256": "b" * 64, "dataset_id": "synthetic-dataset",
    "source_boundary_id": "synthetic-boundary", "window_start": "2026-10-10T00:00:00Z",
    "window_end": "2026-10-11T00:00:00Z", "capture_cutoff": "2026-10-11T00:01:00Z",
}
EARLY = "2026-10-10T23:59:59Z"
LATE = "2026-10-11T00:00:00Z"
FLAGS = {"actionable": True, "safe_mode": False, "bus_configured": True,
         "listener_registered": True}
CRITERIA = {"actionable": True, "trade_allowed": False, "side": "BUY",
            "provenance_valid": True, "symbol": "BTC", "price": 100.0}
SUCCESS = ["OBSERVATION_BUILD_ATTEMPT", "BUILD_OK", "PUBLICATION_ATTEMPT", "SUBMITTED",
           "LISTENER_DISPATCH", "STARTED", "FILTER_ELIGIBLE", "PERSIST_ATTEMPT",
           "RECORD_VALIDATE_PASS", "WRITE_APPEND", "FLUSH", "FSYNC_RETURN",
           "PERSIST_SUCCESS", "RETURNED"]


def data(stages=SUCCESS, *, write_at=LATE, fsync_at=LATE):
    identity = {"attempt_id": "a1", "packet_id": "p1", "trace_id": "t1", "decision_id": "d1"}
    base = {"boundary": deepcopy(BOUNDARY), **identity}
    line = json.dumps({"packet_id": "p1", "trace_id": "t1", "observation_id": "o1",
                       "symbol": "BTC", "side": "BUY", "price": 100.0,
                       "ts_iso": EARLY}) + "\n"
    write = {"file_id": "synthetic-device-inode-generation", "write_date_utc": write_at[:10],
             "partition_selected_at": write_at, "partition_name": f"rejections_{write_at[:10]}.jsonl",
             "byte_start": 0, "byte_end": len(line.encode()),
             "record_sha256": hashlib.sha256(line.encode()).hexdigest()}
    receipts = []
    for sequence, stage in enumerate(stages, 1):
        at = (write_at if stage == "WRITE_APPEND" else fsync_at if stage in
              {"FLUSH", "FSYNC_RETURN", "PERSIST_SUCCESS", "RETURNED", "THREW"} else EARLY)
        receipts.append({**deepcopy(base), "source_id": "producer-receipt-ledger",
                         "receipt_id": f"receipt-{sequence}", "sequence": sequence,
                         "stage": stage, "at": at, "observation_id": "o1",
                         "producer_flags": deepcopy(FLAGS), "criteria": deepcopy(CRITERIA),
                         "reason": "SYNTHETIC_FAILURE", "write": deepcopy(write),
                         "fsync_call_id": "fsync-1", "listener_id": "native-store-listener-1",
                         "listener_kind": "REJECTION_STORE"})
    return {
        "roster": [{**deepcopy(base), "source_id": "independent-packet-roster", "event_time": EARLY}],
        "receipts": receipts,
        "records": [{**deepcopy(base), "source_id": "independent-record-capture",
                     "observation_id": "o1", "write": deepcopy(write), "record_line": line}]
                   if "WRITE_APPEND" in stages else [],
        "fsync": [{**deepcopy(base), "source_id": "independent-fsync-witness",
                   "observation_id": "o1", "write": deepcopy(write), "fsync_call_id": "fsync-1",
                   "fd_file_id": write["file_id"], "outcome": "RETURNED", "at": fsync_at}]
                 if "FSYNC_RETURN" in stages else [],
        "fence": {"at": BOUNDARY["capture_cutoff"], "queue_state": "QUIESCENT",
                  "prefixes": [{"file_id": write["file_id"], "byte_end": write["byte_end"],
                                "sha256": write["record_sha256"]}]},
    }


def arguments(d):
    encoded = {name: json.dumps({"boundary": BOUNDARY, "rows": d[name]}).encode()
               for name in ("roster", "receipts", "records", "fsync")}
    return {"roster_bytes": encoded["roster"], "receipt_bytes": encoded["receipts"],
            "record_bytes": encoded["records"], "fsync_witness_bytes": encoded["fsync"],
            "expected_hashes": {k: hashlib.sha256(v).hexdigest() for k, v in encoded.items()},
            "boundary": BOUNDARY, "fence": d["fence"]}


def run(d):
    return verify_durability_chains(**arguments(d))


def receipt(d, stage):
    return next(r for r in d["receipts"] if r["stage"] == stage)


def assert_category(d, category):
    result = run(d)
    assert result["counts"][category] == 1
    assert sum(result["counts"].values()) == result["packet_roster_entries"]
    assert result["actual_persistence_proof"] == "NOT_OBSERVED"
    assert result["per_packet_durability"] == "NOT_PROVEN"
    assert result["paper_stress_runtime_go"] == "DENIED"
    return result


def test_complete_synthetic_chain_is_never_runtime_certified():
    result = assert_category(data(), "FSYNC_CHAIN_CONSISTENT")
    assert result["matched_fsync_witnesses"] == 1
    assert result["decisions"][0]["late_receipt"]
    for field in ("native_epoch_binding", "producer_completeness", "window_completeness",
                  "crash_durability", "directory_metadata_durability"):
        assert result[field] == "NOT_PROVEN"
    assert result["receipt_source_independence"] == "NOT_VERIFIED"


def test_midnight_rotation_uses_write_date_not_event_date():
    d = data(write_at=LATE)
    assert d["roster"][0]["event_time"][:10] != d["records"][0]["write"]["write_date_utc"]
    assert_category(d, "FSYNC_CHAIN_CONSISTENT")


def test_fsync_can_cross_midnight_without_rotating_the_open_file():
    assert_category(data(write_at=EARLY, fsync_at=LATE), "FSYNC_CHAIN_CONSISTENT")


def test_path_selected_before_midnight_can_be_appended_after_midnight():
    d = data(write_at=EARLY, fsync_at=LATE)
    receipt(d, "WRITE_APPEND")["at"] = LATE
    assert_category(d, "FSYNC_CHAIN_CONSISTENT")


@pytest.mark.parametrize("stages,category", [
    ([], "MISSING_CHAIN"), (SUCCESS[:4], "INCOMPLETE_CHAIN"),
    (SUCCESS[:1] + ["BUILD_FAILED"], "BUILD_FAILED"),
    (SUCCESS[:2] + ["NOT_PUBLISHED"], "NOT_PUBLISHED"),
    (SUCCESS[:3] + ["DROPPED"], "PUBLICATION_DROPPED"),
    (SUCCESS[:4] + ["NOT_DELIVERED"], "NOT_DELIVERED"),
    (SUCCESS[:8] + ["PERSIST_FALSE", "RETURNED"], "PERSIST_FALSE"),
    (SUCCESS[:8] + ["PERSIST_THREW", "THREW"], "PERSIST_THREW"),
    (SUCCESS[:9] + ["APPEND_ERROR", "PERSIST_FALSE", "RETURNED"], "PERSIST_FALSE"),
    (SUCCESS[:10] + ["FLUSH_ERROR", "PERSIST_FALSE", "RETURNED"], "PERSIST_FALSE"),
    (SUCCESS[:11] + ["FSYNC_ERROR", "PERSIST_FALSE", "RETURNED"], "PERSIST_FALSE"),
    (SUCCESS[:6] + ["THREW"], "LISTENER_THREW"),
    (SUCCESS[:12] + ["PERSIST_FALSE", "RETURNED"], "FSYNC_ACK_WITH_PERSIST_FAILURE"),
])
def test_negative_terminal_and_incomplete_paths(stages, category):
    d = data(stages, write_at=EARLY, fsync_at=EARLY)
    result = assert_category(d, category)
    if category == "PERSIST_FALSE":
        assert result["matched_fsync_witnesses"] == 0


def test_listener_return_after_persist_false_is_not_durable():
    d = data(SUCCESS[:8] + ["PERSIST_FALSE", "RETURNED"])
    result = assert_category(d, "PERSIST_FALSE")
    assert result["decisions"][0]["last_stage"] == "RETURNED"


@pytest.mark.parametrize("reason,flag,value,category", [
    ("SAFE_MODE", "safe_mode", True, "BUILD_NOT_ATTEMPTED"),
    ("NON_ACTIONABLE", "actionable", False, "BUILD_NOT_ATTEMPTED"),
    ("UNKNOWN_FLAGS", "safe_mode", None, "BUILD_STATE_UNKNOWN"),
])
def test_safe_mode_and_unknown_flags(reason, flag, value, category):
    d = data(["NOT_ATTEMPTED"])
    d["receipts"][0]["reason"] = reason
    d["receipts"][0]["producer_flags"][flag] = value
    assert_category(d, category)


def test_no_listener_is_distinct_from_shutdown_drop():
    d = data(SUCCESS[:2] + ["NOT_PUBLISHED"])
    d["receipts"][0]["producer_flags"]["listener_registered"] = False
    d["receipts"][-1]["reason"] = "NO_LISTENER"
    assert_category(d, "NOT_PUBLISHED")
    assert_category(data(SUCCESS[:3] + ["DROPPED"]), "PUBLICATION_DROPPED")


@pytest.mark.parametrize("field,value,stage,category", [
    ("actionable", False, "FILTERED_OUT", "FILTERED_OUT"),
    ("trade_allowed", True, "FILTERED_OUT", "FILTERED_OUT"),
    ("side", "HOLD", "FILTERED_OUT", "FILTERED_OUT"),
    ("provenance_valid", False, "FILTERED_OUT", "FILTERED_OUT"),
    ("actionable", None, "FILTER_UNKNOWN", "ELIGIBILITY_UNKNOWN"),
])
def test_native_filter_criteria(field, value, stage, category):
    d = data(SUCCESS[:6] + [stage, "RETURNED"])
    receipt(d, stage)["criteria"][field] = value
    assert_category(d, category)


@pytest.mark.parametrize("price,stage,category", [
    (0, "RECORD_VALIDATE_FAIL", "VALIDATION_FAILED"),
    (-1, "RECORD_VALIDATE_FAIL", "VALIDATION_FAILED"),
    (None, "VALIDATE_UNKNOWN", "VALIDATION_UNKNOWN"),
])
def test_price_validation_does_not_infer_eligibility(price, stage, category):
    d = data(SUCCESS[:8] + [stage, "PERSIST_FALSE", "RETURNED"])
    receipt(d, "FILTER_ELIGIBLE")["criteria"]["price"] = price
    assert_category(d, category)


@pytest.mark.parametrize("stage,field,value,reason", [
    ("FLUSH", "stage", "PERSIST_SUCCESS", "INVALID_STAGE_TRANSITION"),
    ("FSYNC_RETURN", "sequence", 10, "DUPLICATE_OR_GAPPED_CAUSAL_SEQUENCE"),
    ("BUILD_OK", "sequence", 0, "INVALID_CAUSAL_SEQUENCE"),
    ("BUILD_OK", "stage", None, "MISSING_STAGE_OUTCOME"),
    ("BUILD_OK", "packet_id", "other-packet", "NATIVE_CAUSAL_JOIN_MISMATCH"),
    ("BUILD_OK", "trace_id", "other-trace", "NATIVE_CAUSAL_JOIN_MISMATCH"),
    ("BUILD_OK", "decision_id", "other-decision", "NATIVE_CAUSAL_JOIN_MISMATCH"),
    ("FLUSH", "observation_id", "other-observation", "OBSERVATION_CAUSAL_JOIN_MISMATCH"),
    ("STARTED", "listener_id", "telegram-listener", "LISTENER_CAUSAL_JOIN_MISMATCH"),
    ("LISTENER_DISPATCH", "listener_kind", "TELEGRAM", "NOT_A_REJECTION_STORE_RECEIPT"),
    ("BUILD_OK", "at", "2026-10-10T23:59:58Z", "RECEIPT_OUTSIDE_CAPTURE_FENCE"),
    ("FSYNC_RETURN", "at", "2026-10-11T00:01:01Z", "RECEIPT_OUTSIDE_CAPTURE_FENCE"),
    ("BUILD_OK", "at", "2026-10-10T23:59:59", "NAIVE_OR_NON_UTC_TIME"),
    ("FSYNC_RETURN", "fsync_call_id", "invented-fsync", "FSYNC_CALL_JOIN_MISMATCH"),
])
def test_invalid_causal_claims(stage, field, value, reason):
    d = data()
    receipt(d, stage)[field] = value
    with pytest.raises(EvidenceIntegrityError, match=reason):
        run(d)


@pytest.mark.parametrize("role", ["records", "fsync"])
def test_fabricated_fsync_without_independent_evidence_is_rejected(role):
    d = data()
    d[role] = []
    with pytest.raises(EvidenceIntegrityError, match="FSYNC_CLAIM_WITHOUT_INDEPENDENT_EVIDENCE"):
        run(d)


def test_self_attestation_cannot_reuse_receipt_source_as_fsync_witness():
    d = data()
    d["fsync"][0]["source_id"] = d["receipts"][0]["source_id"]
    with pytest.raises(EvidenceIntegrityError, match="SELF_ATTESTED_EVIDENCE_SOURCE"):
        run(d)


@pytest.mark.parametrize("role", ["receipts", "records", "fsync"])
@pytest.mark.parametrize("field", list(BOUNDARY))
def test_each_boundary_field_is_enforced_across_every_stream(role, field):
    d = data()
    value = d[role][0]["boundary"][field]
    d[role][0]["boundary"][field] = ("c" * len(value) if "sha" in field else
                                      "2026-10-10T00:00:01Z" if field == "window_start" else
                                      "2026-10-11T00:00:01Z" if field == "window_end" else
                                      "2026-10-11T00:01:01Z" if field == "capture_cutoff" else "other")
    with pytest.raises(EvidenceIntegrityError, match="NATIVE_BOUNDARY_MISMATCH"):
        run(d)


@pytest.mark.parametrize("role,reason", [("roster", "AMBIGUOUS_NATIVE_IDENTITY"),
                                       ("receipts", "DUPLICATE_RECEIPT_ID"),
                                       ("records", "DUPLICATE_CAPTURED_RECORD"),
                                       ("fsync", "DUPLICATE_FSYNC_WITNESS")])
def test_duplicate_rows_abort(role, reason):
    d = data()
    d[role].append(deepcopy(d[role][0]))
    with pytest.raises(EvidenceIntegrityError, match=reason):
        run(d)


@pytest.mark.parametrize("field,value,reason", [
    ("fd_file_id", "another-file", "FSYNC_FD_FILE_MISMATCH"),
    ("outcome", "ERROR", "FSYNC_WITNESS_NOT_RETURNED"),
    ("observation_id", "other-observation", "WITNESS_OBSERVATION_MISMATCH"),
])
def test_physical_fsync_binding(field, value, reason):
    d = data()
    d["fsync"][0][field] = value
    with pytest.raises(EvidenceIntegrityError, match=reason):
        run(d)


def test_read_prefix_cutoff_rejects_record_after_captured_bytes():
    d = data()
    d["fence"]["prefixes"][0]["byte_end"] -= 1
    with pytest.raises(EvidenceIntegrityError, match="RECORD_OUTSIDE_READ_PREFIX"):
        run(d)


def test_rotation_date_cannot_be_inferred_from_observation_timestamp():
    d = data()
    receipt(d, "WRITE_APPEND")["write"]["write_date_utc"] = EARLY[:10]
    with pytest.raises(EvidenceIntegrityError, match="PHYSICAL_WRITE_DATE_MISMATCH"):
        run(d)


def test_utc_order_is_checked_independently_from_sequence():
    d = data()
    receipt(d, "BUILD_OK")["at"] = LATE
    with pytest.raises(EvidenceIntegrityError, match="CAUSAL_TIME_REVERSED"):
        run(d)


@pytest.mark.parametrize("state", ["UNKNOWN", "NOT_QUIESCENT"])
def test_unclosed_queue_fence_never_certifies_completeness(state):
    d = data()
    d["fence"]["queue_state"] = state
    result = assert_category(d, "FSYNC_CHAIN_CONSISTENT")
    assert result["declared_queue_state"] == state
    assert result["window_completeness"] == "NOT_PROVEN"


def test_hash_pin_detects_changed_bytes_without_repinning():
    args = arguments(data())
    args["receipt_bytes"] += b" "
    with pytest.raises(EvidenceIntegrityError, match="BUNDLE_HASH_MISMATCH"):
        verify_durability_chains(**args)


@pytest.mark.parametrize("raw,reason", [
    (b'{"boundary":{},"boundary":{},"rows":[]}', "DUPLICATE_JSON_KEY"),
    (b'{"boundary":NaN,"rows":[]}', "NONFINITE_JSON"),
    (b'\xff', "INVALID_BUNDLE_JSON"), (b'[]', "INVALID_BUNDLE_ENVELOPE"),
])
def test_ambiguous_or_non_json_bytes_fail_closed(raw, reason):
    args = arguments(data())
    args["roster_bytes"] = raw
    args["expected_hashes"]["roster"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(EvidenceIntegrityError, match=reason):
        verify_durability_chains(**args)


def test_mutable_bundle_and_empty_roster_are_not_zero_population():
    args = arguments(data())
    args["roster_bytes"] = bytearray(args["roster_bytes"])
    with pytest.raises(EvidenceIntegrityError, match="EXPLICIT_IMMUTABLE_BYTES_REQUIRED"):
        verify_durability_chains(**args)
    d = data()
    d["roster"] = []
    with pytest.raises(EvidenceIntegrityError, match="PACKET_ROSTER_NOT_AVAILABLE"):
        run(d)


def test_record_bytes_are_not_accepted_by_presence_alone():
    d = data()
    d["records"][0]["record_line"] = d["records"][0]["record_line"].replace('100.0', '101.0')
    with pytest.raises(EvidenceIntegrityError, match="RECORD_BYTES_HASH_OR_RANGE_MISMATCH"):
        run(d)


def test_truncated_receipts_and_present_record_stay_unknown():
    d = data()
    d["receipts"] = []
    d["fsync"] = []
    result = assert_category(d, "MISSING_CHAIN")
    assert result["records_without_fsync_chain"] == 1


def test_reordering_does_not_create_a_new_causal_order_or_mutate_inputs():
    d = data()
    before = deepcopy(d)
    result = run(d)
    d["receipts"].reverse()
    assert run(d) == result
    d["receipts"].reverse()
    assert d == before


@pytest.mark.parametrize("field,value,stage,reason", [
    ("actionable", 1, "FILTER_ELIGIBLE", "INVALID_NATIVE_FILTER_FLAG"),
    ("side", [], "FILTER_ELIGIBLE", "INVALID_NATIVE_SIDE"),
    ("symbol", [], "FILTER_ELIGIBLE", "INVALID_NATIVE_SYMBOL"),
    ("price", True, "FILTER_ELIGIBLE", "INVALID_NATIVE_PRICE"),
    ("price", None, "FILTER_ELIGIBLE", "VALIDATION_CLAIM_CONTRADICTION"),
    ("actionable", False, "FILTER_ELIGIBLE", "FILTER_CLAIM_CONTRADICTION"),
])
def test_filter_and_validation_claims_cannot_be_reinterpreted(field, value, stage, reason):
    d = data()
    receipt(d, stage)["criteria"][field] = value
    with pytest.raises(EvidenceIntegrityError, match=reason):
        run(d)


@pytest.mark.parametrize("field,value,reason", [
    ("safe_mode", True, "BUILD_ATTEMPT_CONTRADICTS_PRODUCER_FLAGS"),
    ("actionable", False, "BUILD_ATTEMPT_CONTRADICTS_PRODUCER_FLAGS"),
    ("bus_configured", False, "BUILD_ATTEMPT_CONTRADICTS_PRODUCER_FLAGS"),
    ("listener_registered", False, "DISPATCH_WITH_NO_LISTENER"),
    ("safe_mode", 0, "INVALID_PRODUCER_FLAG"),
])
def test_native_producer_flags_are_not_assumed_from_packets(field, value, reason):
    d = data()
    d["receipts"][0]["producer_flags"][field] = value
    with pytest.raises(EvidenceIntegrityError, match=reason):
        run(d)


def test_observed_chain_with_unavailable_flag_retains_unknown_flag():
    d = data()
    d["receipts"][0]["producer_flags"]["safe_mode"] = None
    result = assert_category(d, "FSYNC_CHAIN_CONSISTENT")
    assert result["decisions"][0]["producer_flags"] == "UNKNOWN"


def test_fsync_witness_is_not_backfilled_into_a_missing_chain():
    d = data()
    d["receipts"] = []
    with pytest.raises(EvidenceIntegrityError, match="UNMATCHED_FSYNC_WITNESS"):
        run(d)


def test_captured_record_cannot_contradict_a_proven_filter_exclusion():
    d = data(SUCCESS[:6] + ["FILTERED_OUT", "RETURNED"])
    receipt(d, "FILTERED_OUT")["criteria"]["actionable"] = False
    d["records"] = data()["records"]
    with pytest.raises(EvidenceIntegrityError, match="RECORD_CONTRADICTS_NON_PERSISTED_CHAIN"):
        run(d)


def test_record_payload_cannot_contradict_a_re_pinned_filter_claim():
    d = data()
    receipt(d, "FILTER_ELIGIBLE")["criteria"]["price"] = 200.0
    with pytest.raises(EvidenceIntegrityError, match="RECORD_FILTER_CRITERIA_MISMATCH"):
        run(d)


def test_unknown_builder_state_is_not_an_observed_skip():
    d = data(["BUILD_STATE_UNKNOWN"])
    d["receipts"][0]["producer_flags"] = dict.fromkeys(FLAGS)
    assert_category(d, "BUILD_STATE_UNKNOWN")


def test_multiple_independent_decisions_are_conserved():
    first, second = data(), data()
    identity_changes = {"attempt_id": "a2", "packet_id": "p2", "trace_id": "t2",
                        "decision_id": "d2", "observation_id": "o2", "fsync_call_id": "fsync-2"}
    for role in ("roster", "receipts", "records", "fsync"):
        for row in second[role]:
            for key, value in identity_changes.items():
                if key in row:
                    row[key] = value
            if "receipt_id" in row:
                row["receipt_id"] += "-second"
            if "write" in row:
                row["write"]["file_id"] += "-second"
            if "fd_file_id" in row:
                row["fd_file_id"] += "-second"
    row = second["records"][0]
    row["record_line"] = row["record_line"].replace('p1', 'p2').replace('t1', 't2').replace('o1', 'o2')
    digest = hashlib.sha256(row["record_line"].encode()).hexdigest()
    for role in ("receipts", "records", "fsync"):
        for row in second[role]:
            row["write"]["record_sha256"] = digest
    second["fence"]["prefixes"][0]["file_id"] += "-second"
    second["fence"]["prefixes"][0]["sha256"] = digest
    for role in ("roster", "receipts", "records", "fsync"):
        first[role].extend(second[role])
    first["fence"]["prefixes"].extend(second["fence"]["prefixes"])
    result = run(first)
    assert result["counts"]["FSYNC_CHAIN_CONSISTENT"] == 2
    assert sum(result["counts"].values()) == 2
    first["fsync"][1]["fsync_call_id"] = "fsync-1"
    with pytest.raises(EvidenceIntegrityError, match="DUPLICATE_NATIVE_FSYNC_CALL_ID"):
        run(first)


@pytest.mark.parametrize("number", ["1e400", "-1e400", "NaN", "Infinity", "-Infinity"])
def test_record_rejects_nonfinite_unused_value_with_consistent_bytes_and_fsync(number):
    # Do not produce a misleading SHA mismatch: repin exact record bytes,
    # all write receipts, the independent fsync witness and the prefix fence.
    d = data()
    previous_line = d["records"][0]["record_line"]
    assert '"price": 100.0,' in previous_line
    new_line = previous_line.replace(
        '"price": 100.0,', f'"price": 100.0, "unused_numeric": {number},', 1
    )
    encoded = new_line.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    d["records"][0]["record_line"] = new_line
    for row in [d["records"][0], d["fsync"][0], *d["receipts"]]:
        row["write"]["byte_end"] = len(encoded)
        row["write"]["record_sha256"] = digest
    d["fence"]["prefixes"][0]["byte_end"] = len(encoded)
    d["fence"]["prefixes"][0]["sha256"] = digest
    with pytest.raises(EvidenceIntegrityError, match="NONFINITE_RECORD_JSON"):
        run(d)


def test_record_allows_finite_extra_number_with_consistent_bytes_and_fsync():
    d = data()
    line = d["records"][0]["record_line"].replace(
        '"price": 100.0,', '"price": 100.0, "unused_numeric": 1.25,', 1
    )
    encoded = line.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    d["records"][0]["record_line"] = line
    for row in [d["records"][0], d["fsync"][0], *d["receipts"]]:
        row["write"]["byte_end"] = len(encoded)
        row["write"]["record_sha256"] = digest
    d["fence"]["prefixes"][0]["byte_end"] = len(encoded)
    d["fence"]["prefixes"][0]["sha256"] = digest
    assert_category(d, "FSYNC_CHAIN_CONSISTENT")
