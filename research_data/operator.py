"""RL-DATA-01 operator boundary for offline Research exports.

The core exporter accepts an explicit exporter SHA so it remains a pure library.
This operator layer is the governed source-side entry point: it derives the exact
Git HEAD from a clean repository and refuses dirty/untracked worktrees.

No production runtime discovery occurs here.  Every scientific source path is
provided explicitly by the caller.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .paper_exporter import (
    ExportResult,
    PaperExportError,
    PaperExportRequest,
    SourceStatus,
    export_paper_dataset,
)

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_STATUS_KEYS = frozenset(
    {"dip", "regret", "rejection_store", "admission_ledger"}
)


class OperatorError(PaperExportError):
    """Fail-closed error at the offline operator boundary."""


@dataclass(frozen=True)
class OperatorExportRequest:
    repo_root: Path
    paper_epoch_id: str
    ppl_store_root: Path
    experiment_manifest_path: Path
    experiment_config_path: Path
    output_root: Path
    extracted_at_utc: str
    source_statuses_path: Path
    decision_packet_paths: tuple[Path, ...] = ()
    decision_identity_journal_path: Path | None = None
    certification_references: Mapping[str, str] | None = None


def _run_git(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or exc.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise OperatorError(f"git {' '.join(args)} failed{suffix}") from exc
    return completed.stdout.strip()


def resolve_clean_repo_head(repo_root: Path) -> str:
    """Return exact Git HEAD only when repo_root is the clean repository root."""

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise OperatorError(f"repo_root is not a directory: {root}")

    top = Path(_run_git(root, "rev-parse", "--show-toplevel")).resolve()
    if top != root:
        raise OperatorError(
            f"repo_root must be the Git top-level directory: expected {top}, got {root}"
        )

    head = _run_git(root, "rev-parse", "HEAD")
    if not _SHA40_RE.fullmatch(head):
        raise OperatorError(f"unexpected Git HEAD: {head!r}")

    dirty = _run_git(
        root,
        "status",
        "--porcelain",
        "--untracked-files=all",
    )
    if dirty:
        raise OperatorError(
            "repository worktree is not clean; refusing to certify exporter code SHA"
        )
    return head


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _object_without_duplicate_keys(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def load_source_statuses(path: Path) -> dict[str, SourceStatus]:
    """Load the four explicit v1 unavailable/unbound source declarations."""

    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise OperatorError(f"cannot read source statuses file {source}: {exc}") from exc
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise OperatorError(f"invalid source statuses JSON {source}: {exc}") from exc

    if not isinstance(value, dict):
        raise OperatorError("source statuses document must be a JSON object")

    actual = frozenset(value)
    if actual != _REQUIRED_STATUS_KEYS:
        missing = sorted(_REQUIRED_STATUS_KEYS - actual)
        extra = sorted(actual - _REQUIRED_STATUS_KEYS)
        raise OperatorError(
            f"source statuses keys mismatch: missing={missing}, extra={extra}"
        )

    statuses: dict[str, SourceStatus] = {}
    for name in sorted(value):
        record = value[name]
        if not isinstance(record, dict):
            raise OperatorError(f"source status {name!r} must be a JSON object")
        if set(record) - {"status", "reason", "evidence"}:
            raise OperatorError(
                f"source status {name!r} has unsupported fields: "
                f"{sorted(set(record) - {'status', 'reason', 'evidence'})}"
            )
        evidence = record.get("evidence", [])
        if not isinstance(evidence, list) or not all(
            isinstance(item, str) and item for item in evidence
        ):
            raise OperatorError(
                f"source status {name!r} evidence must be an array of strings"
            )
        try:
            statuses[name] = SourceStatus(
                status=record.get("status"),
                reason=record.get("reason"),
                evidence=tuple(evidence),
            )
        except (TypeError, ValueError) as exc:
            raise OperatorError(f"invalid source status {name!r}: {exc}") from exc
    return statuses


def export_from_clean_repo(request: OperatorExportRequest) -> ExportResult:
    """Resolve clean Git identity, then invoke the pure offline exporter."""

    if not isinstance(request, OperatorExportRequest):
        raise TypeError("request must be OperatorExportRequest")

    exporter_sha = resolve_clean_repo_head(request.repo_root)
    statuses = load_source_statuses(request.source_statuses_path)

    return export_paper_dataset(
        PaperExportRequest(
            paper_epoch_id=request.paper_epoch_id,
            ppl_store_root=request.ppl_store_root,
            experiment_manifest_path=request.experiment_manifest_path,
            experiment_config_path=request.experiment_config_path,
            output_root=request.output_root,
            exporter_code_sha=exporter_sha,
            extracted_at_utc=request.extracted_at_utc,
            optional_source_statuses=statuses,
            decision_packet_paths=request.decision_packet_paths,
            decision_identity_journal_path=request.decision_identity_journal_path,
            certification_references=request.certification_references or {},
        )
    )
