"""observability/operator_api/app.py — read-only canonical operator API.

The canonical advisor snapshot routes NEVER instantiate `MexcSimulator`,
`WalletSync`, or `RealAccountsObserver`; NEVER import or start
`core.advisor_loop`; NEVER connect to an exchange or read API credentials;
NEVER recompute portfolio values, PnL, or decision authority; NEVER infer
process liveness; NEVER write or modify snapshot/manifest files; NEVER read a
JSONL ledger.

WEB-01-MARKET adds one deliberately separate cross-process presentation route:
``GET /api/operator/v1/market``. It reads only the atomic
``cryptoradar_market_snapshot.json`` artifact produced by the read-only
CryptoRadar publisher. The API still never reads DecisionPacket JSONL itself,
never imports the radar Telegram bot, and never upgrades MARKET telemetry into
execution authority.

Every route in this module is a GET. There is no mutating business route.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from observability.operator_api.financial_reconciliation_reader import (
    DEFAULT_FINANCIAL_RECONCILIATION_PATH,
    DEFAULT_FINANCIAL_RECONCILIATION_STALE_AFTER_S,
    FinancialReconciliationReadResult,
    FinancialReconciliationSnapshotReader,
)
from observability.operator_api.market_reader import (
    DEFAULT_MARKET_SNAPSHOT_PATH,
    DEFAULT_STALE_AFTER_S,
    MarketReadResult,
    MarketSnapshotReader,
)
from observability.operator_api.paths import DEFAULT_MANIFEST_PATH, DEFAULT_SNAPSHOT_PATH
from observability.operator_api.ppl_comparison_reader import (
    DEFAULT_PPL_COMPARISON_PATH,
    DEFAULT_STALE_AFTER_S as DEFAULT_PPL_COMPARISON_STALE_AFTER_S,
    PplComparisonReadResult,
    PplComparisonSnapshotReader,
)
from observability.operator_api.reader import SafeSnapshotReader, SnapshotReadResult
from observability.operator_api.research_lab_reader import (
    DEFAULT_RESEARCH_LAB_SNAPSHOT_PATH,
    ResearchLabReadResult,
    ResearchLabSnapshotReader,
)

app = FastAPI(
    title="Crypto AI Terminal — Operator API (read-only)",
    version="0.3.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# No CORS middleware is added at all — the default is "no cross-origin
# access," stricter than a permissive wildcard configuration. Controlled
# external exposure/auth remains a deployment/security responsibility.

_reader = SafeSnapshotReader()
_market_reader = MarketSnapshotReader()
_ppl_comparison_reader = PplComparisonSnapshotReader()
_financial_reconciliation_reader = FinancialReconciliationSnapshotReader()
_research_lab_reader = ResearchLabSnapshotReader()


def configure_reader(
    snapshot_path: Path = DEFAULT_SNAPSHOT_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    now_fn=None,
) -> SafeSnapshotReader:
    """Replace the canonical-snapshot reader (test/local wiring helper)."""

    global _reader
    _reader = SafeSnapshotReader(
        snapshot_path=snapshot_path, manifest_path=manifest_path, now_fn=now_fn
    )
    return _reader


def get_reader() -> SafeSnapshotReader:
    return _reader


def configure_market_reader(
    market_snapshot_path: Path = DEFAULT_MARKET_SNAPSHOT_PATH,
    *,
    stale_after_s: float = DEFAULT_STALE_AFTER_S,
    now_fn=None,
) -> MarketSnapshotReader:
    """Replace the MARKET artifact reader without touching canonical state.

    Production defaults resolve the governed artifact path once at process
    start. Tests point this reader only at ``tmp_path`` fixtures.
    """

    global _market_reader
    kwargs: Dict[str, Any] = {"stale_after_s": stale_after_s}
    if now_fn is not None:
        kwargs["now_fn"] = now_fn
    _market_reader = MarketSnapshotReader(path=market_snapshot_path, **kwargs)
    return _market_reader


def get_market_reader() -> MarketSnapshotReader:
    return _market_reader


def configure_ppl_comparison_reader(
    path: Path = DEFAULT_PPL_COMPARISON_PATH,
    *,
    stale_after_s: float = DEFAULT_PPL_COMPARISON_STALE_AFTER_S,
    now_fn=None,
) -> PplComparisonSnapshotReader:
    """Replace the WEB-02 artifact reader without touching trading state."""

    global _ppl_comparison_reader
    kwargs: Dict[str, Any] = {"stale_after_s": stale_after_s}
    if now_fn is not None:
        kwargs["now_fn"] = now_fn
    _ppl_comparison_reader = PplComparisonSnapshotReader(path=path, **kwargs)
    return _ppl_comparison_reader


def get_ppl_comparison_reader() -> PplComparisonSnapshotReader:
    return _ppl_comparison_reader


def configure_financial_reconciliation_reader(
    path: Path = DEFAULT_FINANCIAL_RECONCILIATION_PATH,
    *,
    stale_after_s: float = DEFAULT_FINANCIAL_RECONCILIATION_STALE_AFTER_S,
    now_fn=None,
) -> FinancialReconciliationSnapshotReader:
    """Replace the FIN-02 artifact reader without touching financial state."""

    global _financial_reconciliation_reader
    kwargs: Dict[str, Any] = {"stale_after_s": stale_after_s}
    if now_fn is not None:
        kwargs["now_fn"] = now_fn
    _financial_reconciliation_reader = FinancialReconciliationSnapshotReader(
        path=path,
        **kwargs,
    )
    return _financial_reconciliation_reader


def get_financial_reconciliation_reader() -> FinancialReconciliationSnapshotReader:
    return _financial_reconciliation_reader


def configure_research_lab_reader(
    path: Path = DEFAULT_RESEARCH_LAB_SNAPSHOT_PATH,
) -> ResearchLabSnapshotReader:
    """Replace the WEB-RL presentation reader without touching Research state."""

    global _research_lab_reader
    _research_lab_reader = ResearchLabSnapshotReader(path=path)
    return _research_lab_reader


def get_research_lab_reader() -> ResearchLabSnapshotReader:
    return _research_lab_reader


def _envelope(result: SnapshotReadResult) -> Dict[str, Any]:
    snap = result.snapshot or {}
    return {
        "snapshot_id": snap.get("snapshot_id"),
        "cycle": snap.get("cycle"),
        "process_instance_id": snap.get("process_instance_id"),
        "generated_at_utc": snap.get("generated_at_utc"),
        "instance_relation": result.instance_relation,
        "runtime_state": result.runtime_state,
        "stale_reason": result.stale_reason,
        "snapshot_age_s": result.snapshot_age_s,
        "freshness_classification": result.freshness_classification,
    }


def _failure_response(result: SnapshotReadResult) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error_code": result.error_code,
            "error_message": result.error_message,
            "retries_used": result.retries_used,
        },
    )


def _market_failure_response(result: MarketReadResult) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error_code": result.error_code,
            "error_message": result.error_message,
        },
    )


def _ppl_comparison_failure_response(
    result: PplComparisonReadResult,
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error_code": result.error_code,
            "error_message": result.error_message,
        },
    )


def _financial_reconciliation_failure_response(
    result: FinancialReconciliationReadResult,
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error_code": result.error_code,
            "error_message": result.error_message,
        },
    )


def _research_lab_failure_response(result: ResearchLabReadResult) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error_code": result.error_code,
            "error_message": result.error_message,
        },
    )


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    """API-transport-process readiness ONLY.

    This endpoint never claims the advisor, CryptoRadar, or MARKET publisher is
    alive. Component freshness is exposed only on its own read route.
    """

    return {
        "api_transport_process": "ready",
        "note": (
            "This reflects only the read-only API transport process's own "
            "readiness. It makes no claim about advisor/runtime or CryptoRadar "
            "publisher liveness."
        ),
    }


@app.get("/api/operator/v1/snapshot")
def get_snapshot() -> Any:
    """Return the validated canonical advisor snapshot verbatim plus
    reader-authored identity/freshness evidence."""

    result = get_reader().read()
    if not result.ok:
        return _failure_response(result)

    payload = dict(result.snapshot)
    payload["instance_relation"] = result.instance_relation
    payload["runtime_state"] = result.runtime_state
    payload["stale_reason"] = result.stale_reason
    payload["snapshot_age_s"] = result.snapshot_age_s
    payload["freshness_classification"] = result.freshness_classification
    return payload


def _domain_projection(domain_key: str) -> Any:
    result = get_reader().read()
    if not result.ok:
        return _failure_response(result)

    domain_payload = result.snapshot.get(domain_key)
    if domain_payload is None:
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


@app.get("/api/operator/v1/ppl-comparison")
def get_ppl_comparison() -> Any:
    """Return only the validated WEB-02 comparison artifact.

    The API does not import PPL projection code, MexcSimulator, or trading
    ledgers. It transports the producer-authored atomic artifact only.
    """

    result = get_ppl_comparison_reader().read()
    if not result.ok:
        return _ppl_comparison_failure_response(result)

    payload = dict(result.snapshot or {})
    payload["snapshot_age_s"] = result.snapshot_age_s
    payload["freshness_classification"] = result.freshness_classification
    return payload


@app.get("/api/operator/v1/financial-reconciliation")
def get_financial_reconciliation() -> Any:
    """Return only the validated FIN-02 presentation artifact.

    The API never imports FIN ledger/reconciliation computation, PPL stores,
    MexcSimulator or exchange clients.  It transports the producer-authored
    atomic artifact verbatim plus reader-authored freshness.
    """

    result = get_financial_reconciliation_reader().read()
    if not result.ok:
        return _financial_reconciliation_failure_response(result)

    payload = dict(result.snapshot or {})
    payload["snapshot_age_s"] = result.snapshot_age_s
    payload["freshness_classification"] = result.freshness_classification
    return payload


@app.get("/api/operator/v1/market")
def get_market() -> Any:
    """Return only the validated CryptoRadar presentation artifact.

    This is intentionally not projected from the advisor snapshot. MARKET is a
    separate observational process boundary under O-02W-B §12 / WEB-01-MARKET.
    """

    result = get_market_reader().read()
    if not result.ok:
        return _market_failure_response(result)

    payload = dict(result.snapshot or {})
    payload["snapshot_age_s"] = result.snapshot_age_s
    payload["freshness_classification"] = result.freshness_classification
    return payload


@app.get("/api/operator/v1/research-lab")
def get_research_lab() -> Any:
    """Return only the validated WEB-RL Research presentation artifact.

    This route never reads Research source datasets/JSONL, never instantiates
    replay/diagnostic/candidate engines, and never recomputes scientific metrics.
    """

    result = get_research_lab_reader().read()
    if not result.ok:
        return _research_lab_failure_response(result)

    return dict(result.snapshot or {})


__all__ = [
    "app",
    "configure_reader",
    "get_reader",
    "configure_market_reader",
    "get_market_reader",
    "configure_ppl_comparison_reader",
    "get_ppl_comparison_reader",
    "configure_financial_reconciliation_reader",
    "get_financial_reconciliation_reader",
    "configure_research_lab_reader",
    "get_research_lab_reader",
]
