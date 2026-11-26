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

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from observability.operator_api.event_center_reader import EventCenterReader
from observability.operator_api.storage_reader import StorageSnapshotReader, read_storage_inventory
from observability.operator_api.venue_comparison_reader import VenueComparisonReader
from observability.operator_api.market_flow_reader import MarketFlowReader
from observability.operator_api.bbo_history_reader import BboHistoryReader
from observability.operator_api.scanner_universe_reader import ScannerUniverseReader
from observability.operator_api.radar_projection_reader import RadarProjectionReader
from observability.operator_api import agent_schedule
from observability.operator_api.agent_invocation_reader import TARGETS as AGENT_INVOCATION_TARGETS, read_agent_invocation, read_agent_history

from observability.operator_api.market_microstructure_reader import (
    DEFAULT_PATH as DEFAULT_MICROSTRUCTURE_PATH,
    MarketMicrostructureReader,
)

from observability.operator_api.runtime_service_reader import (
    DEFAULT_RUNTIME_SERVICE_PATH,
    DEFAULT_STALE_AFTER_S as DEFAULT_RUNTIME_SERVICE_STALE_AFTER_S,
    RuntimeServiceSnapshotReader,
)

from observability.operator_api.burn_in_status_reader import (
    DEFAULT_BURN_IN_STATUS_PATH,
    DEFAULT_STALE_AFTER_S as DEFAULT_BURN_IN_STATUS_STALE_AFTER_S,
    BurnInStatusReadResult,
    BurnInStatusSnapshotReader,
)
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
from observability.operator_api.research_strategy_board_reader import ResearchStrategyBoardReader
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


@app.get("/api/operator/v1/ppl-accounting-history")
def get_ppl_accounting_history() -> Any:
    from observability.operator_api.ppl_accounting_history_reader import read_history
    payload, error = read_history()
    if error:
        return JSONResponse(status_code=503, content={"error_code": error}, headers={"Cache-Control": "no-store"})
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})

# No CORS middleware is added at all — the default is "no cross-origin
# access," stricter than a permissive wildcard configuration. Controlled
# external exposure/auth remains a deployment/security responsibility.

_reader = SafeSnapshotReader()
_event_center_reader = EventCenterReader()
_storage_reader = StorageSnapshotReader()
_microstructure_reader = MarketMicrostructureReader()
_runtime_service_reader = RuntimeServiceSnapshotReader()
_burn_in_status_reader = BurnInStatusSnapshotReader()
_market_reader = MarketSnapshotReader()
_ppl_comparison_reader = PplComparisonSnapshotReader()
_financial_reconciliation_reader = FinancialReconciliationSnapshotReader()
_research_lab_reader = ResearchLabSnapshotReader()
_research_strategy_board_reader = ResearchStrategyBoardReader()


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


def get_event_center_reader() -> EventCenterReader:
    return _event_center_reader


def get_storage_reader() -> StorageSnapshotReader:
    return _storage_reader


def configure_storage_reader(path, *, now_fn=None) -> StorageSnapshotReader:
    global _storage_reader
    _storage_reader = StorageSnapshotReader(path, **({} if now_fn is None else {"now_fn": now_fn}))
    return _storage_reader


@app.get("/api/operator/v1/storage")
def get_storage() -> Any:
    result = get_storage_reader().read()
    if not result.ok:
        return JSONResponse(status_code=503, content={"error_code": result.error_code})
    return result.snapshot


@app.get("/api/operator/v1/storage-inventory")
def get_storage_inventory() -> Any:
    snapshot = read_storage_inventory()
    if snapshot is None:
        return JSONResponse(status_code=503, content={"error_code": "STORAGE_INVENTORY_UNAVAILABLE"}, headers={"Cache-Control": "no-store"})
    return JSONResponse(content=snapshot, headers={"Cache-Control": "no-store"})



