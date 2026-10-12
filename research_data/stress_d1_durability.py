"""D1-E pure receipt-chain verification over explicit, hash-pinned Research bytes.

Consistency of supplied evidence is SOURCE_PROOF, never runtime certification.
No disk, network, EventBus, RejectionStore or production imports are used here.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

from research_data.stress_d1_evidence_contract import (
    EvidenceIntegrityError,
    decode_bundle,
    native_id,
    require,
    utc_time,
    validate_boundary,
)

TRANSITIONS = {
    "ROOT": {"OBSERVATION_BUILD_ATTEMPT", "NOT_ATTEMPTED", "BUILD_STATE_UNKNOWN"},
    "OBSERVATION_BUILD_ATTEMPT": {"BUILD_OK", "BUILD_FAILED"},
    "BUILD_OK": {"PUBLICATION_ATTEMPT", "NOT_PUBLISHED"},
    "PUBLICATION_ATTEMPT": {"SUBMITTED", "DROPPED", "NOT_PUBLISHED"},
    "SUBMITTED": {"LISTENER_DISPATCH", "NOT_DELIVERED"},
    "LISTENER_DISPATCH": {"STARTED", "NOT_DELIVERED"},
    "STARTED": {"FILTER_ELIGIBLE", "FILTERED_OUT", "FILTER_UNKNOWN", "THREW"},
    "FILTER_ELIGIBLE": {"PERSIST_ATTEMPT", "THREW"},
    "FILTERED_OUT": {"RETURNED"},
    "FILTER_UNKNOWN": {"RETURNED", "THREW"},
    "PERSIST_ATTEMPT": {"RECORD_VALIDATE_PASS", "RECORD_VALIDATE_FAIL",
                        "VALIDATE_UNKNOWN", "PERSIST_FALSE", "PERSIST_THREW"},
    "RECORD_VALIDATE_PASS": {"WRITE_APPEND", "APPEND_ERROR", "PERSIST_FALSE", "PERSIST_THREW"},
    "RECORD_VALIDATE_FAIL": {"PERSIST_FALSE"},
    "VALIDATE_UNKNOWN": {"PERSIST_FALSE", "PERSIST_THREW"},
    "WRITE_APPEND": {"FLUSH", "FLUSH_ERROR", "PERSIST_FALSE", "PERSIST_THREW"},
    "FLUSH": {"FSYNC_RETURN", "FSYNC_ERROR", "PERSIST_FALSE", "PERSIST_THREW"},
    "APPEND_ERROR": {"PERSIST_FALSE", "PERSIST_THREW"},
    "FLUSH_ERROR": {"PERSIST_FALSE", "PERSIST_THREW"},
    "FSYNC_ERROR": {"PERSIST_FALSE", "PERSIST_THREW"},
    "FSYNC_RETURN": {"PERSIST_SUCCESS", "PERSIST_FALSE", "PERSIST_THREW"},
    "PERSIST_SUCCESS": {"RETURNED", "THREW"},
    "PERSIST_FALSE": {"RETURNED", "THREW"},
    "PERSIST_THREW": {"THREW"},
}
TERMINALS = frozenset({"NOT_ATTEMPTED", "BUILD_STATE_UNKNOWN", "BUILD_FAILED",
                       "NOT_PUBLISHED", "DROPPED", "NOT_DELIVERED", "RETURNED", "THREW"})
IDENTITY = ("attempt_id", "packet_id", "trace_id", "decision_id")
WRITE_FIELDS = ("file_id", "write_date_utc", "partition_selected_at", "partition_name",
                "byte_start", "byte_end", "record_sha256")
RESULTS = ("MISSING_CHAIN", "INCOMPLETE_CHAIN", "BUILD_NOT_ATTEMPTED", "BUILD_STATE_UNKNOWN",
           "BUILD_FAILED", "NOT_PUBLISHED", "PUBLICATION_DROPPED", "NOT_DELIVERED",
           "FILTERED_OUT", "ELIGIBILITY_UNKNOWN", "VALIDATION_FAILED", "VALIDATION_UNKNOWN",
           "PERSIST_FALSE", "PERSIST_THREW", "LISTENER_THREW", "LISTENER_RETURN_WITHOUT_FSYNC",
           "FSYNC_CHAIN_CONSISTENT", "FSYNC_ACK_WITH_PERSIST_FAILURE")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_RECORD_JSON_KEY")
        result[key] = value
    return result


def _criteria(row: Mapping[str, Any]) -> tuple[bool | None, bool | None]:
    """Frozen-source filter and stricter finite-price Research validation separately."""
    criteria = row.get("criteria")
    require(isinstance(criteria, Mapping), "FILTER_CRITERIA_NOT_AVAILABLE")
    for key in ("actionable", "trade_allowed", "provenance_valid"):
        require(criteria.get(key) is None or type(criteria[key]) is bool,
                "INVALID_NATIVE_FILTER_FLAG")
    side = criteria.get("side")
    require(side is None or isinstance(side, str), "INVALID_NATIVE_SIDE")
    facts = [criteria.get("actionable"),
             None if criteria.get("trade_allowed") is None else not criteria["trade_allowed"],
             None if side is None else side in {"BUY", "SELL", "LONG", "SHORT"},
             criteria.get("provenance_valid")]
    eligible = False if False in facts else None if None in facts else True
    price = criteria.get("price")
    require(price is None or (type(price) in (int, float) and math.isfinite(price)),
            "INVALID_NATIVE_PRICE")
    symbol = criteria.get("symbol")
    require(symbol is None or isinstance(symbol, str), "INVALID_NATIVE_SYMBOL")
    valid = None if price is None or symbol is None else bool(symbol) and price > 0
    return eligible, valid


def _write(row: Mapping[str, Any]) -> dict:
    raw = row.get("write")
    require(isinstance(raw, Mapping) and set(raw) == set(WRITE_FIELDS), "INVALID_WRITE_WITNESS")
    native_id(raw["file_id"], "INVALID_PHYSICAL_FILE_ID")
    require(isinstance(raw["write_date_utc"], str) and
            re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw["write_date_utc"]) is not None,
            "INVALID_WRITE_DATE")
    utc_time(raw["write_date_utc"] + "T00:00:00Z")
    require(utc_time(raw["partition_selected_at"]).strftime("%Y-%m-%d") ==
            raw["write_date_utc"], "PHYSICAL_WRITE_DATE_MISMATCH")
    require(raw["partition_name"] == f"rejections_{raw['write_date_utc']}.jsonl",
            "PHYSICAL_PARTITION_NAME_MISMATCH")
    require(type(raw["byte_start"]) is int and type(raw["byte_end"]) is int and
            0 <= raw["byte_start"] < raw["byte_end"], "INVALID_WRITE_RANGE")
    require(isinstance(raw["record_sha256"], str) and
            re.fullmatch(r"[0-9a-f]{64}", raw["record_sha256"]) is not None,
            "INVALID_RECORD_HASH")
    return dict(raw)


def verify_durability_chains(
    *, roster_bytes: bytes, receipt_bytes: bytes, record_bytes: bytes,
    fsync_witness_bytes: bytes, expected_hashes: Mapping[str, str],
    boundary: Mapping[str, str], fence: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconcile four explicit immutable bundles, not live paths or self-certified files.

    Hash pins and source independence must be established outside this function.
    Missing chains remain UNKNOWN. Claimed fsync without a separate native witness
    and exact captured record bytes is contradictory and aborts verification.
    """
    declared = validate_boundary(boundary)
    require(isinstance(expected_hashes, Mapping) and set(expected_hashes) ==
            {"roster", "receipts", "records", "fsync"}, "BUNDLE_HASH_PINS_REQUIRED")
    rows = {name: decode_bundle(raw, expected_hashes[name], declared) for name, raw in
            (("roster", roster_bytes), ("receipts", receipt_bytes),
             ("records", record_bytes), ("fsync", fsync_witness_bytes))}
    require(bool(rows["roster"]), "PACKET_ROSTER_NOT_AVAILABLE")
    require(isinstance(fence, Mapping) and set(fence) == {"at", "queue_state", "prefixes"},
            "INVALID_CAPTURE_FENCE")
    require(isinstance(fence["queue_state"], str) and
            fence["queue_state"] in {"QUIESCENT", "NOT_QUIESCENT", "UNKNOWN"},
            "INVALID_QUEUE_STATE")
    fence_at = utc_time(fence["at"])
    require(utc_time(declared["window_end"]) <= fence_at <=
            utc_time(declared["capture_cutoff"]), "FENCE_OUTSIDE_CAPTURE_BOUNDARY")
    require(isinstance(fence["prefixes"], (list, tuple)), "PREFIX_FENCES_NOT_AVAILABLE")
    prefixes = {}
    for prefix in fence["prefixes"]:
        require(isinstance(prefix, Mapping), "INVALID_PREFIX_FENCE")
        file_id = native_id(prefix.get("file_id"), "INVALID_PHYSICAL_FILE_ID")
        require(file_id not in prefixes, "DUPLICATE_PREFIX_FENCE")
        require(type(prefix.get("byte_end")) is int and prefix["byte_end"] >= 0,
                "INVALID_PREFIX_RANGE")
        native_id(prefix.get("sha256"), "PREFIX_HASH_NOT_AVAILABLE")
        require(re.fullmatch(r"[0-9a-f]{64}", prefix["sha256"]) is not None,
                "INVALID_PREFIX_HASH")
        prefixes[file_id] = prefix

    roster = {}
    unique = {field: set() for field in IDENTITY}
    for row in rows["roster"]:
        native_id(row.get("source_id"), "NATIVE_ROSTER_SOURCE_NOT_AVAILABLE")
        for field in IDENTITY:
            value = native_id(row.get(field), "MISSING_NATIVE_CAUSAL_IDENTITY")
            require(value not in unique[field], "AMBIGUOUS_NATIVE_IDENTITY")
            unique[field].add(value)
        event_time = utc_time(row.get("event_time"))
        require(utc_time(declared["window_start"]) <= event_time <
                utc_time(declared["window_end"]), "PACKET_OUTSIDE_EVENT_WINDOW")
        roster[row["attempt_id"]] = row

    source_ids = {name: set() for name in rows}
    source_ids["roster"] = {r["source_id"] for r in rows["roster"]}

    def join(row: Mapping[str, Any], role: str) -> str:
        source_ids[role].add(native_id(row.get("source_id"), "NATIVE_SOURCE_ID_NOT_AVAILABLE"))
        attempt = native_id(row.get("attempt_id"), "MISSING_NATIVE_ATTEMPT_ID")
        require(attempt in roster, "EVIDENCE_OUTSIDE_PACKET_ROSTER")
        require(all(row.get(k) == roster[attempt][k] for k in IDENTITY),
                "NATIVE_CAUSAL_JOIN_MISMATCH")
        return attempt

    chains: dict[str, list] = {attempt: [] for attempt in roster}
    receipt_ids: set[str] = set()
    for row in rows["receipts"]:
        attempt = join(row, "receipts")
        receipt_id = native_id(row.get("receipt_id"), "INVALID_RECEIPT_ID")
        require(receipt_id not in receipt_ids, "DUPLICATE_RECEIPT_ID")
        receipt_ids.add(receipt_id)
        require(type(row.get("sequence")) is int and row["sequence"] >= 1,
                "INVALID_CAUSAL_SEQUENCE")
        require(isinstance(row.get("stage"), str), "MISSING_STAGE_OUTCOME")
        at = utc_time(row.get("at"))
        require(utc_time(roster[attempt]["event_time"]) <= at <= fence_at,
                "RECEIPT_OUTSIDE_CAPTURE_FENCE")
        chains[attempt].append(row)

    records, witnesses, record_payloads = {}, {}, {}
    observation_ids: set[str] = set()
    fsync_call_ids: set[str] = set()
    ranges: dict[str, list[tuple[int, int]]] = {}
    for row in rows["records"]:
        attempt = join(row, "records")
        require(attempt not in records, "DUPLICATE_CAPTURED_RECORD")
        write = _write(row)
        require(write["file_id"] in prefixes and write["byte_end"] <=
                prefixes[write["file_id"]]["byte_end"], "RECORD_OUTSIDE_READ_PREFIX")
        for start, end in ranges.setdefault(write["file_id"], []):
            require(write["byte_end"] <= start or end <= write["byte_start"],
                    "OVERLAPPING_RECORD_RANGES")
        ranges[write["file_id"]].append((write["byte_start"], write["byte_end"]))
        line = row.get("record_line")
        require(isinstance(line, str) and line.endswith("\n") and line.count("\n") == 1,
                "EXACT_JSONL_RECORD_BYTES_REQUIRED")
        encoded = line.encode("utf-8")
        require(len(encoded) == write["byte_end"] - write["byte_start"] and
                hashlib.sha256(encoded).hexdigest() == write["record_sha256"],
                "RECORD_BYTES_HASH_OR_RANGE_MISMATCH")
        try:
            record = json.loads(line, object_pairs_hook=_strict_object,
                                parse_constant=lambda _: require(False, "NONFINITE_RECORD_JSON"))
        except json.JSONDecodeError as exc:
            raise EvidenceIntegrityError("INVALID_RECORD_JSON") from exc
        require(isinstance(record, Mapping), "INVALID_RECORD_JSON")
        require(all(record.get(k) == row.get(k) for k in
                    ("packet_id", "trace_id", "observation_id")), "RECORD_NATIVE_JOIN_MISMATCH")
        native_id(row.get("observation_id"), "MISSING_OBSERVATION_ID")
        require(row["observation_id"] not in observation_ids, "DUPLICATE_RECORD_OBSERVATION_ID")
        observation_ids.add(row["observation_id"])
        require(utc_time(record.get("ts_iso")) == utc_time(roster[attempt]["event_time"]),
                "RECORD_EVENT_TIME_MISMATCH")
        records[attempt] = row
        record_payloads[attempt] = record
    for row in rows["fsync"]:
        attempt = join(row, "fsync")
        require(attempt not in witnesses, "DUPLICATE_FSYNC_WITNESS")
        native_id(row.get("fsync_call_id"), "MISSING_NATIVE_FSYNC_CALL_ID")
        require(row["fsync_call_id"] not in fsync_call_ids, "DUPLICATE_NATIVE_FSYNC_CALL_ID")
        fsync_call_ids.add(row["fsync_call_id"])
        require(row.get("outcome") == "RETURNED", "FSYNC_WITNESS_NOT_RETURNED")
        require(row.get("fd_file_id") == _write(row)["file_id"], "FSYNC_FD_FILE_MISMATCH")
        require(utc_time(row.get("at")) <= fence_at, "FSYNC_WITNESS_OUTSIDE_FENCE")
        witnesses[attempt] = row
    for left, right in (("roster", "receipts"), ("roster", "records"), ("roster", "fsync"),
                        ("receipts", "records"), ("receipts", "fsync"), ("records", "fsync")):
        require(not source_ids[left].intersection(source_ids[right]),
                "SELF_ATTESTED_EVIDENCE_SOURCE")

    counts: Counter[str] = Counter()
    decisions = []
    consumed_witnesses: set[str] = set()
    built_observations: set[str] = set()
    for attempt, raw_chain in sorted(chains.items()):
        chain = sorted(raw_chain, key=lambda r: r["sequence"])
        stages = []
        previous, previous_at = "ROOT", utc_time(roster[attempt]["event_time"])
        observation_id = None
        listener_id = None
        flags = None
        write = None
        validation = None
        filter_criteria = None
        for sequence, receipt in enumerate(chain, 1):
            require(receipt["sequence"] == sequence, "DUPLICATE_OR_GAPPED_CAUSAL_SEQUENCE")
            stage = receipt["stage"]
            require(stage in TRANSITIONS.get(previous, set()), "INVALID_STAGE_TRANSITION")
            at = utc_time(receipt["at"])
            require(at >= previous_at, "CAUSAL_TIME_REVERSED")
            if stage in {"NOT_ATTEMPTED", "NOT_PUBLISHED", "DROPPED", "NOT_DELIVERED",
                         "BUILD_FAILED", "BUILD_STATE_UNKNOWN", "THREW", "PERSIST_FALSE",
                         "PERSIST_THREW", "APPEND_ERROR", "FLUSH_ERROR", "FSYNC_ERROR"}:
                native_id(receipt.get("reason"), "MISSING_NATIVE_STAGE_REASON")
            if stage == "NOT_ATTEMPTED":
                require(receipt["reason"] in {"SAFE_MODE", "NON_ACTIONABLE", "UNKNOWN_FLAGS"},
                        "INVALID_BUILD_SKIP_REASON")
            if stage in {"OBSERVATION_BUILD_ATTEMPT", "NOT_ATTEMPTED", "BUILD_STATE_UNKNOWN"}:
                flags = receipt.get("producer_flags")
                require(isinstance(flags, Mapping) and set(flags) ==
                        {"actionable", "safe_mode", "bus_configured", "listener_registered"},
                        "NATIVE_PRODUCER_FLAGS_NOT_AVAILABLE")
                require(all(v is None or type(v) is bool for v in flags.values()),
                        "INVALID_PRODUCER_FLAG")
                if stage == "OBSERVATION_BUILD_ATTEMPT":
                    require(flags["safe_mode"] is not True and flags["actionable"] is not False
                            and flags["bus_configured"] is not False,
                            "BUILD_ATTEMPT_CONTRADICTS_PRODUCER_FLAGS")
                if stage == "NOT_ATTEMPTED" and receipt["reason"] != "UNKNOWN_FLAGS":
                    require(flags["safe_mode"] is True if receipt["reason"] == "SAFE_MODE" else
                            flags["actionable"] is False, "BUILD_SKIP_FLAG_CONTRADICTION")
            if stage == "LISTENER_DISPATCH":
                listener_id = native_id(receipt.get("listener_id"), "MISSING_NATIVE_LISTENER_ID")
                require(receipt.get("listener_kind") == "REJECTION_STORE",
                        "NOT_A_REJECTION_STORE_RECEIPT")
                require(flags["listener_registered"] is not False, "DISPATCH_WITH_NO_LISTENER")
            elif listener_id is not None:
                require(receipt.get("listener_id") == listener_id, "LISTENER_CAUSAL_JOIN_MISMATCH")
            if stage == "BUILD_OK":
                observation_id = native_id(receipt.get("observation_id"), "MISSING_OBSERVATION_ID")
                require(observation_id not in built_observations, "AMBIGUOUS_BUILT_OBSERVATION_ID")
                built_observations.add(observation_id)
            elif observation_id is not None:
                require(receipt.get("observation_id") == observation_id,
                        "OBSERVATION_CAUSAL_JOIN_MISMATCH")
            if stage in {"FILTER_ELIGIBLE", "FILTERED_OUT", "FILTER_UNKNOWN"}:
                eligible, validation = _criteria(receipt)
                filter_criteria = receipt["criteria"]
                require(eligible is {"FILTER_ELIGIBLE": True, "FILTERED_OUT": False,
                                     "FILTER_UNKNOWN": None}[stage], "FILTER_CLAIM_CONTRADICTION")
            if stage in {"RECORD_VALIDATE_PASS", "RECORD_VALIDATE_FAIL", "VALIDATE_UNKNOWN"}:
                require(validation is {"RECORD_VALIDATE_PASS": True, "RECORD_VALIDATE_FAIL": False,
                                       "VALIDATE_UNKNOWN": None}[stage],
                        "VALIDATION_CLAIM_CONTRADICTION")
            if stage in {"WRITE_APPEND", "FLUSH", "FSYNC_RETURN"}:
                claimed = _write(receipt)
                require(utc_time(claimed["partition_selected_at"]) <= at,
                        "PARTITION_SELECTED_AFTER_WRITE")
                require(write is None or claimed == write, "WRITE_RECEIPT_MISMATCH")
                write = claimed
            if stage == "FSYNC_RETURN":
                require(attempt in records and attempt in witnesses,
                        "FSYNC_CLAIM_WITHOUT_INDEPENDENT_EVIDENCE")
                record, witness = records[attempt], witnesses[attempt]
                require(_write(record) == write == _write(witness), "FSYNC_WRITE_JOIN_MISMATCH")
                require(record["observation_id"] == observation_id, "RECORD_OBSERVATION_MISMATCH")
                require(witness.get("observation_id") == observation_id,
                        "WITNESS_OBSERVATION_MISMATCH")
                require(all(record_payloads[attempt].get(k) == filter_criteria.get(k)
                            for k in ("symbol", "side", "price")),
                        "RECORD_FILTER_CRITERIA_MISMATCH")
                require(receipt.get("fsync_call_id") == witness["fsync_call_id"] and
                        utc_time(witness["at"]) == at, "FSYNC_CALL_JOIN_MISMATCH")
                consumed_witnesses.add(attempt)
            stages.append(stage)
            previous, previous_at = stage, at

        if not stages:
            category = "MISSING_CHAIN"
        elif stages[-1] not in TERMINALS:
            category = "INCOMPLETE_CHAIN"
        elif "FSYNC_RETURN" in stages:
            category = ("FSYNC_CHAIN_CONSISTENT" if "PERSIST_SUCCESS" in stages else
                        "FSYNC_ACK_WITH_PERSIST_FAILURE")
        elif "BUILD_STATE_UNKNOWN" in stages or (stages[0] == "NOT_ATTEMPTED" and
                                                 chain[0]["reason"] == "UNKNOWN_FLAGS"):
            category = "BUILD_STATE_UNKNOWN"
        else:
            category = next((result for stage, result in (
                ("BUILD_FAILED", "BUILD_FAILED"), ("NOT_ATTEMPTED", "BUILD_NOT_ATTEMPTED"),
                ("NOT_PUBLISHED", "NOT_PUBLISHED"), ("DROPPED", "PUBLICATION_DROPPED"),
                ("NOT_DELIVERED", "NOT_DELIVERED"), ("FILTERED_OUT", "FILTERED_OUT"),
                ("FILTER_UNKNOWN", "ELIGIBILITY_UNKNOWN"),
                ("RECORD_VALIDATE_FAIL", "VALIDATION_FAILED"),
                ("VALIDATE_UNKNOWN", "VALIDATION_UNKNOWN"), ("PERSIST_THREW", "PERSIST_THREW"),
                ("PERSIST_FALSE", "PERSIST_FALSE"), ("THREW", "LISTENER_THREW"),
            ) if stage in stages), "LISTENER_RETURN_WITHOUT_FSYNC")
        if attempt in records:
            require(not any(s in stages for s in ("NOT_ATTEMPTED", "BUILD_FAILED", "NOT_PUBLISHED",
                                                  "DROPPED", "NOT_DELIVERED", "FILTERED_OUT",
                                                  "RECORD_VALIDATE_FAIL")),
                    "RECORD_CONTRADICTS_NON_PERSISTED_CHAIN")
        counts[category] += 1
        decisions.append({"attempt_id": attempt, "packet_id": roster[attempt]["packet_id"],
                          "category": category, "last_stage": previous,
                          "captured_record": attempt in records,
                          "producer_flags": "UNKNOWN" if flags is None or
                          any(v is None for v in flags.values()) else "DECLARED_COMPLETE",
                          "late_receipt": bool(chain) and utc_time(chain[-1]["at"]) >=
                          utc_time(declared["window_end"])})
    require(set(witnesses) == consumed_witnesses, "UNMATCHED_FSYNC_WITNESS")
    require(sum(counts.values()) == len(roster), "PACKET_CHAIN_ACCOUNTING_FAILURE")
    return {
        "version": "D1_E_V1", "status": "SUPPLIED_CHAIN_CONSISTENCY_ONLY",
        "boundary": declared, "packet_roster_entries": len(roster),
        "counts": {k: counts[k] for k in RESULTS}, "decisions": decisions,
        "captured_records": len(records), "matched_fsync_witnesses": len(consumed_witnesses),
        "records_without_fsync_chain": len(set(records) - consumed_witnesses),
        "declared_queue_state": fence["queue_state"], "window_completeness": "NOT_PROVEN",
        "producer_completeness": "NOT_PROVEN", "native_epoch_binding": "NOT_PROVEN",
        "custody": "NOT_VERIFIED", "receipt_source_independence": "NOT_VERIFIED",
        "clock_certified": False, "actual_persistence_proof": "NOT_OBSERVED",
        "per_packet_durability": "NOT_PROVEN", "crash_durability": "NOT_PROVEN",
        "directory_metadata_durability": "NOT_PROVEN",
        "counterfactual_performance_eligibility": "NOT_PROVEN",
        "paper_stress_runtime_go": "DENIED",
    }
