"""Scientific negative controls, synthetic only; no real-byte certification."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from research_data import stress_d1_snapshot_audit as d1
from research_data.stress_d1_rejection_eligibility import (
    CLASSES, _load_snapshot, audit, classify_records,
)

TS = d1.WINDOW_START + 120


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def records():
    packets, identities = [], []
    for i in range(5):
        packet = {"packet_id": f"packet-{i}", "metadata": {"trace_id": f"trace-{i}",
                  "lse_actionable": True, "signal_raw": "BUY"}, "symbol": "BTC/USDT",
                  "created_cycle_id": str(i), "created_at": TS + i,
                  "reasoning": [{"actor": "live_signal_engine", "message": "score=70 signal=BUY régime=TREND confirmé=True"}],
                  "side": "LONG", "event_category": "TRADE", "lifecycle_state": "REJECTED",
                  "state_history": [{"actor": "pipeline_g8d", "to_state": "REJECTED",
                                     "reason": "trade_allowed=False [gate]"}]}
        payload = {"namespace": "advisor_loop.analyze_symbol", "symbol": "BTC/USDT", "cycle": i}
        identities.append({"decision_id": f"trace-{i}", "ts": TS - 1, **payload,
                           "payload": payload,
                           "payload_digest": hashlib.sha256(encode(payload).rstrip(b"\n")).hexdigest()})
        packets.append(packet)
    packets[1]["metadata"]["lse_actionable"] = False
    packets[2]["metadata"]["signal_raw"] = "HOLD"
    packets[2]["side"] = "FLAT"
    packets[2]["reasoning"][0]["message"] = "score=70 signal=HOLD régime=TREND confirmé=True"
    packets[4]["metadata"].pop("lse_actionable")
    obs = {"observation_id": "observation-0", "packet_id": "packet-0", "trace_id": "trace-0",
           "cycle": 0, "symbol": "BTC/USDT", "ts": TS + 10,
           "side": "BUY", "price": 10, "score": 70, "first_blocker": "gate"}
    return {"decision_packets": packets, "decision_identity_records": identities,
            "rejection_store": [obs], "admission_ledger": []}


def stage(root: Path, rows, raw_override=None):
    root.mkdir(exist_ok=True)
    components = []
    for kind in d1.KINDS:
        raw = b"".join(encode(row) for row in rows[kind])
        if raw_override and kind in raw_override:
            raw = raw_override[kind]
        lines = raw.splitlines(keepends=True)
        offset = 0
        indexes = []
        for n, line in enumerate(lines, 1):
            indexes.append(encode({"source_line": n, "source_byte_offset": offset,
                                   "source_line_bytes": len(line),
                                   "source_line_sha256": hashlib.sha256(line).hexdigest()}))
            offset += len(line)
        index = b"".join(indexes)
        (root / f"{kind}.jsonl").write_bytes(raw)
        (root / f"{kind}.offsets.jsonl").write_bytes(index)
        components.append({"kind": kind, "selected_rows": len(lines), "selected_bytes": len(raw),
                           "selected_sha256": hashlib.sha256(raw).hexdigest(),
                           "offset_index_sha256": hashlib.sha256(index).hexdigest(),
                           "source_prefix_bytes": len(raw), "source_total_rows": len(lines),
                           "source_prefix_sha256": hashlib.sha256(raw).hexdigest(),
                           "outside_utc_window": 0,
                           "source_mode": "closed" if kind in ("decision_packets", "rejection_store") else "prefix"})
    manifest = {"schema": "PAPER_STRESS_D1_OPERATOR_PREFIX_CUSTODY_V1",
                "authority": "RESEARCH_PROVISIONAL_ONLY", "source_epoch_binding": "UNVERIFIED",
                "population_completeness": "NOT_PROVEN",
                "window": {"start_utc": "2026-10-10T00:00:00Z", "end_utc_exclusive": "2026-10-11T00:00:00Z"},
                "records": components}
    raw = encode(manifest)
    (root / "custody_manifest.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest(), {kind: len(rows[kind]) for kind in d1.KINDS}


def test_partition_exact_and_deterministic():
    rows = records()
    before = copy.deepcopy(rows)
    report = classify_records(rows)
    assert report["classifications"] == dict(zip(CLASSES, (1, 2, 1, 1)))
    assert sum(report["classifications"].values()) == report["population"]["rejected"] == 5
    for key in ("coverage_by_event_category", "coverage_by_first_packet_reject_actor",
                "coverage_by_observed_first_blocker", "coverage_by_utc_hour"):
        assert sum(sum(row.values()) for row in report[key].values()) == 5
    assert rows == before
    for value in rows.values():
        value.reverse()
    assert classify_records(rows) == report
    assert "packet-" not in json.dumps(report)
    assert "trace-" not in json.dumps(report)
    assert "observation-" not in json.dumps(report)


@pytest.mark.parametrize("side", ["HOLD", "FLAT", "hold", "OTHER"])
def test_exact_side_exclusion(side):
    rows = records()
    rows["decision_packets"][3]["metadata"]["signal_raw"] = side
    rows["decision_packets"][3]["reasoning"][0]["message"] = f"score=70 signal={side} régime=TREND confirmé=True"
    assert classify_records(rows)["classifications"]["PROVEN_NOT_ELIGIBLE"] == 3


@pytest.mark.parametrize("change", ["actionable", "side", "history", "root_fields", "coercion"])
def test_missing_criteria_remain_unknown(change):
    rows = records()
    p = rows["decision_packets"][3]
    if change == "actionable":
        p["metadata"].pop("lse_actionable")
    elif change == "side":
        p["metadata"].pop("signal_raw")
    elif change == "history":
        p["state_history"] = [{"actor": "risk_gate", "to_state": "REJECTED", "reason": "gate"}]
    elif change == "root_fields":
        p["metadata"] = {"trace_id": "trace-3"}
        p.update(actionable=True, trade_allowed=False, provenance_valid=True, side="BUY")
    else:
        p["metadata"]["lse_actionable"] = "true"
    result = classify_records(rows)
    assert result["classifications"]["UNKNOWN_ELIGIBILITY"] == 2
    assert result["classifications"]["ELIGIBLE_WITHOUT_OBSERVED_RECORD"] == 0


@pytest.mark.parametrize("defect,code", [
    ("packet_duplicate", "DUPLICATE_PACKET_ID"),
    ("trace_duplicate", "DUPLICATE_TRACE_ID"),
    ("observation_duplicate", "DUPLICATE_OBSERVATION_ID"),
    ("multiple_observations", "DUPLICATE_PACKET_ID"),
    ("trace_mismatch", "OBSERVATION_JOIN_INCONSISTENT"),
    ("symbol_mismatch", "OBSERVATION_JOIN_INCONSISTENT"),
    ("cycle_mismatch", "OBSERVATION_JOIN_INCONSISTENT"),
    ("orphan_observation", "OBSERVATION_WITHOUT_PACKET"),
    ("missing_identity", "PACKET_IDENTITY_JOIN_INCONSISTENT"),
    ("identity_digest", "IDENTITY_PAYLOAD_INVALID"),
    ("identity_late", "IDENTITY_TIME_AFTER_PACKET"),
    ("observation_early", "OBSERVATION_TIME_BEFORE_PACKET"),
    ("invalid_price", "INVALID_REJECTION_RECORD"),
    ("linked_non_actionable", "LINK_CONTRADICTS_NATIVE_FILTERS"),
    ("linked_pending", "OBSERVATION_ON_NON_REJECTED"),
    ("missing_packet_id", "MISSING_JOIN_ID"),
    ("missing_trace", "MISSING_JOIN_ID"),
])
def test_join_and_identity_negative_controls(defect, code):
    rows = records()
    p, obs, identity = rows["decision_packets"][0], rows["rejection_store"][0], rows["decision_identity_records"][0]
    if defect == "packet_duplicate":
        rows["decision_packets"].append(copy.deepcopy(p))
    elif defect == "trace_duplicate":
        rows["decision_packets"][1]["metadata"]["trace_id"] = "trace-0"
    elif defect in ("observation_duplicate", "multiple_observations"):
        new = copy.deepcopy(obs)
        if defect == "multiple_observations":
            new["observation_id"] = "distinct"
        rows["rejection_store"].append(new)
    elif defect == "trace_mismatch":
        obs["trace_id"] = "trace-1"
    elif defect == "symbol_mismatch":
        obs["symbol"] = "ETH/USDT"
    elif defect == "cycle_mismatch":
        obs["cycle"] = 99
    elif defect == "orphan_observation":
        obs["packet_id"] = "absent"
    elif defect == "missing_identity":
        rows["decision_identity_records"].pop()
    elif defect == "identity_digest":
        identity["payload_digest"] = "0" * 64
    elif defect == "identity_late":
        identity["ts"] = TS + 1
    elif defect == "observation_early":
        obs["ts"] = TS - 1
    elif defect == "invalid_price":
        obs["price"] = 0
    elif defect == "linked_non_actionable":
        p["metadata"]["lse_actionable"] = False
    elif defect == "linked_pending":
        p["lifecycle_state"] = "EXECUTION_PENDING"
    elif defect == "missing_packet_id":
        p.pop("packet_id")
    else:
        p["metadata"].pop("trace_id")
    with pytest.raises(d1.AuditBlocked, match=code):
        classify_records(rows)


def test_identity_history_is_explicit_not_silent_duplicate():
    rows = records()
    rows["decision_identity_records"].append(copy.deepcopy(rows["decision_identity_records"][0]))
    report = classify_records(rows)
    assert report["integrity"]["identity_history_extra_rows"] == 1
    assert report["classifications"]["LINKED"] == 1


def test_pending_is_never_filled_or_performance_certified():
    rows = records()
    rows["decision_packets"][4]["lifecycle_state"] = "EXECUTION_PENDING"
    report = classify_records(rows)
    assert report["population"]["execution_pending"] == 1
    assert report["population"]["execution_pending_is_filled"] is False
    assert report["producer_completeness"] == "NOT_PROVEN"
    assert report["persistence_attempts"] == "NOT_OBSERVED"
    assert report["certified_lost_records"] is None
    assert report["COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY"] == "NOT_PROVEN"
    assert report["PAPER_STRESS_RUNTIME_GO"] == "DENIED"
    assert report["analysis_status"] == "UNATTESTED_RECORDS_CLASSIFIED"
    assert not report["counterfactual_go"]


def test_loader_rehashes_and_classifies_synthetic_bytes(tmp_path):
    digest, counts = stage(tmp_path, records())
    rows, _ = _load_snapshot(tmp_path, digest, counts)
    assert classify_records(rows)["classifications"] == dict(zip(CLASSES, (1, 2, 1, 1)))
    # Public boundary refuses the synthetic root/profile rather than promoting it.
    assert audit(tmp_path)["status"] == "D1_C_INTEGRITY_FAILURE"


@pytest.mark.parametrize("defect", ["manifest", "sha", "missing_file", "missing_kind", "epoch",
                                    "source", "config", "completeness", "symlink", "index"])
def test_custody_negative_controls(tmp_path, defect):
    digest, counts = stage(tmp_path, records())
    path = tmp_path / "custody_manifest.json"
    if defect == "manifest":
        path.write_bytes(path.read_bytes() + b" ")
    elif defect == "sha":
        (tmp_path / "decision_packets.jsonl").write_bytes(b"{}\n")
    elif defect == "missing_file":
        (tmp_path / "decision_packets.jsonl").unlink()
    elif defect == "symlink":
        data = tmp_path / "decision_packets.jsonl"
        data.rename(tmp_path / "other")
        data.symlink_to(tmp_path / "other")
    elif defect == "index":
        (tmp_path / "decision_packets.offsets.jsonl").write_bytes(b"{}\n")
    else:
        manifest = json.loads(path.read_bytes())
        if defect == "missing_kind":
            manifest["records"].pop()
        elif defect == "epoch":
            manifest["paper_epoch_id"] = "wrong"
        elif defect == "source":
            manifest["runtime_source_sha"] = "0" * 40
        elif defect == "config":
            manifest["experiment_config_sha256"] = "0" * 64
        else:
            manifest["population_completeness"] = "CERTIFIED"
        path.write_bytes(encode(manifest))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises((d1.AuditBlocked, OSError)):
        _load_snapshot(tmp_path, digest, counts)


@pytest.mark.parametrize("raw", [b'{"packet_id":\n', b'{"packet_id":"a","packet_id":"b"}\n',
                                 b'\n', b'[]\n', b'{"created_at":NaN}\n', b'{}'])
def test_malformed_and_duplicate_json_are_not_excluded(tmp_path, raw):
    rows = records()
    rows["decision_packets"] = rows["decision_packets"][:1]
    digest, counts = stage(tmp_path, rows, {"decision_packets": raw})
    with pytest.raises(d1.AuditBlocked):
        _load_snapshot(tmp_path, digest, counts)


@pytest.mark.parametrize("kind", d1.KINDS)
def test_exclusive_utc_window(tmp_path, kind):
    rows = records()
    row = {"created_at": d1.WINDOW_END} if kind == "decision_packets" else {"ts": d1.WINDOW_END}
    rows[kind] = [row]
    digest, counts = stage(tmp_path, rows)
    with pytest.raises(d1.AuditBlocked, match="ROW_OUTSIDE_CAPTURE_WINDOW"):
        _load_snapshot(tmp_path, digest, counts)


def test_naive_clock_uncertainty_remains_visible():
    rows = records()
    rows["decision_packets"][3]["created_at"] = "2026-10-10T00:02:03"
    assert classify_records(rows)["naive_packet_utc_assumed_not_clock_certified"] == 1


def test_public_root_guard_never_reads_production(monkeypatch):
    def forbidden(_):
        pytest.fail("production root must be rejected before any read")
    monkeypatch.setattr(d1, "audit", forbidden)
    for path in (Path("relative/readonly_research_staging"),
                 Path("/home/runtime/readonly_research_staging"),
                 Path("/databases/readonly_research_staging")):
        assert audit(path)["status"] == "D1_C_INTEGRITY_FAILURE"


@pytest.mark.parametrize("candidate", [
    "relative/readonly_research_staging",
    "/tmp/readonly_research_staging",
    "/var/lib/crypto-ai-research-audit-alt/readonly_research_staging",
    "/home/runtime/readonly_research_staging",
    "/var/lib/crypto-ai-research-audit/another_dataset",
])
def test_exact_authorized_research_root_rejects_alias_before_data_read(monkeypatch, candidate):
    from research_data import stress_d1_rejection_eligibility as eligibility

    # Synthetic source-verifier seam: tests the root policy after verified source
    # loading but before touching any Research component or producer path.
    monkeypatch.setattr(eligibility, "_source_verifier", lambda: {"source_loading": "TEST"})
    monkeypatch.setattr(d1, "audit", lambda *_: pytest.fail("dataset audit must not run"))
    monkeypatch.setattr(eligibility, "_read", lambda *_: pytest.fail("dataset read must not run"))
    result = eligibility.audit(Path(candidate))
    assert result["status"] == "D1_C_INTEGRITY_FAILURE"
    assert result["classification"] == "NOT_EMITTED"
    assert result["reason_code"] == "AUTHORIZED_RESEARCH_ROOT_REQUIRED"


def test_overwritten_signal_raw_does_not_fabricate_exclusion():
    rows = records()
    rows["decision_packets"][3]["metadata"]["signal_raw"] = "HOLD"
    result = classify_records(rows)
    assert result["classifications"]["UNKNOWN_ELIGIBILITY"] == 2
    assert result["classifications"]["PROVEN_NOT_ELIGIBLE"] == 2


def test_missing_original_signal_reasoning_is_unknown():
    rows = records()
    rows["decision_packets"][3].pop("reasoning")
    assert classify_records(rows)["classifications"]["UNKNOWN_ELIGIBILITY"] == 2


def test_linked_record_missing_required_score_fails_closed():
    rows = records()
    rows["rejection_store"][0].pop("score")
    with pytest.raises(d1.AuditBlocked, match="MISSING_REJECTION_RECORD_FIELD"):
        classify_records(rows)


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -1, True])
def test_linked_record_invalid_numeric_price_fails_closed(price):
    rows = records()
    rows["rejection_store"][0]["price"] = price
    with pytest.raises(d1.AuditBlocked, match="INVALID_REJECTION_RECORD"):
        classify_records(rows)


def test_missing_component_and_malformed_history_fail_closed():
    rows = records()
    rows.pop("admission_ledger")
    with pytest.raises(d1.AuditBlocked, match="ALL_COMPONENTS_REQUIRED"):
        classify_records(rows)
    rows = records()
    rows["decision_packets"][3]["state_history"] = ["bad"]
    with pytest.raises(d1.AuditBlocked, match="INVALID_STATE_HISTORY"):
        classify_records(rows)


def test_public_boundary_rejects_symlink_root(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    root = tmp_path / "readonly_research_staging"
    root.symlink_to(target, target_is_directory=True)
    result = audit(root)
    assert result["status"] == "D1_C_INTEGRITY_FAILURE"
    assert result["classification"] == "NOT_EMITTED"
    assert result["integrity_counts"] == "NOT_ESTABLISHED_ON_FAILED_VALIDATION"


def test_native_global_risk_gate_actor_is_preserved_separately_from_blocker():
    rows = records()
    rows["decision_packets"][3]["state_history"][0]["actor"] = "global_risk_gate"
    result = classify_records(rows)
    assert result["coverage_by_first_packet_reject_actor"]["global_risk_gate"] == {"UNKNOWN_ELIGIBILITY": 1}
    assert result["coverage_by_observed_first_blocker"]["UNKNOWN"]["UNKNOWN_ELIGIBILITY"] == 2