@app.get("/api/operator/v1/lab-experiments")
def get_lab_experiments() -> Any:
    """Serve the bounded presentation registry, not raw experiment results."""
    from pathlib import Path
    import re
    from observability.runtime_service_artifact import read_document
    from observability.event_center_contract import utc_seconds

    headers = {"Cache-Control": "no-store"}
    try:
        doc, _ = read_document(Path("/var/lib/cat-lab-registry/index.json"))
        rows = doc["experiments"]
        if set(doc) != {"experiments"} or not isinstance(rows, list) or len(rows) > 25:
            raise ValueError("invalid registry")
        ids = set()
        for row in rows:
            summary = row["summary"]
            key = row["experiment_id"]
            if (
                set(row) != {"experiment_id", "execution_host", "published_at", "result_sha256",
                             "summary", "schema_version", "status", "kind", "data_kind"}
                or not re.fullmatch(r"publication-smoke-[0-9]{8}T[0-9]{12}Z", key)
                or key in ids
                or row["execution_host"] != "cat-c1-16m-qual-01"
                or utc_seconds(row["published_at"]) is None
                or not re.fullmatch(r"[0-9a-f]{64}", row["result_sha256"])
                or type(row["schema_version"]) is not int or row["schema_version"] != 1
                or row["status"] != "completed" or row["kind"] != "publication_smoke"
                or row["data_kind"] != "synthetic"
                or set(summary) != {"observations", "net_change"}
                or type(summary["observations"]) is not int or not 1 <= summary["observations"] <= 10000
                or type(summary["net_change"]) is not int or abs(summary["net_change"]) >= 2**53
            ):
                raise ValueError("invalid card")
            ids.add(key)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return JSONResponse(status_code=503, content={"error_code": "LAB_REGISTRY_UNAVAILABLE"}, headers=headers)
    return JSONResponse(content=doc, headers=headers)


def configure_event_center_reader(path, *, now_fn=None) -> EventCenterReader:
    global _event_center_reader
    kwargs = {} if now_fn is None else {"now_fn": now_fn}
    _event_center_reader = EventCenterReader(path, **kwargs)
    return _event_center_reader


@app.get("/api/operator/v1/events")
def get_events() -> Any:
    """Transport one passive presentation artifact; no alert engine or journal."""
    result = get_event_center_reader().read()
    if not result.ok:
        return JSONResponse(status_code=503, content={"error_code": result.error_code})
    return result.snapshot


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


def get_microstructure_reader() -> MarketMicrostructureReader:
    return _microstructure_reader


def configure_microstructure_reader(
    path: Path = DEFAULT_MICROSTRUCTURE_PATH, *, now_fn=None
) -> MarketMicrostructureReader:
    global _microstructure_reader
    kwargs = {} if now_fn is None else {"now_fn": now_fn}
    _microstructure_reader = MarketMicrostructureReader(path, **kwargs)
    return _microstructure_reader


def get_runtime_service_reader() -> RuntimeServiceSnapshotReader:
    return _runtime_service_reader


def configure_runtime_service_reader(
    path: Path = DEFAULT_RUNTIME_SERVICE_PATH,
    *,
    stale_after_s: float = DEFAULT_RUNTIME_SERVICE_STALE_AFTER_S,
    now_fn=None,
) -> RuntimeServiceSnapshotReader:
    global _runtime_service_reader
    kwargs: dict[str, Any] = {"stale_after_s": stale_after_s}
    if now_fn is not None:
        kwargs["now_fn"] = now_fn
    _runtime_service_reader = RuntimeServiceSnapshotReader(path, **kwargs)
    return _runtime_service_reader


def get_burn_in_status_reader() -> BurnInStatusSnapshotReader:
    return _burn_in_status_reader


def configure_burn_in_status_reader(
    path: Path = DEFAULT_BURN_IN_STATUS_PATH,
    *,
    stale_after_s: float = DEFAULT_BURN_IN_STATUS_STALE_AFTER_S,
    now_fn=None,
) -> BurnInStatusSnapshotReader:
    """Replace the U2 presentation reader without touching PPL."""

    global _burn_in_status_reader
    kwargs: Dict[str, Any] = {"stale_after_s": stale_after_s}
    if now_fn is not None:
        kwargs["now_fn"] = now_fn
    _burn_in_status_reader = BurnInStatusSnapshotReader(path=path, **kwargs)
    return _burn_in_status_reader


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


def _burn_in_status_failure_response(result: BurnInStatusReadResult) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error_code": result.error_code,
            "error_message": result.error_message,
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


@app.get("/api/operator/v1/market-microstructure")
def get_market_microstructure() -> Any:
    """Only the passive presentation artifact, never the LMI sidecar itself."""
    result = get_microstructure_reader().read()
    if not result.ok:
        return JSONResponse(status_code=503, content={"error_code": result.error_code})
    return result.snapshot


@app.get("/api/operator/v1/agent-invocations/{agent_id}")
def get_agent_invocation(agent_id: str) -> Any:
    """Lecture seule de la dernière preuve d'invocation d'un agent autorisé."""
    if agent_id not in AGENT_INVOCATION_TARGETS:
        return JSONResponse(status_code=404, content={"error_code": "AGENT_NOT_ALLOWED"},
                            headers={"Cache-Control": "no-store"})
    return JSONResponse(content=read_agent_invocation(agent_id), headers={"Cache-Control": "no-store"})


