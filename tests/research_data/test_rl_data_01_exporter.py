"""RL-DATA-01 isolated proof matrix for the offline PAPER exporter."""

from __future__ import annotations

import hashlib
import json
import re
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


def test_manifest_created_at_mismatch_fails_closed(tmp_path):
    files = _fixture(tmp_path / "fixture")
    manifest = json.loads(files["manifest_path"].read_text(encoding="utf-8"))
    manifest["created_at"] = 2.0
    _write_json(files["manifest_path"], manifest)

    with pytest.raises(SourceValidationError, match="created_at mismatch"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_ppl_event_schema_must_match_authority_manifest(tmp_path):
    files = _fixture(tmp_path / "fixture")
    records = [
        json.loads(line)
        for line in files["epoch_path"].read_text(encoding="utf-8").splitlines()
    ]
    for record in records:
        record["schema_version"] = 1
        if record["event_type"] == "POSITION_OPENED":
            for field in (
                "tp_price",
                "sl_price",
                "timeout_at",
                "recovery_eligible_until",
            ):
                record["payload"].pop(field, None)
    _write_jsonl(files["epoch_path"], records)

    with pytest.raises(SourceValidationError, match="event schema_version mismatch"):
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

def _rewrite_config_with_valid_internal_hash(path: Path, mutate) -> None:
    config = json.loads(path.read_text(encoding="utf-8"))
    mutate(config)
    payload = dict(config)
    payload.pop("snapshot_sha256", None)
    config["snapshot_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    _write_json(path, config)


def test_output_root_must_not_overlap_source_storage(tmp_path):
    files = _fixture(tmp_path / "fixture")
    output = files["source"] / "research_data"

    with pytest.raises(SourceValidationError, match="output_root overlaps source storage"):
        export_paper_dataset(_request(files, output))

    assert not output.exists()


def test_config_rejects_unknown_top_level_field_even_with_valid_internal_hash(tmp_path):
    files = _fixture(tmp_path / "fixture")

    _rewrite_config_with_valid_internal_hash(
        files["config_path"],
        lambda config: config.__setitem__("unexpected_future_field", "value"),
    )

    with pytest.raises(SourceValidationError, match="experiment config fields mismatch"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_config_rejects_activation_keys_drift_even_with_valid_internal_hash(tmp_path):
    files = _fixture(tmp_path / "fixture")

    def mutate(config):
        config["activation_overlay"]["allowed_keys"] = [
            "PB_MAX_POSITIONS",
            "SIGNAL_MIN_SCORE",
        ]

    _rewrite_config_with_valid_internal_hash(files["config_path"], mutate)

    with pytest.raises(SourceValidationError, match="allowed_keys mismatch"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_config_rejects_non_positive_activation_even_with_valid_internal_hash(tmp_path):
    files = _fixture(tmp_path / "fixture")

    def mutate(config):
        config["activation_overlay"]["overrides"]["PB_MAX_POSITIONS"] = "0"
        config["parameters"]["PB_MAX_POSITIONS"]["value"] = "0"

    _rewrite_config_with_valid_internal_hash(files["config_path"], mutate)

    with pytest.raises(SourceValidationError, match="must be >= 1"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_config_rejects_secret_like_parameter_even_with_valid_internal_hash(tmp_path):
    files = _fixture(tmp_path / "fixture")

    def mutate(config):
        config["parameters"]["MEXC_API_KEY"] = {
            "value": "must-not-export",
            "provenance": "EXPLICIT_ENVIRONMENT_FILE",
            "source": "secret.env",
            "callsites": [],
        }
        config["material_parameter_count"] = len(config["parameters"])

    _rewrite_config_with_valid_internal_hash(files["config_path"], mutate)

    with pytest.raises(SourceValidationError, match="secret-like parameter keys"):
        export_paper_dataset(_request(files, tmp_path / "research"))

def test_dataset_id_ignores_explanatory_reason_text_when_statuses_are_unchanged(tmp_path):
    files = _fixture(tmp_path / "fixture")
    statuses_a = _statuses()
    statuses_b = dict(statuses_a)
    statuses_b["dip"] = SourceStatus(
        status="NOT_AVAILABLE",
        reason="same governed status, different explanatory wording",
        evidence=("different-extraction-note",),
    )

    a = export_paper_dataset(
        _request(files, tmp_path / "research-a", statuses=statuses_a)
    )
    b = export_paper_dataset(
        _request(files, tmp_path / "research-b", statuses=statuses_b)
    )

    assert a.source_boundary_id == b.source_boundary_id
    assert a.dataset_id == b.dataset_id
    assert a.manifest["components"]["dip"]["reason"] != b.manifest["components"]["dip"]["reason"]


# ---------------------------------------------------------------------------
# Parite semantique du validateur F00 possede par Research.
#
# Le validateur pur de research_data remplace l'appel au module d'autorite
# runtime PAPER. Ces tests prouvent qu'AUCUNE validation scientifique du
# contrat F00 n'a ete affaiblie par ce remplacement.
# ---------------------------------------------------------------------------


def _mutated_manifest_export(tmp_path, mutate):
    files = _fixture(tmp_path / "fixture")
    manifest = json.loads(files["manifest_path"].read_text(encoding="utf-8"))
    mutate(manifest)
    _write_json(files["manifest_path"], manifest)
    return files


@pytest.mark.parametrize(
    "mutate, expected",
    [
        # role d'epoque exact
        (lambda m: m.__setitem__("epoch_role", "PPL_AUTHORITY_TRANSITION"),
         "requires epoch_role=F00_EXPERIMENT"),
        (lambda m: m.__setitem__("epoch_role", "UNKNOWN"),
         "requires epoch_role=F00_EXPERIMENT"),
        # schema de manifest attendu
        (lambda m: m.__setitem__("manifest_schema_version", 1),
         "must use schema v2"),
        # schema d'evenement PPL attendu
        (lambda m: m.__setitem__("ppl_event_schema_version", 1),
         "PPL event schema must be v2"),
        # predecessor_authority_epoch_id requis pour F00
        (lambda m: m.__setitem__("predecessor_authority_epoch_id", ""),
         "requires predecessor_authority_epoch_id"),
        (lambda m: m.__setitem__("predecessor_authority_epoch_id", EPOCH),
         "must differ from predecessor authority epoch"),
        (lambda m: m.__setitem__("predecessor_authority_epoch_id", 7),
         "must be a string"),
        # predecessor SHADOW incompatible avec le contrat F00 courant
        (lambda m: m.__setitem__("predecessor_shadow_epoch_id", "SHADOW-001"),
         "fields mismatch"),
        # champs manquants / surnumeraires
        (lambda m: m.pop("legacy_boundary_sha256"), "fields mismatch"),
        (lambda m: m.__setitem__("unexpected_field", 1), "fields mismatch"),
        # legacy_event_count entier non negatif
        (lambda m: m.__setitem__("legacy_event_count", -1),
         "non-negative integer"),
        (lambda m: m.__setitem__("legacy_event_count", 1.5),
         "non-negative integer"),
        (lambda m: m.__setitem__("legacy_event_count", True),
         "non-negative integer"),
        # created_at valide
        (lambda m: m.__setitem__("created_at", "1.0"), "created_at must be numeric"),
        (lambda m: m.__setitem__("created_at", True), "created_at must be numeric"),
        # initial_virtual_capital valide
        (lambda m: m.__setitem__("initial_virtual_capital", 0),
         "initial_virtual_capital must be > 0"),
        (lambda m: m.__setitem__("initial_virtual_capital", -10.0),
         "initial_virtual_capital must be > 0"),
        (lambda m: m.__setitem__("initial_virtual_capital", "100"),
         "initial_virtual_capital must be numeric"),
        # chaines d'identite non vides
        (lambda m: m.__setitem__("code_sha", "   "), "code_sha must be a non-empty"),
        (lambda m: m.__setitem__("config_snapshot_hash", ""),
         "config_snapshot_hash must be a non-empty"),
        (lambda m: m.__setitem__("legacy_boundary_sha256", 42),
         "legacy_boundary_sha256 must be a non-empty"),
        # formes de digests exactes (SHA-40 / SHA-256)
        (lambda m: m.__setitem__("code_sha", "a" * 39),
         "manifest.code_sha must be a lowercase 40-hex"),
        (lambda m: m.__setitem__("code_sha", "A" * 40),
         "manifest.code_sha must be a lowercase 40-hex"),
        (lambda m: m.__setitem__("legacy_boundary_sha256", "z" * 64),
         "manifest.legacy_boundary_sha256 must be a lowercase SHA-256"),
    ],
)
def test_f00_manifest_semantic_parity_fails_closed(tmp_path, mutate, expected):
    files = _mutated_manifest_export(tmp_path, mutate)
    with pytest.raises(SourceValidationError, match=re.escape(expected)):
        export_paper_dataset(_request(files, tmp_path / "research"))
    assert not (tmp_path / "research" / "datasets").exists()


def test_f00_manifest_non_finite_values_are_never_coerced_to_zero(tmp_path):
    """NaN/Infinity restent des refus, jamais des zeros silencieux."""

    files = _fixture(tmp_path / "fixture")
    raw = files["manifest_path"].read_text(encoding="utf-8")
    files["manifest_path"].write_text(
        raw.replace('"created_at": 1.0', '"created_at": NaN'), encoding="utf-8"
    )
    with pytest.raises(SourceValidationError):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_f00_manifest_must_be_a_json_object(tmp_path):
    files = _fixture(tmp_path / "fixture")
    files["manifest_path"].write_text("[]", encoding="utf-8")
    with pytest.raises(SourceValidationError, match="must be a JSON object"):
        export_paper_dataset(_request(files, tmp_path / "research"))

# ---------------------------------------------------------------------------
# RB3 — explicit BURN_IN_EXPERIMENT support.
# F00 behavior above remains the backward-compatibility baseline.
# ---------------------------------------------------------------------------


def _promote_fixture_identity_to_burn_in(files: dict[str, Path]) -> None:
    manifest = json.loads(files["manifest_path"].read_text(encoding="utf-8"))
    manifest["epoch_role"] = "BURN_IN_EXPERIMENT"
    manifest["manifest_schema_version"] = 3
    _write_json(files["manifest_path"], manifest)

    _rewrite_config_with_valid_internal_hash(
        files["config_path"],
        lambda config: config.__setitem__(
            "snapshot_schema", "BURN_IN_EXPERIMENT_CONFIG_V1"
        ),
    )


def test_rb3_burn_in_role_exports_with_distinct_authoritative_names(tmp_path):
    files = _fixture(tmp_path / "fixture")
    _promote_fixture_identity_to_burn_in(files)
    before = _source_bytes(files)

    result = export_paper_dataset(_request(files, tmp_path / "research"))

    authoritative = result.dataset_path / "authoritative"
    assert (authoritative / "burn_in_experiment_manifest.json").read_bytes() == (
        before[files["manifest_path"]]
    )
    assert (authoritative / "burn_in_experiment_config.json").read_bytes() == (
        before[files["config_path"]]
    )
    assert not (authoritative / "f00_experiment_manifest.json").exists()
    assert not (authoritative / "f00_experiment_config.json").exists()

    assert result.manifest["authoritative_manifest"]["epoch_role"] == (
        "BURN_IN_EXPERIMENT"
    )
    assert result.manifest["authoritative_manifest"]["manifest_schema_version"] == 3
    assert result.manifest["components"]["burn_in_experiment_manifest"][
        "status"
    ] == "COMPLETE"
    assert result.manifest["components"]["burn_in_experiment_config"][
        "status"
    ] == "COMPLETE"
    assert _source_bytes(files) == before


def test_rb3_burn_in_role_rejects_f00_manifest_schema(tmp_path):
    files = _fixture(tmp_path / "fixture")
    manifest = json.loads(files["manifest_path"].read_text(encoding="utf-8"))
    manifest["epoch_role"] = "BURN_IN_EXPERIMENT"
    # Deliberately retain F00 manifest schema v2.
    _write_json(files["manifest_path"], manifest)

    with pytest.raises(SourceValidationError, match="must use schema v3"):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_rb3_burn_in_role_rejects_f00_config_schema(tmp_path):
    files = _fixture(tmp_path / "fixture")
    manifest = json.loads(files["manifest_path"].read_text(encoding="utf-8"))
    manifest["epoch_role"] = "BURN_IN_EXPERIMENT"
    manifest["manifest_schema_version"] = 3
    _write_json(files["manifest_path"], manifest)

    with pytest.raises(
        SourceValidationError,
        match="BURN_IN_EXPERIMENT_CONFIG_V1",
    ):
        export_paper_dataset(_request(files, tmp_path / "research"))


def test_rb3_f00_output_names_remain_backward_compatible(tmp_path):
    files = _fixture(tmp_path / "fixture")
    result = export_paper_dataset(_request(files, tmp_path / "research"))
    authoritative = result.dataset_path / "authoritative"

    assert (authoritative / "f00_experiment_manifest.json").exists()
    assert (authoritative / "f00_experiment_config.json").exists()
    assert not (authoritative / "burn_in_experiment_manifest.json").exists()
    assert not (authoritative / "burn_in_experiment_config.json").exists()

# ---------------------------------------------------------------------------
# RB4 — immutable accumulating capture and final burn-in designation.
# ---------------------------------------------------------------------------


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _append_closed_lifecycle(files: dict[str, Path]) -> None:
    events = (
        make_position_opened_event(
            event_id="ev-4",
            paper_epoch_id=EPOCH,
            sequence=4,
            timestamp=30.0,
            trade_id="trade-2",
            symbol="ETH/USDT",
            side="LONG",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            decision_id="packet-2",
            schema_version=2,
            tp_price=120.0,
            sl_price=90.0,
            timeout_at=100.0,
            recovery_eligible_until=200.0,
        ),
        make_position_closed_event(
            event_id="ev-5",
            paper_epoch_id=EPOCH,
            sequence=5,
            timestamp=40.0,
            trade_id="trade-2",
            exit_price=105.0,
            exit_fee=0.01,
            decision_id=None,
            schema_version=2,
        ),
    )
    with files["epoch_path"].open("ab") as handle:
        for event in events:
            handle.write(ppl_wire._canonical_line(event))


def _burn_in_capture_request(
    files: dict[str, Path], output_root: Path, *, extracted_at: str
) -> PaperExportRequest:
    return replace(
        _request(files, output_root, extracted_at=extracted_at),
        decision_packet_paths=(),
        decision_identity_journal_path=None,
    )


def test_rb4_accumulating_capture_and_finalization_are_immutable(tmp_path):
    from research_data.burn_in_finalization import (
        BurnInQuiescence,
        designate_final_burn_in_dataset,
    )

    files = _fixture(tmp_path / "fixture")
    _promote_fixture_identity_to_burn_in(files)
    source_before = _source_bytes(files)

    first = export_paper_dataset(
        _burn_in_capture_request(
            files,
            tmp_path / "research-a",
            extracted_at="2026-09-26T03:30:00Z",
        )
    )
    second = export_paper_dataset(
        _burn_in_capture_request(
            files,
            tmp_path / "research-b",
            extracted_at="2026-09-26T04:00:00Z",
        )
    )

    assert first.source_boundary_id == second.source_boundary_id
    assert first.dataset_id == second.dataset_id
    assert _source_bytes(files) == source_before

    first_bytes = _tree_bytes(first.dataset_path)
    second_bytes = _tree_bytes(second.dataset_path)

    _append_closed_lifecycle(files)
    source_after_deliberate_append = _source_bytes(files)

    final_capture = export_paper_dataset(
        _burn_in_capture_request(
            files,
            tmp_path / "research-c",
            extracted_at="2026-09-26T05:00:00Z",
        )
    )
    assert final_capture.source_boundary_id != first.source_boundary_id
    assert final_capture.dataset_id != first.dataset_id
    assert final_capture.manifest["source_boundary_identity"][
        "source_event_count"
    ] == 5
    assert final_capture.manifest["source_boundary_identity"][
        "source_last_sequence"
    ] == 5

    final_capture_bytes = _tree_bytes(final_capture.dataset_path)
    result = designate_final_burn_in_dataset(
        dataset_path=final_capture.dataset_path,
        designation_root=tmp_path / "research-finalization",
        quiescence=BurnInQuiescence(
            authority_process_stopped=True,
            pending_order_count=0,
            lifecycle_transitions_in_flight=0,
        ),
        designated_at_utc="2026-09-26T05:10:00Z",
        protected_roots=(files["source"],),
    )

    assert result.document["designation"] == "FINAL_BURN_IN_DATASET"
    assert result.document["dataset_id"] == final_capture.dataset_id
    assert result.document["source_boundary_id"] == final_capture.source_boundary_id
    assert result.document["source_event_count"] == 5
    assert result.document["source_last_sequence"] == 5
    assert result.document["closed_lifecycle_count"] == 2
    assert result.document["unresolved_lifecycle_count"] == 0
    assert result.document["open_lifecycle_count"] == 0
    assert result.designation_path.is_file()

    assert _tree_bytes(first.dataset_path) == first_bytes
    assert _tree_bytes(second.dataset_path) == second_bytes
    assert _tree_bytes(final_capture.dataset_path) == final_capture_bytes
    assert _source_bytes(files) == source_after_deliberate_append


def test_rb4_final_designation_id_ignores_publication_time(tmp_path):
    from research_data.burn_in_finalization import (
        BurnInQuiescence,
        designate_final_burn_in_dataset,
    )

    files = _fixture(tmp_path / "fixture")
    _promote_fixture_identity_to_burn_in(files)
    capture = export_paper_dataset(
        _burn_in_capture_request(
            files,
            tmp_path / "research",
            extracted_at="2026-09-26T03:30:00Z",
        )
    )
    quiescence = BurnInQuiescence(
        authority_process_stopped=True,
        pending_order_count=0,
        lifecycle_transitions_in_flight=0,
    )
    first = designate_final_burn_in_dataset(
        dataset_path=capture.dataset_path,
        designation_root=tmp_path / "final-a",
        quiescence=quiescence,
        designated_at_utc="2026-09-26T04:00:00Z",
    )
    second = designate_final_burn_in_dataset(
        dataset_path=capture.dataset_path,
        designation_root=tmp_path / "final-b",
        quiescence=quiescence,
        designated_at_utc="2026-09-27T04:00:00Z",
    )

    assert first.designation_id == second.designation_id
    assert first.document["designated_at_utc"] != second.document["designated_at_utc"]


def test_rb4_final_designation_is_write_once_and_rejects_non_quiescence(tmp_path):
    from research_data.burn_in_finalization import (
        BurnInQuiescence,
        BurnInQuiescenceError,
        FinalDesignationExistsError,
        designate_final_burn_in_dataset,
    )

    files = _fixture(tmp_path / "fixture")
    _promote_fixture_identity_to_burn_in(files)
    capture = export_paper_dataset(
        _burn_in_capture_request(
            files,
            tmp_path / "research",
            extracted_at="2026-09-26T03:30:00Z",
        )
    )
    root = tmp_path / "final"

    with pytest.raises(BurnInQuiescenceError):
        designate_final_burn_in_dataset(
            dataset_path=capture.dataset_path,
            designation_root=root,
            quiescence=BurnInQuiescence(
                authority_process_stopped=False,
                pending_order_count=0,
                lifecycle_transitions_in_flight=0,
            ),
            designated_at_utc="2026-09-26T04:00:00Z",
        )

    quiescence = BurnInQuiescence(
        authority_process_stopped=True,
        pending_order_count=0,
        lifecycle_transitions_in_flight=0,
    )
    designate_final_burn_in_dataset(
        dataset_path=capture.dataset_path,
        designation_root=root,
        quiescence=quiescence,
        designated_at_utc="2026-09-26T04:00:00Z",
    )
    with pytest.raises(FinalDesignationExistsError):
        designate_final_burn_in_dataset(
            dataset_path=capture.dataset_path,
            designation_root=root,
            quiescence=quiescence,
            designated_at_utc="2026-09-27T04:00:00Z",
        )


def test_rb4_finalizer_rejects_f00_and_dataset_tampering(tmp_path):
    from research_data.burn_in_finalization import (
        BurnInDatasetValidationError,
        BurnInQuiescence,
        designate_final_burn_in_dataset,
    )

    f00_files = _fixture(tmp_path / "f00")
    f00_capture = export_paper_dataset(
        replace(
            _request(f00_files, tmp_path / "research-f00"),
            decision_packet_paths=(),
            decision_identity_journal_path=None,
        )
    )
    quiescence = BurnInQuiescence(
        authority_process_stopped=True,
        pending_order_count=0,
        lifecycle_transitions_in_flight=0,
    )
    with pytest.raises(BurnInDatasetValidationError):
        designate_final_burn_in_dataset(
            dataset_path=f00_capture.dataset_path,
            designation_root=tmp_path / "final-f00",
            quiescence=quiescence,
            designated_at_utc="2026-09-26T04:00:00Z",
        )

    files = _fixture(tmp_path / "burn")
    _promote_fixture_identity_to_burn_in(files)
    capture = export_paper_dataset(
        _burn_in_capture_request(
            files,
            tmp_path / "research-burn",
            extracted_at="2026-09-26T03:30:00Z",
        )
    )
    ppl_copy = capture.dataset_path / "authoritative" / "ppl_events.jsonl"
    ppl_copy.write_bytes(ppl_copy.read_bytes() + b"\n")

    with pytest.raises(BurnInDatasetValidationError):
        designate_final_burn_in_dataset(
            dataset_path=capture.dataset_path,
            designation_root=tmp_path / "final-tampered",
            quiescence=quiescence,
            designated_at_utc="2026-09-26T04:00:00Z",
        )


def test_rb4_finalizer_rejects_research_output_under_protected_paper_root(tmp_path):
    from research_data.burn_in_finalization import (
        BurnInFinalizationError,
        BurnInQuiescence,
        designate_final_burn_in_dataset,
    )

    files = _fixture(tmp_path / "fixture")
    _promote_fixture_identity_to_burn_in(files)
    capture = export_paper_dataset(
        _burn_in_capture_request(
            files,
            tmp_path / "research",
            extracted_at="2026-09-26T03:30:00Z",
        )
    )

    with pytest.raises(BurnInFinalizationError, match="protected PAPER/runtime root"):
        designate_final_burn_in_dataset(
            dataset_path=capture.dataset_path,
            designation_root=files["source"] / "research-finalization",
            quiescence=BurnInQuiescence(
                authority_process_stopped=True,
                pending_order_count=0,
                lifecycle_transitions_in_flight=0,
            ),
            designated_at_utc="2026-09-26T04:00:00Z",
            protected_roots=(files["source"],),
        )

