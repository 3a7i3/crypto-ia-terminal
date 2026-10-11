"""D1-C: aggregate, read-only classification of the pinned Research capture.

No runtime imports, producer discovery, writes or performance calculations.
LINKED proves a captured join, never a complete producer or a trading outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# The standalone launcher injects its verified historical module. Package import
# is retained solely for unattested synthetic helpers; public audit rejects it.
if "d1" not in globals():
    from research_data import stress_d1_snapshot_audit as d1

_source_verifier = None

VERSION = "D1_C_V2"
PARENT_SHA = "b99c2ed4f38ebeff481b5f470ed2d08e8e852257"
SOURCE_SHA = "116634be0d3c015cce1cfa58be7da7255414fbfd"
EPOCH = "BURN-IN-EPOCH-01-20260926T064144Z"
CONFIG_SHA = "9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4"
CLASSES = ("LINKED", "PROVEN_NOT_ELIGIBLE", "ELIGIBLE_WITHOUT_OBSERVED_RECORD",
           "UNKNOWN_ELIGIBILITY")
SIDES = ("BUY", "SELL", "LONG", "SHORT")
MAX_COMPONENT = 256 * 1024 * 1024
SIGNAL = re.compile(r"score=[^ ]+ signal=([^ ]+) régime=[^ ]+ confirmé=(?:True|False)")
G8D = re.compile(r"trade_allowed=False \[([^\[\]\n]+)\]")


def _read(path: Path, limit: int) -> bytes:
    with d1.open_regular(path) as stream:
        before = stream.fileno()
        first = os.fstat(before)
        d1.require(first.st_size <= limit, "READ_BUDGET_EXCEEDED")
        raw = stream.read(limit + 1)
        last = os.fstat(before)
        d1.require((first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns) ==
                   (last.st_dev, last.st_ino, last.st_size, last.st_mtime_ns),
                   "SOURCE_MUTATED_DURING_READ")
        d1.require(len(raw) == first.st_size, "SOURCE_SHORT_READ")
        return raw


def _load_snapshot(root: Path, manifest_sha: str,
                   counts: dict[str, int]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Internal bounded loader; synthetic fixtures use their own exact digest/counts.

    Public audit always pins the historical digest/counts, with no CLI override.
    Reuse D1 strict JSON, file, timestamp and index rules on bytes read once.
    """
    raw_manifest = _read(root / "custody_manifest.json", d1.MAX_MANIFEST)
    d1.require(hashlib.sha256(raw_manifest).hexdigest() == manifest_sha,
               "MANIFEST_SHA256_MISMATCH")
    manifest = d1.strict_json(raw_manifest)
    d1.require(manifest.get("schema") == "PAPER_STRESS_D1_OPERATOR_PREFIX_CUSTODY_V1",
               "MANIFEST_SCHEMA_MISMATCH")
    d1.require(manifest.get("authority") == "RESEARCH_PROVISIONAL_ONLY" and
               manifest.get("source_epoch_binding") == "UNVERIFIED" and
               manifest.get("population_completeness") == "NOT_PROVEN",
               "UNEXPECTED_AUTHORITY_OR_COMPLETENESS")
    d1.require(manifest.get("window") == {"start_utc": "2026-10-10T00:00:00Z",
               "end_utc_exclusive": "2026-10-11T00:00:00Z"}, "MANIFEST_WINDOW_MISMATCH")
    for field, expected in (("paper_epoch_id", EPOCH), ("runtime_source_sha", SOURCE_SHA),
                            ("experiment_config_sha256", CONFIG_SHA)):
        d1.require(field not in manifest or manifest[field] == expected,
                   "UNEXPECTED_SOURCE_IDENTITY")
    meta = manifest.get("records")
    d1.require(isinstance(meta, list) and len(meta) == len(d1.KINDS) and
               all(isinstance(row, dict) for row in meta), "MANIFEST_COMPONENTS_INVALID")
    by_kind = {row.get("kind"): row for row in meta}
    d1.require(set(by_kind) == set(d1.KINDS), "MANIFEST_COMPONENTS_MISMATCH")
    records = {}
    for kind in d1.KINDS:
        item = by_kind[kind]
        raw = _read(root / f"{kind}.jsonl", MAX_COMPONENT)
        index = _read(root / f"{kind}.offsets.jsonl", MAX_COMPONENT)
        d1.require(hashlib.sha256(raw).hexdigest() == item.get("selected_sha256"),
                   "COMPONENT_SHA_MISMATCH")
        d1.require(hashlib.sha256(index).hexdigest() == item.get("offset_index_sha256"),
                   "INDEX_SHA_MISMATCH")
        d1.require(len(raw) == item.get("selected_bytes"), "COMPONENT_SIZE_MISMATCH")
        d1.require((not raw or raw.endswith(b"\n")) and
                   (not index or index.endswith(b"\n")), "MALFORMED_JSONL_LINE")
        lines, offsets = raw.splitlines(keepends=True), index.splitlines(keepends=True)
        d1.require(len(lines) == len(offsets) == counts[kind] == item.get("selected_rows"),
                   "CAPTURE_CARDINALITY_MISMATCH")
        prefix = item.get("source_prefix_bytes")
        d1.require(type(prefix) is int and prefix >= 0, "INVALID_SOURCE_PREFIX_SIZE")
        d1.require(isinstance(item.get("source_prefix_sha256"), str) and
                   bool(d1.SHA256.fullmatch(item["source_prefix_sha256"])), "BAD_PREFIX_SHA")
        outside = item.get("outside_utc_window")
        d1.require(type(outside) is int and outside >= 0 and
                   item.get("source_total_rows") == counts[kind] + outside,
                   "SOURCE_ROW_ACCOUNTING_INCONSISTENT")
        closed = kind in ("decision_packets", "rejection_store")
        d1.require(item.get("source_mode") == ("closed" if closed else "prefix"),
                   "SOURCE_MODE_MISMATCH")
        d1.require(not closed or outside == 0, "CLOSED_SOURCE_COUNTS_MISMATCH")
        rows = []
        last_line = last_end = 0
        for line, offset in zip(lines, offsets):
            d1.require(len(line) <= d1.MAX_LINE and len(offset) <= d1.MAX_LINE,
                       "LINE_TOO_LARGE")
            obj, off = d1.strict_json(line), d1.strict_json(offset)
            number, start, span = (off.get(k) for k in
                                   ("source_line", "source_byte_offset", "source_line_bytes"))
            d1.require(type(number) is int and number > last_line and
                       type(start) is int and start >= last_end and
                       type(span) is int and span == len(line) and start + span <= prefix,
                       "SOURCE_OFFSETS_INVALID")
            d1.require(not closed or (number == last_line + 1 and start == last_end),
                       "CLOSED_SOURCE_HAS_UNEXPLAINED_GAPS")
            d1.require(off.get("source_line_sha256") == hashlib.sha256(line).hexdigest(),
                       "SOURCE_LINE_SHA_MISMATCH")
            moment, _ = d1.time_value(obj, kind)
            d1.require(d1.WINDOW_START <= moment < d1.WINDOW_END, "ROW_OUTSIDE_CAPTURE_WINDOW")
            rows.append(obj)
            last_line, last_end = number, start + span
        d1.require(not closed or last_end == prefix, "CLOSED_PREFIX_SIZE_MISMATCH")
        records[kind] = rows
    return records, manifest