@app.get("/api/operator/v1/agent-invocations/{agent_id}/history")
def get_agent_invocation_history(agent_id: str) -> Any:
    """Lecture seule de l'historique des rapports d'un agent autorisé (20 plus récents)."""
    if agent_id not in AGENT_INVOCATION_TARGETS:
        return JSONResponse(status_code=404, content={"error_code": "AGENT_NOT_ALLOWED"},
                            headers={"Cache-Control": "no-store"})
    return JSONResponse(content=read_agent_history(agent_id), headers={"Cache-Control": "no-store"})


@app.get("/api/operator/v1/agent-invocations/{agent_id}/schedule")
def get_agent_schedule(agent_id: str) -> Any:
    """Rythme demandé et rythme appliqué (publié par l'applicateur root)."""
    if agent_id not in agent_schedule.SCHEDULABLE:
        return JSONResponse(status_code=404, content={"error_code": "AGENT_NOT_ALLOWED"},
                            headers={"Cache-Control": "no-store"})
    return JSONResponse(content=agent_schedule.read_schedule(agent_id), headers={"Cache-Control": "no-store"})


@app.post("/api/operator/v1/agent-invocations/{agent_id}/schedule")
async def post_agent_schedule(agent_id: str, request: Request) -> Any:
    """SEULE écriture de l'API (exception gouvernée) : dépose une demande de rythme. Ne lance rien."""
    h = {"Cache-Control": "no-store"}
    if agent_id not in agent_schedule.WRITABLE:
        return JSONResponse(status_code=404, content={"error_code": "AGENT_NOT_ALLOWED"}, headers=h)
    if request.headers.get("x-cat-operator") != "schedule":
        return JSONResponse(status_code=403, content={"error_code": "MISSING_OPERATOR_HEADER"}, headers=h)
    try:
        body = await request.json()
        rhythm = body.get("rhythm") if isinstance(body, dict) else None
    except ValueError:
        rhythm = None
    if rhythm not in agent_schedule.allowed_rhythms():
        return JSONResponse(status_code=422, content={"error_code": "RHYTHM_NOT_ALLOWED",
                                                      "allowed": list(agent_schedule.allowed_rhythms())}, headers=h)
    try:
        out = agent_schedule.request_rhythm(agent_id, rhythm)
    except OSError:
        return JSONResponse(status_code=503, content={"error_code": "CONTROL_UNWRITABLE"}, headers=h)
    return JSONResponse(status_code=202, content=out, headers=h)


@app.get("/api/operator/v1/runtime-service")
def get_runtime_service() -> Any:
    """Transport only the passive host/systemd observation artifact."""
    result = get_runtime_service_reader().read()
    if not result.ok:
        return JSONResponse(status_code=503, content={"error_code": result.error_code})
    return result.snapshot


@app.get("/api/operator/v1/burn-in")
def get_burn_in_status() -> Any:
    """Transport only the validated U2 atomic presentation artifact."""

    result = get_burn_in_status_reader().read()
    if not result.ok:
        return _burn_in_status_failure_response(result)

    payload = dict(result.snapshot or {})
    payload["snapshot_age_s"] = result.snapshot_age_s
    payload["freshness_classification"] = result.freshness_classification
    return payload


@app.get("/api/operator/v1/burn-in/statistics")
def get_burn_in_statistics() -> Any:
    """Descriptive metrics over the validated complete PPL presentation."""
    from observability.burn_in_statistics import build_burn_in_statistics

    result = get_burn_in_status_reader().read()
    if not result.ok:
        return _burn_in_status_failure_response(result)
    try:
        payload = build_burn_in_statistics(dict(result.snapshot or {}))
    except (ValueError, TypeError):
        return JSONResponse(status_code=503, content={"error_code": "BURN_IN_STATISTICS_INVALID_POPULATION"})
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


def get_research_strategy_board_reader() -> ResearchStrategyBoardReader:
    return _research_strategy_board_reader


@app.get("/api/operator/v1/research-strategies")
def get_research_strategies() -> Any:
    """Transport only the strategy presentation artifact; no source/evaluation I/O."""
    result = get_research_strategy_board_reader().read()
    if not result.ok:
        return JSONResponse(status_code=503, content={"error_code": result.error_code})
    return result.snapshot


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
    "get_storage_reader",
    "configure_storage_reader",
    "get_event_center_reader",
    "configure_event_center_reader",
    "configure_reader",
    "get_reader",
    "get_microstructure_reader",
    "configure_microstructure_reader",
    "get_runtime_service_reader",
    "configure_runtime_service_reader",
    "configure_burn_in_status_reader",
    "get_burn_in_status_reader",
    "configure_market_reader",
    "get_market_reader",
    "configure_ppl_comparison_reader",
    "get_ppl_comparison_reader",
    "configure_financial_reconciliation_reader",
    "get_financial_reconciliation_reader",
    "configure_research_lab_reader",
    "get_research_lab_reader",
]


