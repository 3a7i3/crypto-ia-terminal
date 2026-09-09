"""observability/operator_runtime_manifest.py — O-02W-C runtime manifest.

Per docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md §14.1: a
small, atomically-written, write-once-per-process-start file declaring
which process instance is the most recently started one. This is an
identity/succession declaration only — never a liveness heartbeat (§14.2)
— written before the first canonical operator domain snapshot of a new
process lifetime.

Purely passive (ADR-0007): a write failure is logged/counted and never
propagated into the advisor loop.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from observability.json_logger import get_logger

_log = get_logger("observability.operator_runtime_manifest")

DEFAULT_MANIFEST_PATH = Path(
    os.getenv(
        "OPERATOR_RUNTIME_MANIFEST_PATH",
        "databases/operator_runtime_manifest.json",
    )
)

SCHEMA_VERSION = 1

# Write-failure counter — the only observable evidence of a failed write,
# never raised into the advisor loop (fail-passive, ADR-0007).
write_errors = 0


def build_manifest(
    process_instance_id: str,
    boot_timestamp_utc: str,
    pid: Optional[int] = None,
    source_sha: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose the manifest payload — pure, no I/O, no side effects.

    Minimum fields per §14.1/§21.1: process_instance_id, boot_timestamp_utc,
    pid, source_sha. Declares identity/succession only — never claims the
    process is still running (§14.2).
    """

    return {
        "schema_version": SCHEMA_VERSION,
        "process_instance_id": process_instance_id,
        "boot_timestamp_utc": boot_timestamp_utc,
        "pid": pid if pid is not None else os.getpid(),
        "source_sha": source_sha,
    }


def write_manifest_atomic(payload: Dict[str, Any], path: Path = DEFAULT_MANIFEST_PATH) -> bool:
    """Write the manifest via tmp-file + os.replace() (§1.3 pattern).

    Returns True on success, False on failure. Never raises — a failure is
    logged and counted (`write_errors`), the caller must treat it as
    fail-passive and continue the advisor loop unaffected.
    """

    global write_errors
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return True
    except Exception as exc:  # pragma: no cover - defensive, exercised by tests via injected failures
        write_errors += 1
        _log.warning(
            "[OperatorRuntimeManifest] Écriture échouée (non bloquant): %s", exc
        )
        return False


def write_runtime_manifest(
    process_instance_id: str,
    source_sha: Optional[str] = None,
    pid: Optional[int] = None,
    path: Path = DEFAULT_MANIFEST_PATH,
    now_fn=time.time,
    boot_timestamp_utc: Optional[str] = None,
) -> bool:
    """Convenience: build + write the manifest in one call.

    Intended to be called exactly once per process lifetime, before the
    main advisor loop begins and before the first canonical operator
    domain snapshot is written (§14.1 step 1).

    Correction G (R2, MASTER review round 2): a manifest write can be
    RETRIED (§14.1 — the write may fail once and succeed on a later
    cycle) for the SAME `process_instance_id`. Without an explicit
    `boot_timestamp_utc`, every retry recomputed `_iso_utc(now_fn())`
    fresh, silently redefining the process's boot time to "now" on a
    delayed successful retry. Pass the ORIGINAL boot timestamp (captured
    once, at bootstrap, by the caller) here on every retry so it never
    drifts. Omit only for direct/standalone callers that intentionally
    want "now" (e.g. simple one-shot test helpers) — production code
    (`OperatorBootCoordinator`) always passes it explicitly.
    """

    boot_ts = boot_timestamp_utc if boot_timestamp_utc is not None else _iso_utc(now_fn())
    payload = build_manifest(
        process_instance_id=process_instance_id,
        boot_timestamp_utc=boot_ts,
        pid=pid,
        source_sha=source_sha,
    )
    return write_manifest_atomic(payload, path=path)


def read_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> Optional[Dict[str, Any]]:
    """Read the manifest back, if present. Returns None if missing/corrupt
    — never coerced to a default identity (§14.2 rule 2)."""

    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _iso_utc(ts: float) -> str:
    import datetime as _dt

    return (
        _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "SCHEMA_VERSION",
    "build_manifest",
    "write_manifest_atomic",
    "write_runtime_manifest",
    "read_manifest",
]
