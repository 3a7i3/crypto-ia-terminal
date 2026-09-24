"""RL-DATA-01 isolated proof matrix for the offline PAPER exporter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from paper_trading import durable_event_store as ppl_wire
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
)
from research_data.paper_exporter import (
    DatasetExistsError,
    PaperExportRequest,
    SourceStatus,
    SourceValidationError,
    export_paper_dataset,
)

EPOCH = "F00-EPOCH-TEST-001"
CODE_SHA = "1" * 40
CONFIG_HASH = "2" * 64
RUNTIME_SHA = "3" * 40
LEGACY_SHA = "4" * 64
OVERLAY_SHA = "5" * 64
EXPORTER_SHA = "6" * 40


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(_canonical(record) + b"\n" for record in records))


def _decision_payload_digest(payload: dict) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _statuses() -> dict[str, SourceStatus]:
    return {
        "dip": SourceStatus(
            status="NOT_AVAILABLE",
            reason="NOT_STARTED",
            evidence=("runtime_provenance_snapshot:NOT_STARTED",),
        ),
        "regret": SourceStatus(
            status="UNRESOLVED_PROVENANCE",
            reason="no explicit F00 authority binding",
        ),
        "rejection_store": SourceStatus(
            status="UNBOUND",
            reason="no explicit F00 experiment binding",
        ),
        "admission_ledger": SourceStatus(
            status="UNBOUND",
            reason="no packet/trace/epoch identity",
        ),
    }


def _fixture(
    root: Path,
    *,
    exit_price: float = 110.0,
) -> dict[str, Path]:
    source = root / "source"
    store_root = source / "ppl_store"
    epoch_path = (
        store_root
        / "epochs"
        / f"{hashlib.sha256(EPOCH.encode('utf-8')).hexdigest()}.jsonl"
    )

    events = (
        make_epoch_created_event(
            event_id="ev-1",
            paper_epoch_id=EPOCH,
            sequence=1,
            timestamp=1.0,
            initial_virtual_capital=100.0,
            code_sha=CODE_SHA,
            config_snapshot_hash=CONFIG_HASH,
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="ev-2",
            paper_epoch_id=EPOCH,
            sequence=2,
            timestamp=10.0,
            trade_id="trade-1",
            symbol="BTC/USDT",
            side="LONG",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            decision_id="packet-1",
            schema_version=2,
            tp_price=120.0,
            sl_price=90.0,
            timeout_at=100.0,
            recovery_eligible_until=200.0,
        ),
        make_position_closed_event(
            event_id="ev-3",
            paper_epoch_id=EPOCH,
            sequence=3,
            timestamp=20.0,
            trade_id="trade-1",
            exit_price=exit_price,
            exit_fee=0.01,
            decision_id=None,
            schema_version=2,
        ),
    )
    epoch_path.parent.mkdir(parents=True, exist_ok=True)
    epoch_path.write_bytes(b"".join(ppl_wire._canonical_line(event) for event in events))

    manifest_path = source / "f00.manifest.json"
    manifest = {
        "manifest_schema_version": 2,
        "paper_epoch_id": EPOCH,
        "created_at": 1.0,
        "initial_virtual_capital": 100.0,
        "code_sha": CODE_SHA,
        "config_snapshot_hash": CONFIG_HASH,
        "legacy_boundary_sha256": LEGACY_SHA,
        "legacy_event_count": 7,
        "epoch_role": "F00_EXPERIMENT",
        "ppl_event_schema_version": 2,
        "predecessor_authority_epoch_id": "PPL-PREDECESSOR-001",
    }
    _write_json(manifest_path, manifest)

    config_path = source / "f00.experiment-config.json"
    config_payload = {
        "snapshot_schema": "F00_EXPERIMENT_CONFIG_V1",
        "paper_epoch_id": EPOCH,
        "runtime_source_sha": RUNTIME_SHA,
        "prestart_environment_files_in_precedence_order": ["base.env"],
        "activation_overlay": {
            "path": "activation.env",
            "sha256": OVERLAY_SHA,
            "allowed_keys": ["PB_MAX_POSITIONS"],
            "overrides": {"PB_MAX_POSITIONS": "2"},
            "must_not_be_wired_before_owner_authorization": True,
        },
        "prestart_guard": {"PB_MAX_POSITIONS": "0"},
        "material_parameter_count": 1,
        "parameters": {
            "PB_MAX_POSITIONS": {
                "value": "2",
                "provenance": "EXPLICIT_ENVIRONMENT_FILE",
                "source": "activation.env",
                "callsites": [],
            }
        },
    }
    config = {
        **config_payload,
        "snapshot_sha256": hashlib.sha256(_canonical(config_payload)).hexdigest(),
    }
    _write_json(config_path, config)

    packets_path = source / "decision_packets_2026-09-20.jsonl"
    selected_packet = {
        "packet_id": "packet-1",
        "symbol": "BTC/USDT",
        "created_cycle_id": "7",
        "lifecycle_state": "EXECUTION_PENDING",
        "metadata": {"trace_id": "trace-1"},
    }
    unrelated_packet = {
        "packet_id": "packet-other",
        "symbol": "ETH/USDT",
        "created_cycle_id": "8",
        "lifecycle_state": "REJECTED",
        "metadata": {"trace_id": "trace-other"},
    }
    _write_jsonl(packets_path, [unrelated_packet, selected_packet])

    journal_path = source / "decision_identity_journal.jsonl"
    selected_payload = {
        "namespace": "advisor_loop.analyze_symbol",
        "cycle": 7,
        "symbol": "BTC/USDT",
        "action": None,
    }
    selected_identity = {
        "schema_version": 2,
        "decision_id": "trace-1",
        "namespace": "advisor_loop.analyze_symbol",
        "cycle": 7,
        "symbol": "BTC/USDT",
        "action": None,
        "payload": selected_payload,
        "payload_digest": _decision_payload_digest(selected_payload),
        "lifecycle_state": "CREATED",
        "bound_intent_digest": None,
        "ts": 10.0,
    }
    unrelated_payload = {
        "namespace": "advisor_loop.analyze_symbol",
        "cycle": 8,
        "symbol": "ETH/USDT",
        "action": None,
    }
    unrelated_identity = {
        "schema_version": 2,
        "decision_id": "trace-other",
        "namespace": "advisor_loop.analyze_symbol",
        "cycle": 8,
        "symbol": "ETH/USDT",
        "action": None,
        "payload": unrelated_payload,
        "payload_digest": _decision_payload_digest(unrelated_payload),
        "lifecycle_state": "CREATED",
        "bound_intent_digest": None,
        "ts": 11.0,
    }
    _write_jsonl(journal_path, [unrelated_identity, selected_identity])

    return {
        "source": source,
        "store_root": store_root,
        "epoch_path": epoch_path,
        "manifest_path": manifest_path,
        "config_path": config_path,
        "packets_path": packets_path,
        "journal_path": journal_path,
    }


def _request(
    files: dict[str, Path],
    output_root: Path,
    *,
    extracted_at: str = "2026-09-24T04:30:00Z",
    exporter_sha: str = EXPORTER_SHA,
    statuses: dict[str, SourceStatus] | None = None,
) -> PaperExportRequest:
    return PaperExportRequest(
        paper_epoch_id=EPOCH,
        ppl_store_root=files["store_root"],
        experiment_manifest_path=files["manifest_path"],
        experiment_config_path=files["config_path"],
        output_root=output_root,
        exporter_code_sha=exporter_sha,
        extracted_at_utc=extracted_at,
        optional_source_statuses=statuses or _statuses(),
        decision_packet_paths=(files["packets_path"],),
        decision_identity_journal_path=files["journal_path"],
        certification_references={
            "f00": "F00_FINAL_SCIENTIFIC_EXPERIMENT_CERTIFIED",
            "fin02": "WITHIN_TOLERANCE",
        },
    )


def _source_bytes(files: dict[str, Path]) -> dict[Path, bytes]:
    return {
        files["epoch_path"]: files["epoch_path"].read_bytes(),
        files["manifest_path"]: files["manifest_path"].read_bytes(),
        files["config_path"]: files["config_path"].read_bytes(),
        files["packets_path"]: files["packets_path"].read_bytes(),
        files["journal_path"]: files["journal_path"].read_bytes(),
    }


def test_success_exports_exact_authoritative_bytes_and_certified_optional_subset(tmp_path):
    files = _fixture(tmp_path / "fixture")
    before = _source_bytes(files)

    result = export_paper_dataset(_request(files, tmp_path / "research"))

    assert result.dataset_path.is_dir()
    assert (
        result.dataset_path / "authoritative" / "ppl_events.jsonl"
    ).read_bytes() == before[files["epoch_path"]]
    assert (
        result.dataset_path / "authoritative" / "f00_experiment_manifest.json"
    ).read_bytes() == before[files["manifest_path"]]
    assert (
        result.dataset_path / "authoritative" / "f00_experiment_config.json"
    ).read_bytes() == before[files["config_path"]]

    packets = (
        result.dataset_path / "optional" / "decision_packets.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    identities = (
        result.dataset_path / "optional" / "decision_identity_records.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert len(packets) == 1
    assert len(identities) == 1
    assert json.loads(packets[0])["packet_id"] == "packet-1"
    assert json.loads(identities[0])["decision_id"] == "trace-1"

    manifest = json.loads(
        (result.dataset_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["dataset_id"] == result.dataset_id
    assert manifest["source_boundary_id"] == result.source_boundary_id
    assert manifest["source_boundary_identity"]["source_first_timestamp"] == 1.0
    assert manifest["source_boundary_identity"]["source_last_timestamp"] == 20.0
    assert manifest["completeness_status"] == "COMPLETE"
    assert manifest["components"]["dip"]["status"] == "NOT_AVAILABLE"
    assert manifest["components"]["regret"]["status"] == "UNRESOLVED_PROVENANCE"
    assert manifest["components"]["rejection_store"]["status"] == "UNBOUND"
    assert manifest["components"]["admission_ledger"]["status"] == "UNBOUND"

    assert _source_bytes(files) == before
    assert not (files["store_root"] / ".ppl-event-store.lock").exists()


def test_same_boundary_and_components_keep_ids_across_extraction_time_and_output_root(
    tmp_path,
):
    files = _fixture(tmp_path / "fixture")

    first = export_paper_dataset(
        _request(
            files,
            tmp_path / "research-a",
            extracted_at="2026-09-24T04:30:00Z",
        )
    )
    second = export_paper_dataset(
        _request(
            files,
            tmp_path / "research-b",
            extracted_at="2026-09-25T09:00:00Z",
        )
    )

    assert first.source_boundary_id == second.source_boundary_id
    assert first.dataset_id == second.dataset_id
    assert (
        first.dataset_path / "optional" / "decision_packets.jsonl"
    ).read_bytes() == (
        second.dataset_path / "optional" / "decision_packets.jsonl"
    ).read_bytes()
    assert first.manifest["extraction_provenance"]["extracted_at_utc"] != (
        second.manifest["extraction_provenance"]["extracted_at_utc"]
    )


def test_ids_do_not_depend_on_absolute_source_paths(tmp_path):
    left = _fixture(tmp_path / "left")
    right = _fixture(tmp_path / "right")

    a = export_paper_dataset(_request(left, tmp_path / "research-left"))
    b = export_paper_dataset(_request(right, tmp_path / "research-right"))

    assert a.source_boundary_id == b.source_boundary_id
    assert a.dataset_id == b.dataset_id


def test_changed_ppl_bytes_change_source_boundary_and_dataset_identity(tmp_path):
    left = _fixture(tmp_path / "left", exit_price=110.0)
    right = _fixture(tmp_path / "right", exit_price=111.0)

    a = export_paper_dataset(_request(left, tmp_path / "research-left"))
    b = export_paper_dataset(_request(right, tmp_path / "research-right"))

    assert a.source_boundary_id != b.source_boundary_id
    assert a.dataset_id != b.dataset_id


def test_exporter_code_sha_changes_dataset_id_not_source_boundary_id(tmp_path):
    files = _fixture(tmp_path / "fixture")

    a = export_paper_dataset(
        _request(files, tmp_path / "research-a", exporter_sha="a" * 40)
    )
    b = export_paper_dataset(
        _request(files, tmp_path / "research-b", exporter_sha="b" * 40)
    )

    assert a.source_boundary_id == b.source_boundary_id
    assert a.dataset_id != b.dataset_id


def test_truncated_ppl_fails_closed_without_dataset(tmp_path):
    files = _fixture(tmp_path / "fixture")
    raw = files["epoch_path"].read_bytes()
    files["epoch_path"].write_bytes(raw[:-1])
    output = tmp_path / "research"

    with pytest.raises(SourceValidationError, match="final newline"):
        export_paper_dataset(_request(files, output))

    assert not (output / "datasets").exists()


def test_manifest_epoch_mismatch_fails_closed(tmp_path):
    files = _fixture(tmp_path / "fixture")
    manifest = json.loads(files["manifest_path"].read_text(encoding="utf-8"))
    manifest["paper_epoch_id"] = "OTHER-EPOCH"
    _write_json(files["manifest_path"], manifest)

    with pytest.raises(SourceValidationError, match="paper_epoch_id mismatch"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_manifest_digest_shape_mismatch_fails_closed(tmp_path):
    files = _fixture(tmp_path / "fixture")
    manifest = json.loads(files["manifest_path"].read_text(encoding="utf-8"))
    manifest["config_snapshot_hash"] = "not-a-sha256"
    _write_json(files["manifest_path"], manifest)

    with pytest.raises(SourceValidationError, match="manifest.config_snapshot_hash"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_config_internal_snapshot_hash_mismatch_fails_closed(tmp_path):
    files = _fixture(tmp_path / "fixture")
    config = json.loads(files["config_path"].read_text(encoding="utf-8"))
    config["parameters"]["PB_MAX_POSITIONS"]["value"] = "99"
    _write_json(files["config_path"], config)

    with pytest.raises(SourceValidationError, match="snapshot_sha256"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_missing_decision_packet_fails_closed(tmp_path):
    files = _fixture(tmp_path / "fixture")
    records = [
        json.loads(line)
        for line in files["packets_path"].read_text(encoding="utf-8").splitlines()
    ]
    records = [record for record in records if record["packet_id"] != "packet-1"]
    _write_jsonl(files["packets_path"], records)

    with pytest.raises(SourceValidationError, match="missing DecisionPacket"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_duplicate_selected_decision_packet_fails_closed(tmp_path):
    files = _fixture(tmp_path / "fixture")
    records = [
        json.loads(line)
        for line in files["packets_path"].read_text(encoding="utf-8").splitlines()
    ]
    selected = next(record for record in records if record["packet_id"] == "packet-1")
    _write_jsonl(files["packets_path"], records + [selected])

    with pytest.raises(SourceValidationError, match="duplicated"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_decision_identity_payload_digest_mismatch_fails_closed(tmp_path):
    files = _fixture(tmp_path / "fixture")
    records = [
        json.loads(line)
        for line in files["journal_path"].read_text(encoding="utf-8").splitlines()
    ]
    selected = next(record for record in records if record["decision_id"] == "trace-1")
    selected["payload"]["cycle"] = 999
    _write_jsonl(files["journal_path"], records)

    with pytest.raises(SourceValidationError, match="payload_digest mismatch"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_declared_source_statuses_must_be_complete(tmp_path):
    files = _fixture(tmp_path / "fixture")
    statuses = _statuses()
    statuses.pop("dip")

    with pytest.raises(SourceValidationError, match="keys mismatch"):
        export_paper_dataset(
            _request(files, tmp_path / "research", statuses=statuses)
        )


def test_existing_dataset_directory_is_never_overwritten(tmp_path):
    files = _fixture(tmp_path / "fixture")
    request = _request(files, tmp_path / "research")
    first = export_paper_dataset(request)
    manifest_before = (first.dataset_path / "manifest.json").read_bytes()

    with pytest.raises(DatasetExistsError):
        export_paper_dataset(
            replace(request, extracted_at_utc="2026-09-25T00:00:00Z")
        )

    assert (first.dataset_path / "manifest.json").read_bytes() == manifest_before


def test_optional_decision_layer_can_be_explicitly_not_included(tmp_path):
    files = _fixture(tmp_path / "fixture")
    request = replace(
        _request(files, tmp_path / "research"),
        decision_packet_paths=(),
        decision_identity_journal_path=None,
    )

    result = export_paper_dataset(request)

    assert result.manifest["components"]["decision_packets"]["status"] == "NOT_INCLUDED"
    assert (
        result.manifest["components"]["decision_identity_records"]["status"]
        == "NOT_INCLUDED"
    )
    assert not (result.dataset_path / "optional").exists()