# MARKET-MULTI-VENUE-02: separate artifact, no on-demand collection or calculation.
_venue_comparison_reader = VenueComparisonReader()

def configure_venue_comparison_reader(path=None, *, now_fn=None):
    global _venue_comparison_reader
    _venue_comparison_reader = VenueComparisonReader(path, **({} if now_fn is None else {"now_fn": now_fn}))
    return _venue_comparison_reader

@app.get("/api/operator/v1/venue-comparison")
def get_venue_comparison():
    result = _venue_comparison_reader.read()
    if not result.ok:
        return JSONResponse(status_code=503, content={"error_code": result.error_code}, headers={"Cache-Control": "no-store"})
    return JSONResponse(content=result.snapshot, headers={"Cache-Control": "no-store"})


# CRYPTORADAR-FLUX (#553): one explicitly configured artifact; no collection or calculation here.
_market_flow_reader = MarketFlowReader()

def configure_market_flow_reader(path=None):
    global _market_flow_reader
    _market_flow_reader = MarketFlowReader(path)
    return _market_flow_reader

@app.get("/api/operator/v1/market-flow")
def get_market_flow():
    result = _market_flow_reader.read()
    if not result.ok:
        return JSONResponse(status_code=503, content={"error_code": result.error_code}, headers={"Cache-Control": "no-store"})
    return JSONResponse(content=result.snapshot, headers={"Cache-Control": "no-store"})


# CAT-RADAR-KRAKEN-MEXC-01/BBO: one explicitly configured historical publication; no collection or calculation here.
_bbo_history_reader = BboHistoryReader()

def configure_bbo_history_reader(path=None):
    global _bbo_history_reader
    _bbo_history_reader = BboHistoryReader(path)
    return _bbo_history_reader

@app.get("/api/operator/v1/bbo-composite-history")
def get_bbo_composite_history():
    result = _bbo_history_reader.read()
    if not result.ok:
        return JSONResponse(status_code=503, content={"error_code": result.error_code}, headers={"Cache-Control": "no-store"})
    return JSONResponse(content=result.snapshot, headers={"Cache-Control": "no-store"})


# SCANNER-V1 (univers commun MEXC × Kraken): one explicitly configured publication;
# no collection here, only validation and serving-time freshness withdrawal.
_scanner_universe_reader = ScannerUniverseReader()

def configure_scanner_universe_reader(path=None, *, now_fn=None):
    global _scanner_universe_reader
    _scanner_universe_reader = ScannerUniverseReader(path, now_fn=now_fn)
    return _scanner_universe_reader

@app.get("/api/operator/v1/scanner-universe")
def get_scanner_universe():
    result = _scanner_universe_reader.read()
    if not result.ok:
        return JSONResponse(status_code=503, content={"error_code": result.error_code}, headers={"Cache-Control": "no-store"})
    return JSONResponse(content=result.snapshot, headers={"Cache-Control": "no-store"})


# S4-b (Radar scientifique): one explicitly configured sealed export, verified by the
# S4-a verifier (project_bytes) and served verbatim inside a service envelope carrying
# E2 (publication freshness) and E1 (catalogue provenance against the Scanner
# publication, read through the reader above). No collection, no score recomputation.
def _scanner_universe_read():
    return _scanner_universe_reader.read()


_radar_projection_reader = RadarProjectionReader(scanner_read=_scanner_universe_read)

def configure_radar_projection_reader(path=None, *, now_fn=None, max_age_ms=None):
    global _radar_projection_reader
    _radar_projection_reader = RadarProjectionReader(path, scanner_read=_scanner_universe_read, now_fn=now_fn,
                                                     max_age_ms=max_age_ms)
    return _radar_projection_reader

@app.get("/api/operator/v1/radar-projection")
def get_radar_projection():
    result = _radar_projection_reader.read()
    if not result.ok:
        content = {"error_code": result.error_code}
        if result.refusal_code is not None:
            content["refusal_code"] = result.refusal_code
        return JSONResponse(status_code=503, content=content, headers={"Cache-Control": "no-store"})
    return Response(content=result.body, media_type="application/json", headers={"Cache-Control": "no-store"})
