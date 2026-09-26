"""RL-BURNIN-01 RB4 — immutable final burn-in dataset designation.

The finalizer is Research-owned and offline. It validates an already immutable
RL-DATA burn-in dataset, replays the copied PPL stream, requires an explicit
quiescent authority boundary, and publishes a separate write-once designation.

It never discovers runtime paths, opens the authoritative PPL store, mutates a
dataset, or creates PAPER authority.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from paper_trading import durable_event_store as ppl_wire
from paper_trading.ledger_events import LedgerEvent
from paper_trading.paper_portfolio_ledger import project
from research_data import paper_exporter as exporter


_DESIGNATION_SCHEMA = "RL_BURNIN_01_FINAL_DESIGNATION_V1"
_DESIGNATION = "FINAL_BURN_IN_DATASET"
_BURN_IN_ROLE = "BURN_IN_EXPERIMENT"
_BURN_IN_MANIFEST_SCHEMA_VERSION = 3


class BurnInFinalizationError(RuntimeError):
    """Base fail-closed error for RB4 finalization."""


class BurnInDatasetValidationError(BurnInFinalizationError):
    """The immutable Research dataset is not a valid final burn-in source."""


class BurnInQuiescenceError(BurnInFinalizationError):
    """The explicit final authority boundary is not quiescent."""


class FinalDesignationExistsError(BurnInFinalizationError):
    """A deterministic final designation already exists and is never replaced."""


@dataclass(frozen=True)
class BurnInQuiescence:
    authority_process_stopped: bool
    pending_order_count: int
    lifecycle_transitions_in_flight: int

    @property
    def quiescent(self) -> bool:
        return (
            self.authority_process_stopped
            and self.pending_order_count == 0
            and self.lifecycle_transitions_in_flight == 0
        )


@dataclass(frozen=True)
class FinalDesignationResult:
    designation_id: str
    designation_path: Path
    document: Mapping[str, Any]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents


def _require_regular_file(path: Path) -> bytes:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise BurnInDatasetValidationError(f"required file missing: {path}") from exc
    if not path.is_file() or path.is_symlink():
        raise BurnInDatasetValidationError(
            f"required path must be a regular non-symlink file: {path}"
        )
    raw = path.read_bytes()
    if info.st_size != len(raw):
        raise BurnInDatasetValidationError(f"file size changed while reading: {path}")
    return raw


def _strict_json(raw: bytes, *, source: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=ppl_wire._object_without_duplicate_keys,
            parse_constant=ppl_wire._reject_json_constant,
        )
    except Exception as exc:
        raise BurnInDatasetValidationError(f"invalid JSON {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise BurnInDatasetValidationError(f"{source} must contain a JSON object")
    return value


def _load_dataset_ppl(
    path: Path, *, paper_epoch_id: str
) -> tuple[bytes, tuple[LedgerEvent, ...], Any]:
    raw = _require_regular_file(path)
    if not raw:
        raise BurnInDatasetValidationError("dataset PPL stream is empty")
    if not raw.endswith(b"\n"):
        raise BurnInDatasetValidationError("dataset PPL stream lacks final newline")

    events: list[LedgerEvent] = []
    expected_sequence = 1
    seen_ids: set[str] = set()
    for record_number, raw_line in enumerate(raw.splitlines(keepends=True), 1):
        if not raw_line.endswith(b"\n") or not raw_line[:-1].strip():
            raise BurnInDatasetValidationError(
                f"dataset PPL record {record_number} is incomplete or blank"
            )
        try:
            event = ppl_wire._decode_record(
                raw_line[:-1], source=path, record_number=record_number
            )
            canonical = ppl_wire._canonical_line(event)
        except Exception as exc:
            raise BurnInDatasetValidationError(
                f"dataset PPL record {record_number} is invalid: {exc}"
            ) from exc
        if canonical != raw_line:
            raise BurnInDatasetValidationError(
                f"dataset PPL record {record_number} is non-canonical"
            )
        if event.paper_epoch_id != paper_epoch_id:
            raise BurnInDatasetValidationError(
                f"dataset PPL record {record_number} epoch mismatch"
            )
        if event.sequence != expected_sequence:
            raise BurnInDatasetValidationError(
                f"dataset PPL sequence={event.sequence}, expected={expected_sequence}"
            )
        if event.event_id in seen_ids:
            raise BurnInDatasetValidationError(
                f"duplicate dataset PPL event_id={event.event_id!r}"
            )
        expected_sequence += 1
        seen_ids.add(event.event_id)
        events.append(event)

    try:
        projection = project(tuple(events))
    except Exception as exc:
        raise BurnInDatasetValidationError(
            f"dataset PPL lifecycle projection failed: {exc}"
        ) from exc
    if projection.paper_epoch_id != paper_epoch_id or projection.epoch is None:
        raise BurnInDatasetValidationError("dataset PPL projection epoch mismatch")
    return raw, tuple(events), projection


def _validate_dataset(
    dataset_path: Path,
) -> tuple[Mapping[str, Any], bytes, tuple[LedgerEvent, ...], Any]:
    dataset_path = dataset_path.resolve()
    manifest_path = dataset_path / "manifest.json"
    manifest_raw = _require_regular_file(manifest_path)
    dataset_manifest = _strict_json(manifest_raw, source=manifest_path)

    dataset_id = dataset_manifest.get("dataset_id")
    source_boundary_id = dataset_manifest.get("source_boundary_id")
    paper_epoch_id = dataset_manifest.get("paper_epoch_id")
    if not all(
        isinstance(value, str) and value
        for value in (dataset_id, source_boundary_id, paper_epoch_id)
    ):
        raise BurnInDatasetValidationError(
            "dataset_id/source_boundary_id/paper_epoch_id must be non-empty strings"
        )

    identity = dataset_manifest.get("dataset_identity")
    boundary = dataset_manifest.get("source_boundary_identity")
    if not isinstance(identity, dict) or not isinstance(boundary, dict):
        raise BurnInDatasetValidationError(
            "dataset identity/source boundary documents are missing"
        )
    if _sha256(_canonical_json_bytes(identity)) != dataset_id:
        raise BurnInDatasetValidationError("dataset_id does not match dataset_identity")
    if _sha256(_canonical_json_bytes(boundary)) != source_boundary_id:
        raise BurnInDatasetValidationError(
            "source_boundary_id does not match source_boundary_identity"
        )
    if identity.get("source_boundary_id") != source_boundary_id:
        raise BurnInDatasetValidationError(
            "dataset_identity/source_boundary_id binding mismatch"
        )
    if boundary.get("paper_epoch_id") != paper_epoch_id:
        raise BurnInDatasetValidationError(
            "source boundary paper_epoch_id mismatch"
        )

    authoritative = dataset_path / "authoritative"
    ppl_path = authoritative / "ppl_events.jsonl"
    ppl_raw, events, projection = _load_dataset_ppl(
        ppl_path, paper_epoch_id=paper_epoch_id
    )
    manifest_copy = authoritative / "burn_in_experiment_manifest.json"
    config_copy = authoritative / "burn_in_experiment_config.json"

    try:
        manifest_snapshot, manifest_doc, authority_manifest = exporter._load_manifest(
            manifest_copy,
            paper_epoch_id=paper_epoch_id,
            ppl_projection=projection,
        )
        config_snapshot, config_doc = exporter._load_experiment_config(
            config_copy,
            paper_epoch_id=paper_epoch_id,
            epoch_role=authority_manifest.epoch_role,
        )
    except Exception as exc:
        raise BurnInDatasetValidationError(
            f"burn-in authority provenance invalid: {exc}"
        ) from exc

    if (
        authority_manifest.epoch_role != _BURN_IN_ROLE
        or authority_manifest.manifest_schema_version
        != _BURN_IN_MANIFEST_SCHEMA_VERSION
    ):
        raise BurnInDatasetValidationError(
            "final designation requires BURN_IN_EXPERIMENT manifest schema v3"
        )
    if dataset_manifest.get("authoritative_manifest") != manifest_doc:
        raise BurnInDatasetValidationError(
            "dataset authoritative_manifest differs from copied manifest"
        )

    expected = {
        "manifest_file_sha256": manifest_snapshot.sha256,
        "experiment_config_file_sha256": config_snapshot.sha256,
        "experiment_config_snapshot_sha256": config_doc["snapshot_sha256"],
        "ppl_stream_sha256": _sha256(ppl_raw),
        "source_event_count": len(events),
        "source_first_sequence": events[0].sequence,
        "source_last_sequence": events[-1].sequence,
        "source_first_timestamp": events[0].timestamp,
        "source_last_timestamp": events[-1].timestamp,
    }
    mismatches = {
        key: {"expected": value, "actual": boundary.get(key)}
        for key, value in expected.items()
        if boundary.get(key) != value
    }
    if mismatches:
        raise BurnInDatasetValidationError(
            f"dataset source boundary fingerprint mismatch: {mismatches}"
        )

    components = dataset_manifest.get("components")
    if not isinstance(components, dict):
        raise BurnInDatasetValidationError("dataset components are missing")
    expected_components = {
        "ppl_events": _sha256(ppl_raw),
        "burn_in_experiment_manifest": manifest_snapshot.sha256,
        "burn_in_experiment_config": config_snapshot.sha256,
    }
    for name, digest in expected_components.items():
        component = components.get(name)
        if not isinstance(component, dict) or component.get("sha256") != digest:
            raise BurnInDatasetValidationError(
                f"dataset component fingerprint mismatch: {name}"
            )

    return dataset_manifest, ppl_raw, events, projection


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise FinalDesignationExistsError(
            f"final designation already exists and will not be replaced: {path}"
        ) from exc
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


def designate_final_burn_in_dataset(
    *,
    dataset_path: Path,
    designation_root: Path,
    quiescence: BurnInQuiescence,
    designated_at_utc: str,
    protected_roots: Sequence[Path] = (),
) -> FinalDesignationResult:
    """Validate and designate one immutable, quiescent burn-in Research dataset."""

    if not isinstance(quiescence, BurnInQuiescence):
        raise TypeError("quiescence must be BurnInQuiescence")
    if not isinstance(designated_at_utc, str) or not designated_at_utc.strip():
        raise BurnInFinalizationError("designated_at_utc is required")

    dataset_path = Path(dataset_path).resolve()
    designation_root = Path(designation_root).resolve()
    if _paths_overlap(dataset_path, designation_root):
        raise BurnInFinalizationError(
            "designation_root must not overlap the immutable dataset directory"
        )
    for protected in protected_roots:
        if _paths_overlap(designation_root, Path(protected)):
            raise BurnInFinalizationError(
                f"designation_root overlaps protected PAPER/runtime root: {protected}"
            )

    dataset_manifest, ppl_before, events, projection = _validate_dataset(dataset_path)
    if not quiescence.quiescent:
        raise BurnInQuiescenceError(
            "final designation requires stopped authority process, zero pending "
            "orders and zero lifecycle transitions in flight"
        )
    if projection.open_positions:
        raise BurnInQuiescenceError(
            "final designation requires zero open PPL positions"
        )

    boundary = dataset_manifest["source_boundary_identity"]
    identity = {
        "designation_schema": _DESIGNATION_SCHEMA,
        "designation": _DESIGNATION,
        "dataset_id": dataset_manifest["dataset_id"],
        "source_boundary_id": dataset_manifest["source_boundary_id"],
        "paper_epoch_id": dataset_manifest["paper_epoch_id"],
        "epoch_role": _BURN_IN_ROLE,
        "manifest_schema_version": _BURN_IN_MANIFEST_SCHEMA_VERSION,
        "ppl_stream_sha256": boundary["ppl_stream_sha256"],
        "source_event_count": boundary["source_event_count"],
        "source_last_sequence": boundary["source_last_sequence"],
        "ppl_birth_code_sha": boundary["ppl_birth_code_sha"],
        "ppl_semantic_config_snapshot_hash": (
            boundary["ppl_semantic_config_snapshot_hash"]
        ),
        "experiment_config_snapshot_sha256": (
            boundary["experiment_config_snapshot_sha256"]
        ),
        "closed_lifecycle_count": len(projection.closed_trade_ids),
        "unresolved_lifecycle_count": len(projection.unresolved_positions),
        "open_lifecycle_count": len(projection.open_positions),
        "quiescence": {
            "authority_process_stopped": quiescence.authority_process_stopped,
            "pending_order_count": quiescence.pending_order_count,
            "lifecycle_transitions_in_flight": (
                quiescence.lifecycle_transitions_in_flight
            ),
        },
    }
    designation_id = _sha256(_canonical_json_bytes(identity))
    document = {
        **identity,
        "designation_id": designation_id,
        "designated_at_utc": designated_at_utc,
    }
    target = designation_root / "finalizations" / f"{designation_id}.json"
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"
    _write_exclusive(target, encoded)

    try:
        ppl_after = _require_regular_file(
            dataset_path / "authoritative" / "ppl_events.jsonl"
        )
        _validate_dataset(dataset_path)
    except Exception:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    if ppl_after != ppl_before:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise BurnInDatasetValidationError(
            "immutable dataset changed during final designation"
        )

    return FinalDesignationResult(
        designation_id=designation_id,
        designation_path=target,
        document=document,
    )