def _id(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    d1.require(isinstance(value, str) and bool(value), "MISSING_JOIN_ID")
    return value


def _unique(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        key = _id(row, field)
        d1.require(key not in result, f"DUPLICATE_{field.upper()}")
        result[key] = row
    return result


def _criteria(packet: dict[str, Any]) -> tuple[str, str]:
    metadata = packet["metadata"]
    actionable = metadata.get("lse_actionable")
    side_claim = metadata.get("signal_raw")
    # extra_meta can overwrite signal_raw. Corroborate with the original
    # builder reasoning template; do not invert packet.FLAT (default mapping).
    native_signals = {match.group(1) for entry in packet.get("reasoning", [])
                      if isinstance(entry, dict) and entry.get("actor") == "live_signal_engine"
                      and isinstance(entry.get("message"), str)
                      and (match := SIGNAL.fullmatch(entry["message"]))}
    side = side_claim if isinstance(side_claim, str) and native_signals == {side_claim} else None
    # Only native fields from the audited builder, never packet.is_actionable().
    if type(actionable) is bool and not actionable:
        return "PROVEN_NOT_ELIGIBLE", "NATIVE_LSE_NON_ACTIONABLE"
    if isinstance(side, str) and side not in SIDES:
        return "PROVEN_NOT_ELIGIBLE", "NATIVE_SIGNAL_SIDE_EXCLUDED"
    denied = False
    for transition in packet.get("state_history", []):
        d1.require(isinstance(transition, dict), "INVALID_STATE_HISTORY")
        if transition.get("actor") == "pipeline_g8d" and transition.get("to_state") == "REJECTED":
            message = transition.get("reason")
            if isinstance(message, str) and G8D.fullmatch(message):
                denied = True
    if actionable is True and side in SIDES and denied:
        return "ELIGIBLE_WITHOUT_OBSERVED_RECORD", "IDENTIFIABLE_FILTERS_PASS_RECORD_PRICE_UNKNOWN"
    return "UNKNOWN_ELIGIBILITY", "MISSING_NATIVE_CRITERIA_OR_LEGACY_VERDICT"


def classify_records(records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Pure analysis primitive; does not attest custody of caller-supplied records."""
    d1.require(set(records) == set(d1.KINDS), "ALL_COMPONENTS_REQUIRED")
    packets = _unique(records["decision_packets"], "packet_id")
    traces = _unique([{"trace_id": p.get("metadata", {}).get("trace_id")}
                      for p in packets.values() if isinstance(p.get("metadata"), dict)], "trace_id")
    d1.require(len(traces) == len(packets), "MISSING_PACKET_METADATA")
    summary = d1.count_summary(records)
    causes = summary["step3_causes"]
    join = causes["packet_identity_join"]
    d1.require(all(join[k] == 0 for k in ("packet_traces_without_identity",
               "identities_without_packet_trace", "symbol_mismatched_trace_ids",
               "cycle_mismatched_trace_ids")), "PACKET_IDENTITY_JOIN_INCONSISTENT")
    ids = causes["identities"]
    d1.require(ids["payload_digest_invalid_rows"] == 0 and
               ids["identity_ids_with_conflicting_payload_digest"] == 0,
               "IDENTITY_PAYLOAD_INVALID")
    d1.require(not summary["step4_coverage"]["other_record_defects"], "MISSING_RECORD_IDENTITY")
    identities: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for identity in records["decision_identity_records"]:
        identities[_id(identity, "decision_id")].append(identity)
        payload = identity.get("payload")
        d1.require(isinstance(payload, dict) and all(payload.get(k) == identity.get(k)
                   for k in ("namespace", "symbol", "cycle")), "IDENTITY_BINDING_INVALID")
    for packet in packets.values():
        for identity in identities[packet["metadata"]["trace_id"]]:
            ti, _ = d1.time_value(identity, "decision_identity_records")
            tp, _ = d1.time_value(packet, "decision_packets")
            d1.require(ti <= tp, "IDENTITY_TIME_AFTER_PACKET")
        d1.require(isinstance(packet.get("state_history", []), list), "INVALID_STATE_HISTORY")
        d1.require(isinstance(packet.get("reasoning", []), list), "INVALID_REASONING")
        _id(packet, "lifecycle_state")
    _unique(records["rejection_store"], "observation_id")
    observations = _unique(records["rejection_store"], "packet_id")
    for pid, obs in observations.items():
        d1.require(pid in packets, "OBSERVATION_WITHOUT_PACKET")
        packet = packets[pid]
        d1.require({"observation_id", "packet_id", "symbol", "side", "score", "price", "ts"} <= obs.keys(),
                   "MISSING_REJECTION_RECORD_FIELD")
        d1.require(packet["lifecycle_state"] == "REJECTED", "OBSERVATION_ON_NON_REJECTED")
        d1.require(_id(obs, "trace_id") == packet["metadata"]["trace_id"] and
                   obs.get("symbol") == packet.get("symbol") and
                   str(obs.get("cycle")) == str(packet.get("created_cycle_id")),
                   "OBSERVATION_JOIN_INCONSISTENT")
        d1.require(obs.get("side") in SIDES and bool(obs.get("symbol")) and
                   type(obs.get("price")) in (int, float) and math.isfinite(obs["price"]) and obs["price"] > 0,
                   "INVALID_REJECTION_RECORD")
        to, _ = d1.time_value(obs, "rejection_store")
        tp, _ = d1.time_value(packet, "decision_packets")
        d1.require(to >= tp, "OBSERVATION_TIME_BEFORE_PACKET")
        candidate, _ = _criteria(packet)
        d1.require(candidate != "PROVEN_NOT_ELIGIBLE", "LINK_CONTRADICTS_NATIVE_FILTERS")
    totals: Counter[str] = Counter({key: 0 for key in CLASSES})
    reasons: Counter[str] = Counter()
    categories: dict[str, Counter[str]] = defaultdict(Counter)
    actors: dict[str, Counter[str]] = defaultdict(Counter)
    blockers: dict[str, Counter[str]] = defaultdict(Counter)
    hours = {f"{hour:02d}": Counter({key: 0 for key in CLASSES}) for hour in range(24)}
    states = Counter(p["lifecycle_state"] for p in packets.values())
    naive = 0
    for pid, packet in packets.items():
        moment, assumed = d1.time_value(packet, "decision_packets")
        naive += int(assumed)
        d1.require(d1.WINDOW_START <= moment < d1.WINDOW_END, "PACKET_OUTSIDE_WINDOW")
        if packet["lifecycle_state"] != "REJECTED":
            continue
        classification, reason = ("LINKED", "EXACT_CAPTURED_JOIN") if pid in observations else _criteria(packet)
        totals[classification] += 1
        reasons[reason] += 1
        category = packet.get("event_category")
        categories[category if category in ("TRADE", "GOVERNANCE", "SYSTEM") else "UNKNOWN"][classification] += 1
        rejected = [t for t in packet.get("state_history", []) if isinstance(t, dict) and
                    t.get("to_state") == "REJECTED"]
        actor = rejected[0].get("actor") if rejected else None
        # Closed vocabulary prevents raw custom actor names/IDs leaking to stdout.
        actor = actor if actor in ("risk_gate", "global_risk_gate", "portfolio_brain", "capital_engine",
                                  "pipeline_g8d", "governance_g0", "conviction_engine") else "UNKNOWN"
        actors[actor][classification] += 1
        blocker = observations.get(pid, {}).get("first_blocker")
        blocker = blocker if blocker in ("authority", "meta", "gate", "awareness", "conviction",
                                         "no_trade", "portfolio", "cae", "mistake_mem",
                                         "exec_override", "radar", "arbitrator") else "UNKNOWN"
        blockers[blocker][classification] += 1
        hours[f"{int((moment - d1.WINDOW_START) // 3600):02d}"][classification] += 1
    rejected_count = states.get("REJECTED", 0)
    d1.require(sum(totals.values()) == rejected_count and totals["LINKED"] == len(observations),
               "CLASSIFICATION_ACCOUNTING_FAILURE")
    for matrix in (categories, actors, blockers, hours):
        d1.require(sum(sum(row.values()) for row in matrix.values()) == rejected_count,
                   "MATRIX_ACCOUNTING_FAILURE")
    return {"analysis_status": "UNATTESTED_RECORDS_CLASSIFIED", "version": VERSION,
            "population": {"packets": len(packets), "rejected": rejected_count,
                           "non_rejected": len(packets) - rejected_count,
                           "execution_pending": states.get("EXECUTION_PENDING", 0),
                           "execution_pending_is_filled": False},
            "classifications": dict(totals), "evidence_reasons": dict(sorted(reasons.items())),
            "coverage_by_event_category": dict(sorted(categories.items())),
            "coverage_by_first_packet_reject_actor": dict(sorted(actors.items())),
            "coverage_by_observed_first_blocker": dict(sorted(blockers.items())),
            "coverage_by_utc_hour": hours,
            "integrity": {"duplicate_packets": 0, "duplicate_packet_traces": 0,
                          "duplicate_observations": 0, "multiple_observations_per_packet": 0,
                          "inconsistent_joins": 0,
                          "identity_history_extra_rows": ids["history_extra_rows"]},
            "naive_packet_utc_assumed_not_clock_certified": naive,
            "accounting": "PASS_ALL_REJECTED_PARTITIONED",
            "denominator": "REJECTED_PACKETS_IN_VERIFIED_CAPTURE_ONLY",
            "producer_completeness": "NOT_PROVEN", "persistence_attempts": "NOT_OBSERVED",
            "unlinked_record_price_validation": "UNKNOWN",
            "eligibility_scope": "IDENTIFIABLE_ON_OBSERVATION_FILTERS_ONLY",
            "contract_application": "CONDITIONAL_ON_AUDITED_SOURCE_BUILDER_NOT_RUNTIME_CERTIFICATION",
            "implementation_git_sha": "USE_REVIEWED_PR_HEAD_WITH_SCRIPT_SHA256",
            "certified_lost_records": None, "counterfactual_go": False,
            "COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY": "NOT_PROVEN",
            "PAPER_STRESS_RUNTIME_GO": "DENIED",
            "ACTIVE_BURN_IN_IMMUTABILITY_GUARD": "ACTIVE"}


def audit(root: Path) -> dict[str, Any]:
    """Pinned public boundary. No manifest/count/custody override is exposed."""
    try:
        if _source_verifier is None:
            raise ValueError("VERIFIED_SOURCE_LAUNCHER_REQUIRED")
        # Must precede even custody/manifest/component reads. The closure binds
        # the actual module identity, approved origins and verified source bytes.
        provenance = _source_verifier()
        d1.require(root.is_absolute() and root.name == "readonly_research_staging" and
                   not any(x in root.parts for x in ("home", "databases", "ppl_authority")),
                   "EXPLICIT_RESEARCH_ROOT_REQUIRED")
        for ancestor in (root, *root.parents):
            ancestor_stat = ancestor.lstat()
            d1.require(stat.S_ISDIR(ancestor_stat.st_mode) and not ancestor.is_symlink(),
                       "SYMLINK_ROOT_OR_ANCESTOR")
            d1.require(ancestor_stat.st_uid == 0 and
                       not ancestor_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
                       "UNTRUSTED_ROOT_ANCESTOR")
        mode = root.lstat()
        d1.require(stat.S_ISDIR(mode.st_mode) and mode.st_uid == 0 and
                   not mode.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH),
                   "IMMUTABLE_ROOT_CUSTODY_REQUIRED")
        for name in ("custody_manifest.json", *(f"{kind}{suffix}" for kind in d1.KINDS
                     for suffix in (".jsonl", ".offsets.jsonl"))):
            component = (root / name).lstat()
            d1.require(stat.S_ISREG(component.st_mode) and component.st_uid == 0 and
                       not component.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH),
                       "IMMUTABLE_COMPONENT_CUSTODY_REQUIRED")
        old = d1.audit(root)
        d1.require(old.get("status") == "D1_4STEP_COPY_AUDIT_COMPLETE_NOT_COUNTERFACTUAL_CERTIFIED",
                   "D1_COPY_VALIDATION_FAILED")
        rows, manifest = _load_snapshot(root, d1.EXPECTED_MANIFEST_SHA, d1.EXPECTED_COUNTS)
        result = classify_records(rows)
        result.update({"status": "D1_C_REAL_SUBSET_CLASSIFIED", "analysis_status": "PINNED_RESEARCH_COPY_CLASSIFIED",
                       "manifest_sha256": d1.EXPECTED_MANIFEST_SHA, "window_utc": manifest["window"],
                       "source_epoch_binding": manifest["source_epoch_binding"],
                       "dataset_id": None, "source_boundary_id": None,
                       "source_boundary_status": "NOT_PROVEN_BY_CUSTODY_MANIFEST",
                       "contract_parent_sha": PARENT_SHA,
                       **provenance})
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        # No exception text/raw values: report does not leak individual records.
        return {"status": "D1_C_INTEGRITY_FAILURE", "version": VERSION,
                "classification": "NOT_EMITTED", "counterfactual_go": False,
                "integrity_counts": "NOT_ESTABLISHED_ON_FAILED_VALIDATION",
                "reason_code": str(exc) if isinstance(exc, ValueError) and
                re.fullmatch(r"[A-Z_]+", str(exc)) else "VALIDATION_FAILED",
                "COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY": "NOT_PROVEN",
                "PAPER_STRESS_RUNTIME_GO": "DENIED", "ACTIVE_BURN_IN_IMMUTABILITY_GUARD": "ACTIVE"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.research_root)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    raise SystemExit(0 if result["status"] == "D1_C_REAL_SUBSET_CLASSIFIED" else 2)


if __name__ == "__main__":
    main()
