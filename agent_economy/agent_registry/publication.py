"""Write-once AgentSpec publication (A1 section 11, AW-01 ... AW-06).

SOURCE-ONLY primitive. It is NOT the operational durable registry storage:
Q10 (where specs and events live) is UNRESOLVED and no location is chosen here;
the caller must pass an explicit root. Publication never creates registry state
(AW-06): state is born only from an event.

Semantics mirror ``research_candidate.registry.publish_candidate``:
identical existing artifact -> idempotent success; same ``agent_spec_id`` with
different bytes -> fail closed; never overwrite, never truncate-and-rewrite.
The artifact becomes visible atomically: bytes are written and fsynced to an
exclusive temporary file, then hard-linked to the final name (``link`` fails if
the name exists), so a crash never leaves a partially written artifact.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import AgentRegistryError, compile_schema_pattern
from .spec import (
    PATTERN_SHA256,
    PROVENANCE_FIELDS,
    compute_spec_artifact_bytes,
    compute_spec_artifact_hash,
    validate_agent_spec,
)

CREATED = "CREATED"
ALREADY_EXISTS_IDENTICAL = "ALREADY_EXISTS_IDENTICAL"

_ARTIFACT_SUFFIX = ".json"
_SHA256 = compile_schema_pattern(PATTERN_SHA256)


@dataclass(frozen=True)
class PublicationResult:
    agent_id: str
    agent_spec_id: str
    spec_artifact_hash: str
    path: Path
    disposition: str


def spec_artifact_path(root: str | Path, agent_id: str, agent_spec_id: str) -> Path:
    """AW-01: artifact key is agent_spec_id, under agent_id, under an explicit root."""
    for name, value in (("agent_id", agent_id), ("agent_spec_id", agent_spec_id)):
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise AgentRegistryError(
                "SPEC_SCHEMA_VIOLATION", f"{name} must be lowercase sha256"
            )
    return Path(root) / agent_id / f"{agent_spec_id}{_ARTIFACT_SUFFIX}"


def _reject_float(text: str) -> Any:
    raise AgentRegistryError("SPEC_NUMERIC_AMBIGUITY", f"float {text} in artifact")


def _reject_constant(text: str) -> Any:
    raise AgentRegistryError("SPEC_NUMERIC_AMBIGUITY", f"constant {text} in artifact")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise AgentRegistryError("SPEC_SCHEMA_VIOLATION", "duplicate key in artifact")
    return dict(pairs)


def parse_spec_artifact(raw: bytes) -> dict[str, Any]:
    """Strictly parse published artifact bytes (no float, no duplicate key)."""
    if not isinstance(raw, (bytes, bytearray)):
        raise AgentRegistryError("SPEC_SCHEMA_VIOLATION", "artifact must be bytes")
    try:
        parsed = json.loads(
            bytes(raw).decode("utf-8"),
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except AgentRegistryError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise AgentRegistryError(
            "SPEC_SCHEMA_VIOLATION", f"artifact is not valid JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise AgentRegistryError("SPEC_SCHEMA_VIOLATION", "artifact must be an object")
    return parsed


def _material(document: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in document.items() if k not in PROVENANCE_FIELDS}


def classify_artifact_difference(existing: bytes, candidate: bytes) -> str | None:
    """Compare two artifacts claimed to share one ``agent_spec_id`` (AW-03).

    None when byte-identical; ``AGENT_SPEC_PROVENANCE_CONFLICT`` when only the
    provenance fields differ (same matter, different provenance);
    ``AGENT_SPEC_ID_COLLISION_OR_CORRUPTION`` for any other difference,
    including bytes that cannot be parsed.
    """
    if existing == candidate:
        return None
    try:
        left, right = parse_spec_artifact(existing), parse_spec_artifact(candidate)
    except AgentRegistryError:
        return "AGENT_SPEC_ID_COLLISION_OR_CORRUPTION"
    if _material(left) == _material(right):
        return "AGENT_SPEC_PROVENANCE_CONFLICT"
    return "AGENT_SPEC_ID_COLLISION_OR_CORRUPTION"


def _read_existing(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb", closefd=True) as handle:
            return handle.read()
    except OSError as exc:
        raise AgentRegistryError(
            "PUBLICATION_IO_ERROR", f"cannot read existing artifact: {exc}"
        ) from exc


def _conflict(existing: bytes, payload: bytes) -> AgentRegistryError:
    code = classify_artifact_difference(existing, payload)
    return AgentRegistryError(
        code or "AGENT_SPEC_ID_COLLISION_OR_CORRUPTION",
        "an artifact with this agent_spec_id already exists with different bytes",
    )


def _publish_exclusive(path: Path, payload: bytes) -> bool:
    """Create ``path`` atomically with ``payload``; False if it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path)  # atomic and exclusive: fails if the name exists
        except FileExistsError:
            return False
        finally:
            temp.unlink(missing_ok=True)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return True
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise AgentRegistryError(
            "PUBLICATION_IO_ERROR", f"cannot publish artifact: {exc}"
        ) from exc


def publish_agent_spec(root: str | Path, spec: dict[str, Any]) -> PublicationResult:
    """Validate then publish one AgentSpec artifact write-once.

    Raises AgentRegistryError: any AS-* code for an invalid spec;
    AGENT_SPEC_PROVENANCE_CONFLICT / AGENT_SPEC_ID_COLLISION_OR_CORRUPTION when an
    artifact with this ``agent_spec_id`` already exists with different bytes.
    """
    identities = validate_agent_spec(spec)
    payload = compute_spec_artifact_bytes(spec)
    path = spec_artifact_path(root, identities.agent_id, identities.agent_spec_id)

    if path.exists() or path.is_symlink():
        existing = _read_existing(path)
        if existing == payload:
            disposition = ALREADY_EXISTS_IDENTICAL
        else:
            raise _conflict(existing, payload)
    elif _publish_exclusive(path, payload):
        disposition = CREATED
    else:  # lost a race on the exact name: compare with the winner
        existing = _read_existing(path)
        if existing != payload:
            raise _conflict(existing, payload)
        disposition = ALREADY_EXISTS_IDENTICAL
    return PublicationResult(
        agent_id=identities.agent_id,
        agent_spec_id=identities.agent_spec_id,
        spec_artifact_hash=compute_spec_artifact_hash(spec),
        path=path,
        disposition=disposition,
    )


def read_spec_artifact(
    root: str | Path, agent_id: str, agent_spec_id: str
) -> bytes | None:
    """Exact published bytes, or None when the artifact was never published."""
    path = spec_artifact_path(root, agent_id, agent_spec_id)
    if not path.exists() and not path.is_symlink():
        return None
    return _read_existing(path)
