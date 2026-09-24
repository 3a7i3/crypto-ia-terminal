"""RL-DATA-01 - immutable PAPER to Research dataset exporter.

This module is deliberately offline and source-path explicit.

Safety properties:
- no production path defaults;
- no environment lookup;
- no service/runtime imports;
- no DurableEventStore lock acquisition because load_epoch opens a writable lock;
- source files are read-only inputs;
- output is written only below the caller-supplied Research root;
- authoritative source bytes are copied byte-for-byte;
- optional decision evidence is selected only by exact certified identities;
- missing/unbound evidence is represented, never reconstructed.

The implementation deliberately uses the PPL durable-store decoder/canonicalizer
without constructing DurableEventStore. That reuses frozen PPL wire validation
while avoiding the store lock-file write side effect.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from paper_trading import durable_event_store as ppl_wire
from paper_trading.ledger_events import LedgerEvent, LedgerEventType
from paper_trading.paper_portfolio_ledger import project
from paper_trading.ppl_authority_runtime import (
    AuthorityManifestError,
    load_authority_manifest,
)

_SOURCE_BOUNDARY_SCHEMA = "RL_DATA_01_SOURCE_BOUNDARY_V1"
_DATASET_SCHEMA_VERSION = 1
_DERIVATION = "PAPER_EXPORT"
_SOURCE_DOMAIN = "PAPER"
_SOURCE_AUTHORITY = "PPL_AUTHORITY"
_F00_ROLE = "F00_EXPERIMENT"
_F00_CONFIG_SCHEMA = "F00_EXPERIMENT_CONFIG_V1"

_ALLOWED_COMPONENT_STATES = frozenset(
    {
        "COMPLETE",
        "PARTIAL",
        "UNRESOLVED",
        "UNRESOLVED_PROVENANCE",
        "UNBOUND",
        "NOT_AVAILABLE",
        "NOT_STARTED",
        "NOT_APPLICABLE",
        "NOT_INCLUDED",
    }
)
_REQUIRED_DECLARED_SOURCES = frozenset(
    {"dip", "regret", "rejection_store", "admission_ledger"}
)
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PaperExportError(RuntimeError):
    """Fail-closed RL-DATA-01 export error."""


class SourceValidationError(PaperExportError):
    """A source violates the certified RL-DATA-01 contract."""


class SourceMutationError(PaperExportError):
    """A source changed across one export invocation."""


class DatasetExistsError(PaperExportError):
    """The immutable target dataset directory already exists."""


class _DuplicateJSONKey(ValueError):
    pass


@dataclass(frozen=True)
class SourceStatus:
    """Governed declaration for a source unavailable to the v1 dataset."""

    status: str
    reason: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_COMPONENT_STATES:
            raise ValueError(f"unsupported source status: {self.status!r}")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("source status reason must be non-empty")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, str) and item for item in self.evidence
        ):
            raise ValueError("source status evidence must be a tuple of strings")


@dataclass(frozen=True)
class PaperExportRequest:
    """All inputs are explicit; no runtime/environment discovery occurs here."""

    paper_epoch_id: str
    ppl_store_root: Path
    experiment_manifest_path: Path
    experiment_config_path: Path
    output_root: Path
    exporter_code_sha: str
    extracted_at_utc: str
    optional_source_statuses: Mapping[str, SourceStatus]
    decision_packet_paths: tuple[Path, ...] = ()
    decision_identity_journal_path: Path | None = None
    certification_references: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExportResult:
    dataset_id: str
    source_boundary_id: str
    dataset_path: Path
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class _FileSnapshot:
    path: Path
    raw: bytes
    sha256: str
    size: int


@dataclass(frozen=True)
class _PrefixSnapshot:
    path: Path
    raw: bytes
    sha256: str
    size: int


def _duplicate_key_guard(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateJSONKey(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _strict_json_loads(raw: bytes, *, source: Path, context: str = "") -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SourceValidationError(f"{source}: invalid UTF-8 {context}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_duplicate_key_guard,
            parse_constant=_reject_json_constant,
        )
    except (_DuplicateJSONKey, json.JSONDecodeError, ValueError) as exc:
        suffix = f" ({context})" if context else ""
        raise SourceValidationError(f"{source}: invalid JSON{suffix}: {exc}") from exc


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SourceValidationError(f"canonical JSON failed: {exc}") from exc


def _canonical_jsonl(records: Sequence[Mapping[str, Any]], *, key: str) -> bytes:
    ordered = sorted(records, key=lambda record: str(record.get(key) or ""))
    return b"".join(_canonical_json_bytes(record) + b"\n" for record in ordered)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_sha40(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise SourceValidationError(f"{field_name} must be a lowercase 40-hex Git SHA")
    return value


def _require_sha256(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SourceValidationError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return value


def _require_regular_file(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise SourceValidationError(f"source file not found: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise SourceValidationError(f"source must be a regular non-symlink file: {path}")
    return info


def _read_regular_file(path: Path) -> _FileSnapshot:
    info = _require_regular_file(path)
    raw = path.read_bytes()
    if len(raw) != info.st_size:
        raise SourceMutationError(f"source size changed while reading: {path}")
    return _FileSnapshot(path=path, raw=raw, sha256=_sha256_bytes(raw), size=len(raw))


def _read_prefix_snapshot(path: Path) -> _PrefixSnapshot:
    info = _require_regular_file(path)
    boundary = info.st_size
    with path.open("rb") as handle:
        raw = handle.read(boundary)
    if len(raw) != boundary:
        raise SourceMutationError(f"append-only source shrank while reading: {path}")
    return _PrefixSnapshot(
        path=path,
        raw=raw,
        sha256=_sha256_bytes(raw),
        size=boundary,
    )


def _verify_full_file_unchanged(snapshot: _FileSnapshot) -> None:
    current = _read_regular_file(snapshot.path)
    if current.size != snapshot.size or current.sha256 != snapshot.sha256:
        raise SourceMutationError(f"source changed during export: {snapshot.path}")


def _verify_prefix_unchanged(snapshot: _PrefixSnapshot) -> None:
    info = _require_regular_file(snapshot.path)
    if info.st_size < snapshot.size:
        raise SourceMutationError(f"append-only source shrank during export: {snapshot.path}")
    with snapshot.path.open("rb") as handle:
        current_prefix = handle.read(snapshot.size)
    if len(current_prefix) != snapshot.size:
        raise SourceMutationError(
            f"append-only source prefix became unreadable: {snapshot.path}"
        )
    if _sha256_bytes(current_prefix) != snapshot.sha256:
        raise SourceMutationError(
            f"append-only source prefix changed during export: {snapshot.path}"
        )


def _validate_extracted_at(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise SourceValidationError("extracted_at_utc must be a non-empty ISO timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise SourceValidationError("extracted_at_utc must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceValidationError("extracted_at_utc must include a timezone")
    return value


def _validate_declared_statuses(
    statuses: Mapping[str, SourceStatus],
) -> dict[str, SourceStatus]:
    actual = frozenset(statuses)
    if actual != _REQUIRED_DECLARED_SOURCES:
        missing = sorted(_REQUIRED_DECLARED_SOURCES - actual)
        extra = sorted(actual - _REQUIRED_DECLARED_SOURCES)
        raise SourceValidationError(
            f"optional_source_statuses keys mismatch: missing={missing}, extra={extra}"
        )
    out: dict[str, SourceStatus] = {}
    for key in sorted(statuses):
        value = statuses[key]
        if not isinstance(value, SourceStatus):
            raise SourceValidationError(f"{key} status must be SourceStatus")
        out[key] = value
    return out


def _epoch_file_path(root: Path, paper_epoch_id: str) -> Path:
    digest = hashlib.sha256(paper_epoch_id.encode("utf-8")).hexdigest()
    return root / "epochs" / f"{digest}.jsonl"


def _load_ppl_readonly(
    root: Path, paper_epoch_id: str
) -> tuple[_FileSnapshot, tuple[LedgerEvent, ...], Any]:
    """Validate one canonical PPL file without opening the store write lock."""

    source = _epoch_file_path(root, paper_epoch_id)
    snapshot = _read_regular_file(source)
    raw = snapshot.raw
    if not raw:
        raise SourceValidationError(f"empty PPL epoch file: {source}")
    if not raw.endswith(b"\n"):
        raise SourceValidationError(f"PPL epoch file lacks final newline: {source}")

    events: list[LedgerEvent] = []
    seen_ids: set[str] = set()
    expected_sequence = 1

    for record_number, raw_line in enumerate(raw.splitlines(keepends=True), 1):
        if not raw_line.endswith(b"\n"):
            raise SourceValidationError(
                f"{source}:record {record_number}: incomplete record"
            )
        body = raw_line[:-1]
        if not body.strip():
            raise SourceValidationError(f"{source}:record {record_number}: blank record")
        try:
            event = ppl_wire._decode_record(
                body, source=source, record_number=record_number
            )
            canonical = ppl_wire._canonical_line(event)
        except Exception as exc:
            raise SourceValidationError(
                f"{source}:record {record_number}: invalid PPL event: {exc}"
            ) from exc

        if canonical != raw_line:
            raise SourceValidationError(
                f"{source}:record {record_number}: non-canonical PPL encoding"
            )
        if event.paper_epoch_id != paper_epoch_id:
            raise SourceValidationError(
                f"{source}:record {record_number}: embedded epoch mismatch"
            )
        if event.sequence != expected_sequence:
            raise SourceValidationError(
                f"{source}:record {record_number}: sequence={event.sequence}, "
                f"expected={expected_sequence}"
            )
        expected_sequence += 1
        if event.event_id in seen_ids:
            raise SourceValidationError(
                f"{source}:record {record_number}: duplicate event_id={event.event_id!r}"
            )
        seen_ids.add(event.event_id)
        events.append(event)

    try:
        projection = project(tuple(events))
    except Exception as exc:
        raise SourceValidationError(f"PPL lifecycle projection failed: {exc}") from exc

    if projection.epoch is None or projection.paper_epoch_id != paper_epoch_id:
        raise SourceValidationError("PPL projection does not resolve requested epoch")
    return snapshot, tuple(events), projection


def _load_manifest(
    path: Path,
    *,
    paper_epoch_id: str,
    ppl_projection: Any,
) -> tuple[_FileSnapshot, Mapping[str, Any], Any]:
    snapshot = _read_regular_file(path)
    raw_doc = _strict_json_loads(snapshot.raw, source=path)
    if not isinstance(raw_doc, dict):
        raise SourceValidationError("F00 manifest must be a JSON object")
    try:
        manifest = load_authority_manifest(path)
    except AuthorityManifestError as exc:
        raise SourceValidationError(f"F00 manifest invalid: {exc}") from exc

    if manifest.epoch_role != _F00_ROLE:
        raise SourceValidationError(
            f"RL-DATA-01 requires epoch_role={_F00_ROLE}, got {manifest.epoch_role!r}"
        )
    if manifest.paper_epoch_id != paper_epoch_id:
        raise SourceValidationError("F00 manifest paper_epoch_id mismatch")

    epoch = ppl_projection.epoch
    if epoch is None:
        raise SourceValidationError("PPL projection has no epoch")
    if epoch.initial_virtual_capital != manifest.initial_virtual_capital:
        raise SourceValidationError("PPL/manifest initial capital mismatch")
    if epoch.code_sha != manifest.code_sha:
        raise SourceValidationError("PPL/manifest code_sha mismatch")
    if epoch.config_snapshot_hash != manifest.config_snapshot_hash:
        raise SourceValidationError("PPL/manifest config_snapshot_hash mismatch")

    return snapshot, raw_doc, manifest


def _load_experiment_config(
    path: Path, *, paper_epoch_id: str
) -> tuple[_FileSnapshot, Mapping[str, Any]]:
    snapshot = _read_regular_file(path)
    doc = _strict_json_loads(snapshot.raw, source=path)
    if not isinstance(doc, dict):
        raise SourceValidationError("experiment config must be a JSON object")

    if doc.get("snapshot_schema") != _F00_CONFIG_SCHEMA:
        raise SourceValidationError("unsupported experiment config snapshot_schema")
    if doc.get("paper_epoch_id") != paper_epoch_id:
        raise SourceValidationError("experiment config paper_epoch_id mismatch")

    stored_digest = _require_sha256(
        doc.get("snapshot_sha256"), field_name="experiment_config.snapshot_sha256"
    )
    payload = dict(doc)
    payload.pop("snapshot_sha256", None)
    calculated = _sha256_bytes(_canonical_json_bytes(payload))
    if calculated != stored_digest:
        raise SourceValidationError(
            "experiment config snapshot_sha256 does not match canonical payload"
        )

    _require_sha40(
        doc.get("runtime_source_sha"), field_name="experiment_config.runtime_source_sha"
    )
    parameters = doc.get("parameters")
    if not isinstance(parameters, dict):
        raise SourceValidationError("experiment config parameters must be an object")
    count = doc.get("material_parameter_count")
    if not isinstance(count, int) or isinstance(count, bool) or count != len(parameters):
        raise SourceValidationError(
            "experiment config material_parameter_count mismatch"
        )
    if doc.get("prestart_guard") != {"PB_MAX_POSITIONS": "0"}:
        raise SourceValidationError("experiment config prestart_guard mismatch")

    overlay = doc.get("activation_overlay")
    if not isinstance(overlay, dict):
        raise SourceValidationError("experiment config activation_overlay missing")
    _require_sha256(
        overlay.get("sha256"), field_name="experiment_config.activation_overlay.sha256"
    )
    overrides = overlay.get("overrides")
    if not isinstance(overrides, dict) or set(overrides) != {"PB_MAX_POSITIONS"}:
        raise SourceValidationError(
            "experiment config activation overlay must only override PB_MAX_POSITIONS"
        )

    return snapshot, doc


def _jsonl_records(raw: bytes, *, source: Path) -> list[tuple[int, Mapping[str, Any]]]:
    if raw and not raw.endswith(b"\n"):
        raise SourceValidationError(f"{source}: JSONL source lacks final newline")
    records: list[tuple[int, Mapping[str, Any]]] = []
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            raise SourceValidationError(f"{source}:{line_number}: blank JSONL record")
        value = _strict_json_loads(line, source=source, context=f"line {line_number}")
        if not isinstance(value, dict):
            raise SourceValidationError(
                f"{source}:{line_number}: JSONL record must be an object"
            )
        records.append((line_number, value))
    return records


def _decision_payload_digest(payload: Mapping[str, Any]) -> str:
    try:
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SourceValidationError(
            f"DecisionIdentity payload canonicalization failed: {exc}"
        ) from exc
    return _sha256_bytes(raw)


def _extract_decision_evidence(
    *,
    events: Sequence[LedgerEvent],
    packet_paths: Sequence[Path],
    journal_path: Path,
) -> tuple[bytes, bytes, Mapping[str, Any], list[_FileSnapshot], _PrefixSnapshot]:
    open_events = [
        event for event in events if event.event_type is LedgerEventType.POSITION_OPENED
    ]
    if not open_events:
        raise SourceValidationError("decision evidence requested but PPL has no OPEN events")
    if any(not event.decision_id for event in open_events):
        raise SourceValidationError(
            "decision evidence requires a non-null decision_id on every PPL OPEN"
        )

    open_by_packet: dict[str, LedgerEvent] = {}
    for event in open_events:
        packet_id = str(event.decision_id)
        if packet_id in open_by_packet:
            raise SourceValidationError(f"duplicate PPL OPEN decision_id={packet_id!r}")
        open_by_packet[packet_id] = event
    expected_ids = set(open_by_packet)

    packet_sources: list[_FileSnapshot] = []
    source_meta: list[dict[str, Any]] = []
    matched: dict[str, tuple[Mapping[str, Any], Path, int]] = {}

    for path in packet_paths:
        snapshot = _read_regular_file(path)
        packet_sources.append(snapshot)
        records = _jsonl_records(snapshot.raw, source=path)
        matched_count = 0
        for line_number, record in records:
            packet_id = str(record.get("packet_id") or "")
            if packet_id not in expected_ids:
                continue
            if packet_id in matched:
                prior = matched[packet_id]
                raise SourceValidationError(
                    f"DecisionPacket {packet_id!r} duplicated at "
                    f"{prior[1]}:{prior[2]} and {path}:{line_number}"
                )
            matched[packet_id] = (record, path, line_number)
            matched_count += 1
        source_meta.append(
            {
                "path": str(path),
                "sha256": snapshot.sha256,
                "bytes": snapshot.size,
                "record_count": len(records),
                "matched_record_count": matched_count,
            }
        )

    missing = sorted(expected_ids - set(matched))
    if missing:
        raise SourceValidationError(f"missing DecisionPacket IDs: {missing}")

    packet_records: list[Mapping[str, Any]] = []
    packet_to_trace: dict[str, str] = {}
    packet_locations: dict[str, dict[str, Any]] = {}

    for packet_id in sorted(expected_ids):
        record, path, line_number = matched[packet_id]
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            raise SourceValidationError(f"DecisionPacket {packet_id!r} metadata missing")
        trace_id = metadata.get("trace_id")
        if not isinstance(trace_id, str) or not trace_id:
            raise SourceValidationError(f"DecisionPacket {packet_id!r} trace_id missing")

        ppl_symbol = open_by_packet[packet_id].payload.get("symbol")
        if str(record.get("symbol")) != str(ppl_symbol):
            raise SourceValidationError(
                f"DecisionPacket/PPL symbol mismatch for packet_id={packet_id!r}"
            )

        packet_to_trace[packet_id] = trace_id
        packet_records.append(record)
        packet_locations[packet_id] = {"path": str(path), "line": line_number}

    if len(set(packet_to_trace.values())) != len(packet_to_trace):
        raise SourceValidationError("DecisionPacket trace_id values are not one-to-one")

    packet_bytes = _canonical_jsonl(packet_records, key="packet_id")
    packet_digest = _sha256_bytes(packet_bytes)

    journal_snapshot = _read_prefix_snapshot(journal_path)
    journal_records = _jsonl_records(journal_snapshot.raw, source=journal_path)
    expected_traces = set(packet_to_trace.values())
    journal_matches: dict[str, tuple[Mapping[str, Any], int]] = {}

    for line_number, record in journal_records:
        decision_id = str(record.get("decision_id") or "")
        if decision_id not in expected_traces:
            continue
        if decision_id in journal_matches:
            prior = journal_matches[decision_id][1]
            raise SourceValidationError(
                f"DecisionIdentity {decision_id!r} duplicated at "
                f"{journal_path}:{prior} and {journal_path}:{line_number}"
            )
        journal_matches[decision_id] = (record, line_number)

    missing_traces = sorted(expected_traces - set(journal_matches))
    if missing_traces:
        raise SourceValidationError(
            f"missing DecisionIdentity trace IDs: {missing_traces}"
        )

    trace_to_packet = {trace: packet for packet, trace in packet_to_trace.items()}
    journal_output: list[Mapping[str, Any]] = []
    journal_locations: dict[str, int] = {}

    for trace_id in sorted(expected_traces):
        record, line_number = journal_matches[trace_id]
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise SourceValidationError(
                f"DecisionIdentity {trace_id!r} payload must be an object"
            )
        stored_digest = _require_sha256(
            record.get("payload_digest"),
            field_name=f"DecisionIdentity[{trace_id}].payload_digest",
        )
        if _decision_payload_digest(payload) != stored_digest:
            raise SourceValidationError(
                f"DecisionIdentity {trace_id!r} payload_digest mismatch"
            )

        packet_id = trace_to_packet[trace_id]
        packet_record = matched[packet_id][0]
        if str(record.get("symbol")) != str(packet_record.get("symbol")):
            raise SourceValidationError(
                f"packet/trace symbol mismatch for packet_id={packet_id!r}"
            )
        if str(record.get("cycle")) != str(packet_record.get("created_cycle_id")):
            raise SourceValidationError(
                f"packet/trace cycle mismatch for packet_id={packet_id!r}"
            )

        journal_output.append(record)
        journal_locations[trace_id] = line_number

    journal_bytes = _canonical_jsonl(journal_output, key="decision_id")
    journal_digest = _sha256_bytes(journal_bytes)

    metadata = {
        "decision_packets": {
            "status": "COMPLETE",
            "authority_class": "OPTIONAL_CERTIFIED",
            "record_count": len(packet_records),
            "canonical_subset_sha256": packet_digest,
            "selection_rule": "PPL_OPEN.decision_id == DecisionPacket.packet_id",
            "source_files": source_meta,
            "source_locations": packet_locations,
        },
        "decision_identity_records": {
            "status": "COMPLETE",
            "authority_class": "OPTIONAL_CERTIFIED",
            "record_count": len(journal_output),
            "canonical_subset_sha256": journal_digest,
            "selection_rule": (
                "PPL packet_id -> DecisionPacket.metadata.trace_id -> "
                "DecisionIdentityJournal.decision_id"
            ),
            "source_prefix": {
                "path": str(journal_path),
                "bytes": journal_snapshot.size,
                "sha256": journal_snapshot.sha256,
                "record_count": len(journal_records),
            },
            "source_locations": journal_locations,
        },
    }
    return packet_bytes, journal_bytes, metadata, packet_sources, journal_snapshot


def _source_boundary_document(
    *,
    paper_epoch_id: str,
    manifest_snapshot: _FileSnapshot,
    manifest: Any,
    config_snapshot: _FileSnapshot,
    config_doc: Mapping[str, Any],
    ppl_snapshot: _FileSnapshot,
    events: Sequence[LedgerEvent],
) -> dict[str, Any]:
    return {
        "identity_schema": _SOURCE_BOUNDARY_SCHEMA,
        "source_domain": _SOURCE_DOMAIN,
        "source_authority": _SOURCE_AUTHORITY,
        "paper_epoch_id": paper_epoch_id,
        "manifest_file_sha256": manifest_snapshot.sha256,
        "ppl_birth_code_sha": manifest.code_sha,
        "ppl_semantic_config_snapshot_hash": manifest.config_snapshot_hash,
        "experiment_config_file_sha256": config_snapshot.sha256,
        "experiment_config_snapshot_sha256": config_doc["snapshot_sha256"],
        "experiment_runtime_source_sha": config_doc["runtime_source_sha"],
        "ppl_stream_sha256": ppl_snapshot.sha256,
        "source_event_count": len(events),
        "source_first_sequence": events[0].sequence,
        "source_last_sequence": events[-1].sequence,
        "source_first_timestamp": events[0].timestamp,
        "source_last_timestamp": events[-1].timestamp,
        "legacy_boundary_sha256": manifest.legacy_boundary_sha256,
        "legacy_event_count": manifest.legacy_event_count,
    }


def _dataset_identity_document(
    *,
    source_boundary_id: str,
    exporter_code_sha: str,
    decision_meta: Mapping[str, Any] | None,
    declared_statuses: Mapping[str, SourceStatus],
) -> dict[str, Any]:
    components: list[dict[str, Any]] = [
        {
            "name": "authoritative_core",
            "status": "COMPLETE",
            "source_boundary_id": source_boundary_id,
        }
    ]
    if decision_meta is None:
        components.extend(
            [
                {
                    "name": "decision_packets",
                    "status": "NOT_INCLUDED",
                    "record_count": 0,
                    "canonical_subset_sha256": None,
                },
                {
                    "name": "decision_identity_records",
                    "status": "NOT_INCLUDED",
                    "record_count": 0,
                    "canonical_subset_sha256": None,
                },
            ]
        )
    else:
        for name in ("decision_packets", "decision_identity_records"):
            component = decision_meta[name]
            components.append(
                {
                    "name": name,
                    "status": component["status"],
                    "record_count": component["record_count"],
                    "canonical_subset_sha256": component["canonical_subset_sha256"],
                }
            )

    for name in sorted(declared_statuses):
        status_value = declared_statuses[name]
        components.append(
            {
                "name": name,
                "status": status_value.status,
                "reason": status_value.reason,
            }
        )

    return {
        "dataset_schema_version": _DATASET_SCHEMA_VERSION,
        "derivation": _DERIVATION,
        "source_boundary_id": source_boundary_id,
        "research_exporter_code_sha": exporter_code_sha,
        "components": components,
    }


def _write_new_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            written = handle.write(raw)
            if written != len(raw):
                raise OSError(f"short write for {path}")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                manifest,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PaperExportError(f"manifest serialization failed: {exc}") from exc


def export_paper_dataset(request: PaperExportRequest) -> ExportResult:
    """Create one immutable Research-owned dataset from explicit PAPER sources."""

    if not isinstance(request, PaperExportRequest):
        raise TypeError("request must be PaperExportRequest")
    if not request.paper_epoch_id:
        raise SourceValidationError("paper_epoch_id is required")
    exporter_sha = _require_sha40(
        request.exporter_code_sha, field_name="exporter_code_sha"
    )
    extracted_at = _validate_extracted_at(request.extracted_at_utc)
    statuses = _validate_declared_statuses(request.optional_source_statuses)

    has_packets = bool(request.decision_packet_paths)
    has_journal = request.decision_identity_journal_path is not None
    if has_packets != has_journal:
        raise SourceValidationError(
            "decision_packet_paths and decision_identity_journal_path "
            "must be supplied together"
        )
    if len(set(map(str, request.decision_packet_paths))) != len(
        request.decision_packet_paths
    ):
        raise SourceValidationError("decision_packet_paths contains duplicates")

    ppl_snapshot, events, projection = _load_ppl_readonly(
        Path(request.ppl_store_root), request.paper_epoch_id
    )
    manifest_snapshot, manifest_doc, authority_manifest = _load_manifest(
        Path(request.experiment_manifest_path),
        paper_epoch_id=request.paper_epoch_id,
        ppl_projection=projection,
    )
    config_snapshot, config_doc = _load_experiment_config(
        Path(request.experiment_config_path),
        paper_epoch_id=request.paper_epoch_id,
    )

    boundary_doc = _source_boundary_document(
        paper_epoch_id=request.paper_epoch_id,
        manifest_snapshot=manifest_snapshot,
        manifest=authority_manifest,
        config_snapshot=config_snapshot,
        config_doc=config_doc,
        ppl_snapshot=ppl_snapshot,
        events=events,
    )
    source_boundary_id = _sha256_bytes(_canonical_json_bytes(boundary_doc))

    decision_packet_bytes: bytes | None = None
    journal_bytes: bytes | None = None
    decision_meta: Mapping[str, Any] | None = None
    decision_sources: list[_FileSnapshot] = []
    journal_snapshot: _PrefixSnapshot | None = None

    if has_packets and request.decision_identity_journal_path is not None:
        (
            decision_packet_bytes,
            journal_bytes,
            decision_meta,
            decision_sources,
            journal_snapshot,
        ) = _extract_decision_evidence(
            events=events,
            packet_paths=tuple(Path(p) for p in request.decision_packet_paths),
            journal_path=Path(request.decision_identity_journal_path),
        )

    dataset_identity_doc = _dataset_identity_document(
        source_boundary_id=source_boundary_id,
        exporter_code_sha=exporter_sha,
        decision_meta=decision_meta,
        declared_statuses=statuses,
    )
    dataset_id = _sha256_bytes(_canonical_json_bytes(dataset_identity_doc))

    components: dict[str, Any] = {
        "ppl_events": {
            "authority_class": "AUTHORITATIVE_CORE",
            "status": "COMPLETE",
            "record_count": len(events),
            "sha256": ppl_snapshot.sha256,
        },
        "f00_experiment_manifest": {
            "authority_class": "AUTHORITATIVE_CORE",
            "status": "COMPLETE",
            "record_count": 1,
            "sha256": manifest_snapshot.sha256,
        },
        "f00_experiment_config": {
            "authority_class": "AUTHORITATIVE_CORE",
            "status": "COMPLETE",
            "record_count": 1,
            "sha256": config_snapshot.sha256,
            "snapshot_sha256": config_doc["snapshot_sha256"],
        },
    }

    if decision_meta is None:
        components["decision_packets"] = {
            "authority_class": "OPTIONAL_CERTIFIED",
            "status": "NOT_INCLUDED",
            "record_count": 0,
        }
        components["decision_identity_records"] = {
            "authority_class": "OPTIONAL_CERTIFIED",
            "status": "NOT_INCLUDED",
            "record_count": 0,
        }
    else:
        components.update(decision_meta)

    unresolved_reasons: list[dict[str, str]] = []
    for name in sorted(statuses):
        status_value = statuses[name]
        components[name] = {
            "authority_class": "EXPLICITLY_UNAVAILABLE_OR_UNBOUND",
            "status": status_value.status,
            "reason": status_value.reason,
            "evidence": list(status_value.evidence),
        }
        if status_value.status not in {"COMPLETE", "NOT_APPLICABLE"}:
            unresolved_reasons.append(
                {
                    "source": name,
                    "status": status_value.status,
                    "reason": status_value.reason,
                }
            )

    source_provenance: list[dict[str, Any]] = [
        {
            "role": "PAPER_LIFECYCLE_AUTHORITY",
            "path": str(ppl_snapshot.path),
            "sha256": ppl_snapshot.sha256,
            "bytes": ppl_snapshot.size,
            "record_count": len(events),
        },
        {
            "role": "EXPERIMENT_BIRTH_PROVENANCE",
            "path": str(manifest_snapshot.path),
            "sha256": manifest_snapshot.sha256,
            "bytes": manifest_snapshot.size,
            "record_count": 1,
        },
        {
            "role": "EXPERIMENT_CONFIGURATION_PROVENANCE",
            "path": str(config_snapshot.path),
            "sha256": config_snapshot.sha256,
            "bytes": config_snapshot.size,
            "record_count": 1,
        },
    ]
    if decision_meta is not None:
        for source in decision_meta["decision_packets"]["source_files"]:
            source_provenance.append(
                {"role": "OPTIONAL_DECISION_PACKET_SOURCE", **source}
            )
        source_provenance.append(
            {
                "role": "OPTIONAL_DECISION_IDENTITY_PREFIX",
                **decision_meta["decision_identity_records"]["source_prefix"],
            }
        )

    manifest = {
        "dataset_schema_version": _DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "source_boundary_id": source_boundary_id,
        "derivation": _DERIVATION,
        "source_domain": _SOURCE_DOMAIN,
        "source_authority": _SOURCE_AUTHORITY,
        "paper_epoch_id": request.paper_epoch_id,
        "completeness_status": "COMPLETE",
        "unresolved_reasons": unresolved_reasons,
        "source_boundary_identity": boundary_doc,
        "dataset_identity": dataset_identity_doc,
        "authoritative_manifest": manifest_doc,
        "components": components,
        "certification_references": dict(
            sorted(request.certification_references.items())
        ),
        "extraction_provenance": {
            "extracted_at_utc": extracted_at,
            "research_exporter_code_sha": exporter_sha,
            "sources": source_provenance,
        },
    }

    datasets_root = Path(request.output_root) / "datasets"
    target = datasets_root / dataset_id
    if target.exists():
        raise DatasetExistsError(f"immutable dataset already exists: {target}")

    datasets_root.mkdir(parents=True, exist_ok=True)
    tmp = Path(
        tempfile.mkdtemp(prefix=f".{dataset_id}.tmp-", dir=str(datasets_root))
    )
    try:
        _write_new_bytes(
            tmp / "authoritative" / "ppl_events.jsonl",
            ppl_snapshot.raw,
        )
        _write_new_bytes(