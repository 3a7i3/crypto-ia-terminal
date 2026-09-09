"""observability/operator_api/app.py — O-02W-D1: minimum read-only
canonical operator API.

A separate FastAPI process. It NEVER instantiates `MexcSimulator`,
`WalletSync`, or `RealAccountsObserver`; NEVER imports or starts
`core.advisor_loop`; NEVER connects to an exchange or reads API
credentials; NEVER recomputes portfolio values, PnL, or decision
authority; NEVER infers process liveness; NEVER writes or modifies the
snapshot/manifest files; NEVER reads a JSONL ledger (deferred, §6 of the
mission — trades/decision-history/regret are out of D1 scope pending the
governed generation-sidecar/lifecycle mechanism).

Every route in this module is a GET. There is no mutating business
route — see `tests/test_operator_api.py` for a route-table assertion of
that fact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from observability.operator_api.reader import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SNAPSHOT_PATH,
    SafeSnapshotReader,
    SnapshotReadResult,
)

app = FastAPI(
    title="Crypto AI Terminal — Operator API (read-only)",
    version="0.1.0",
    # Reduce exposed surface (mission §7) — interactive docs are not
    # required for this minimum read-only transport.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# No CORS middleware is added at all — the default is "no cross-origin
# access," which is stricter than any permissive wildcard configuration
# (mission §7: "no permissive wildcard CORS"). Controlled external
# exposure/auth is explicitly deferred to a later security/deployment
# mission.

# Overridable at import time by tests via `configure_reader()` — the
# reader itself only ever takes configurable paths, never the real
# `databases/` directory in a test process (mission §5/§8/§17).
_reader = SafeSnapshotReader()


def configure_reader(
    snapshot_path: Path = DEFAULT_SNAPSHOT_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    now_fn=None,
) -> SafeSnapshotReader:
    """Replace the module-level reader instance. Test-only convenience —
    production entry points construct one `SafeSnapshotReader` at
    process start and never repoint it at a different pair of files."""

    global _reader
    _reader = SafeSnapshotReader(
        snapshot_path=snapshot_path, manifest_path=manifest_path, now_fn=now_fn
    )
    return _reader


def get_reader() -> SafeSnapshotReader:
    return _reader


def _envelope(result: SnapshotReadResult) -> Dict[str, Any]:
    snap = result.snapshot or {}
    return {
        "snapshot_id": snap.get("snapshot_id"),
        "cycle": snap.get("cycle"),
        "process_instance_id": snap.get("process_instance_id"),
        "generated_at_utc": snap.get("generated_at_utc"),
        "instance_relation": result.instance_relation,
        "runtime_state": result.runtime_state,
        "snapshot_age_s": result.snapshot_age_s,
        "freshness_classification": result.freshness_classification,
    }


def _failure_response(result: SnapshotReadResult) -> JSONResponse:
    # Structured non-success — never HTTP 200 with fabricated empty
    # domains (mission §5).
    return JSONResponse(
        status_code=503,
        content={
            "error_code": result.error_code,
            "error_message": result.error_message,
            "retries_used": result.retries_used,
        },
    )


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    """API-transport-process readiness ONLY.

    This endpoint never claims the advisor is alive, that the manifest or
    a snapshot proves liveness, or that a PID/S-03 proves liveness — it
    reports only that this FastAPI process itself is up and able to
    answer requests (mission §4).
    """

    return {
        "api_transport_process": "ready",
        "note": (
            "This reflects only the read-only API transport process's own "
            "readiness. It makes no claim about advisor/runtime liveness — "
            "see /api/operator/v1/system-health's boot_alive field, which "
            "is honestly UNKNOWN today (no independent liveness publisher "
            "exists yet)."
        ),
    }


@app.get("/api/operator/v1/snapshot")
def get_snapshot() -> Any:
    """Return the validated canonical snapshot verbatim (no recomputation
    of any domain value) plus the reader's identity/freshness evidence."""

    result = get_reader().read()
    if not result.ok:
        return _failure_response(result)

    payload = dict(result.snapshot)  # shallow copy of the already-deep-copied doc
    payload["instance_relation"] = result.instance_relation
    payload["runtime_state"] = result.runtime_state
    payload["snapshot_age_s"] = result.snapshot_age_s
    payload["freshness_classification"] = result.freshness_classification
    return payload


def _domain_projection(domain_key: str) -> Any:
    result = get_reader().read()
    if not result.ok:
        return _failure_response(result)

    domain_payload = result.snapshot.get(domain_key)
    if domain_payload is None:
        # The envelope validated (required fields present, §5 rule 6
        # covers this key already), so a missing domain here would be an
        # internal inconsistency in the producer's own output — never
        # silently substituted with an empty dict.
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "SNAPSHOT_DOMAIN_MISSING",
                "error_message": f"Snapshot envelope carries no '{domain_key}' domain.",
            },
        )

    return {**_envelope(result), domain_key: domain_payload}


@app.get("/api/operator/v1/portfolio")
def get_portfolio() -> Any:
    return _domain_projection("portfolio")


@app.get("/api/operator/v1/decision-pipeline")
def get_decision_pipeline() -> Any:
    return _domain_projection("decision_pipeline")


@app.get("/api/operator/v1/system-health")
def get_system_health() -> Any:
    return _domain_projection("system_health")


__all__ = ["app", "configure_reader", "get_reader"]
