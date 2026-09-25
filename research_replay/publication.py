"""Immutable result publication for RL-REPLAY-01.

Publication is Research-owned and source-independent: this module receives an
already-computed FactualReplayResult and writes only to a caller-supplied output
root. It never opens PAPER/PPL/RL-DATA source files.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .factual import FactualReplayResult, ReplayError, _canonical_json_bytes, _sha256_bytes


_RESULT_SCHEMA_VERSION = "rl-replay-01.result.v1"
_DERIVATION = "OFFLINE_FACTUAL_PPL_REPLAY"


class PublicationError(ReplayError):
    """Base error for immutable Research replay publication."""


class RunExistsError(PublicationError):
    """The immutable run target already exists."""


@dataclass(frozen=True)
class PublicationResult:
    research_run_id: str
    run_path: Path
    manifest: Mapping[str, Any]


def _json_file_bytes(value: Any) -> bytes:
    return _canonical_json_bytes(value) + b"\n"


def _lifecycle_jsonl_bytes(result: FactualReplayResult) -> bytes:
    return b"".join(
        _canonical_json_bytes(record.as_dict()) + b"\n"
        for record in result.lifecycle
    )


def _write_new_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise PublicationError(f"refusing to overwrite existing file: {path}") from exc


def _component_meta(raw: bytes, *, record_count: int) -> dict[str, Any]:
    return {
        "sha256": _sha256_bytes(raw),
        "bytes": len(raw),
        "record_count": record_count,
    }


def build_publication_payload(
    result: FactualReplayResult,
    *,
    generated_at_utc: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Build deterministic component bytes plus a provenance-bearing manifest.

    generated_at_utc is deliberately excluded from research_run_id and all
    scientific component identities. It is publication provenance only.
    """

    if not isinstance(generated_at_utc, str) or not generated_at_utc:
        raise PublicationError("generated_at_utc must be a non-empty string")

    lifecycle_raw = _lifecycle_jsonl_bytes(result)
    terminal_raw = _json_file_bytes(dict(result.terminal_state))
    metrics_raw = _json_file_bytes(dict(result.metrics))

    files = {
        "lifecycle.jsonl": lifecycle_raw,
        "terminal_state.json": terminal_raw,
        "metrics.json": metrics_raw,
    }
    components = {
        "lifecycle": _component_meta(
            lifecycle_raw,
            record_count=len(result.lifecycle),
        ),
        "terminal_state": _component_meta(terminal_raw, record_count=1),
        "metrics": _component_meta(metrics_raw, record_count=1),
    }

    identity = dict(result.research_run_identity)
    if _sha256_bytes(_canonical_json_bytes(identity)) != result.research_run_id:
        raise PublicationError(
            "research_run_id does not match research_run_identity"
        )

    manifest = {
        "result_schema_version": _RESULT_SCHEMA_VERSION,
        "research_run_id": result.research_run_id,
        "run_kind": identity["run_kind"],
        "status": "COMPLETE",
        "derivation": _DERIVATION,
        "dataset_id": result.dataset_id,
        "source_boundary_id": result.source_boundary_id,
        "paper_epoch_id": result.paper_epoch_id,
        "research_replay_code_sha": identity["research_replay_code_sha"],
        "replay_config_hash": result.replay_config_hash,
        "replay_method": identity["replay_method"],
        "population": identity["population"],
        "source_experiment_identity": identity["source_experiment_identity"],
        "candidate_config_hash": identity.get("candidate_config_hash"),
        "counterfactual_spec_digest": identity.get("counterfactual_spec_digest"),
        "research_run_identity": identity,
        "terminal_state": dict(result.terminal_state),
        "metrics": dict(result.metrics),
        "components": components,
        "limitations": {
            "mark_to_market_max_drawdown": (
                result.metrics["mark_to_market_max_drawdown"]
            ),
            "sharpe": result.metrics["sharpe"],
            "general_strategy_counterfactual": {
                "status": "NOT_AVAILABLE",
                "reason": (
                    "RL-DATA v1 has no certified complete market trajectory "
                    "or F00 DIP decision graph"
                ),
            },
        },
        "publication_provenance": {
            "generated_at_utc": generated_at_utc,
        },
    }
    files["manifest.json"] = _json_file_bytes(manifest)
    return manifest, files


def publish_factual_result(
    result: FactualReplayResult,
    *,
    output_root: str | Path,
    generated_at_utc: str,
) -> PublicationResult:
    """Atomically publish one immutable factual replay result.

    The target is output_root/runs/research_run_id. Existing targets are never
    overwritten, even for the same run identity.
    """

    root = Path(output_root).resolve()
    runs_root = root / "runs"
    target = runs_root / result.research_run_id

    if target.exists():
        raise RunExistsError(f"immutable Research run already exists: {target}")

    manifest, files = build_publication_payload(
        result,
        generated_at_utc=generated_at_utc,
    )

    runs_root.mkdir(parents=True, exist_ok=True)
    tmp = Path(
        tempfile.mkdtemp(
            prefix=f".{result.research_run_id}.tmp-",
            dir=str(runs_root),
        )
    )
    try:
        for relative_path, raw in files.items():
            _write_new_bytes(tmp / relative_path, raw)

        if target.exists():
            raise RunExistsError(
                f"immutable Research run already exists: {target}"
            )
        os.rename(tmp, target)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    return PublicationResult(
        research_run_id=result.research_run_id,
        run_path=target,
        manifest=manifest,
    )
