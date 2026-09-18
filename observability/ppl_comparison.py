"""WEB-02 passive legacy-vs-PPL comparison materialization.

Observational only: this module snapshots already-existing in-process MEXC_SIM
and PPL SHADOW state. Raw values and provenance are preserved. Numeric deltas
exist only for genuinely COMPARABLE numeric facts.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

SCHEMA_VERSION = "1.0.0"
PRODUCT = "PPLComparator"
DOMAIN = "ppl_comparison"
AUTHORITY = "OBSERVATIONAL_TELEMETRY"
MODE = "SHADOW_COMPARISON"
NUMERIC_ABS_TOL = 1e-9

_COMPARISON_CLASSES = {"COMPARABLE", "PARTIAL", "UNRESOLVED"}
_SHADOW_STATUSES = {"OFF", "WAITING_CLEAN_BOUNDARY", "ACTIVE", "DEGRADED"}

# A legacy mutation and its downstream PPL observation are deliberately not one
# shared transaction. WEB-02 therefore publishes only after two consecutive
# legacy+PPL source-pair captures are byte-semantically stable. This prevents a
# mid-transition observation from being materialized as a durable divergence,
# while a persistent divergence remains visible. The guard is bounded so the
# observer can never stall the advisor loop indefinitely.
_SOURCE_STABILITY_ATTEMPTS = 4
_SOURCE_STABILITY_SLEEP_S = 0.025


def _iso_utc(ts: float) -> str:
    return (
        datetime.fromtimestamp(float(ts), tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _json_value(value: Any) -> Any:
    value = _enum_value(value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite comparison value: {value!r}")
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    return str(value)


def _source(value: Any, *, status: str, provenance: str) -> Dict[str, Any]:
    return {
        "value": _json_value(value),
        "status": str(status),
        "provenance": str(provenance),
    }


def _comparison_id(
    paper_epoch_id: Optional[str],
    domain: str,
    field: str,
    trade_id: Optional[str],
) -> str:
    canonical = "\x1f".join(
        (
            "WEB-02-PPL-COMPARATOR-V1",
            paper_epoch_id or "NO_EPOCH",
            domain,
            trade_id or "__GLOBAL__",
            field,
        )
    ).encode("utf-8")
    return "web02-" + hashlib.sha256(canonical).hexdigest()


def _same_number(left: float, right: float) -> bool:
    return math.isclose(
        float(left),
        float(right),
        rel_tol=0.0,
        abs_tol=NUMERIC_ABS_TOL,
    )


def _canonical_side(value: Any) -> Any:
    raw = str(_enum_value(value)).upper()
    if raw in {"BUY", "LONG"}:
        return "LONG"
    if raw in {"SELL", "SHORT"}:
        return "SHORT"
    return raw


def _same_value(left: Any, right: Any, rule: str) -> bool:
    if rule == "canonical_side":
        return _canonical_side(left) == _canonical_side(right)
    if _finite_number(left) and _finite_number(right):
        return _same_number(float(left), float(right))
    return _json_value(left) == _json_value(right)


def _record(
    *,
    paper_epoch_id: Optional[str],
    domain: str,
    field: str,
    trade_id: Optional[str],
    classification: str,
    legacy: Dict[str, Any],
    ppl: Dict[str, Any],
    comparison_rule: str = "exact",
    note: Optional[str] = None,
) -> Dict[str, Any]:
    if classification not in _COMPARISON_CLASSES:
        raise ValueError(f"invalid comparison class: {classification}")

    legacy_present = legacy["status"] == "PRESENT"
    ppl_present = ppl["status"] == "PRESENT"

    delta: Optional[float] = None
    if classification != "COMPARABLE":
        relation = "NOT_COMPARABLE"
    elif legacy_present and ppl_present:
        relation = (
            "EQUAL"
            if _same_value(legacy["value"], ppl["value"], comparison_rule)
            else "DIFFERENT"
        )
        if _finite_number(legacy["value"]) and _finite_number(ppl["value"]):
            delta = float(ppl["value"]) - float(legacy["value"])
    elif legacy_present:
        relation = "LEGACY_ONLY"
    elif ppl_present:
        relation = "PPL_ONLY"
    else:
        relation = "NOT_COMPARABLE"

    return {
        "comparison_id": _comparison_id(
            paper_epoch_id, domain, field, trade_id
        ),
        "domain": domain,
        "field": field,
        "trade_id": trade_id,
        "classification": classification,
        "relation": relation,
        "legacy": legacy,
        "ppl": ppl,
        "delta_ppl_minus_legacy": delta,
        "comparison_rule": comparison_rule,
        "note": note,
    }


def _snapshot_legacy(simulator: Any) -> Dict[str, Any]:
    """Copy authoritative MEXC_SIM accounting state under its own lock.

    Private fields are intentionally READ only: MexcSimulator currently has
    no complete public accounting snapshot. No execution method is called.
    """

    lock = getattr(simulator, "_lock", None)
    if lock is None:
        raise ValueError("MEXC_SIM exposes no lock for coherent snapshotting")

    with lock:
        capital = float(getattr(simulator, "_capital"))
        initial_capital = float(getattr(simulator, "_initial_capital"))
        positions = []
        for pos in getattr(simulator, "_positions", {}).values():
            positions.append(
                {
                    "trade_id": str(getattr(pos, "pos_id")),
                    "symbol": str(getattr(pos, "symbol")),
                    "side": str(_enum_value(getattr(pos, "side"))),
                    "principal": float(getattr(pos, "qty_usd")),
                    "entry_price": float(getattr(pos, "entry_price")),
                    "entry_fee": float(getattr(pos, "fee_entry_usd")),
                    "opened_at": float(getattr(pos, "opened_ts")),
                    "decision_id": getattr(pos, "decision_id", None),
                    "restored_evidence_gaps": list(
                        getattr(pos, "restored_evidence_gaps", []) or []
                    ),
                }
            )

        closed_session = []
        for pos in getattr(simulator, "_closed", []):
            closed_session.append(
                {
                    "trade_id": str(getattr(pos, "pos_id")),
                    "symbol": str(getattr(pos, "symbol")),
                    "side": str(_enum_value(getattr(pos, "side"))),
                    "principal": float(getattr(pos, "qty_usd")),
                    "entry_price": float(getattr(pos, "entry_price")),
                    "entry_fee": float(getattr(pos, "fee_entry_usd")),
                    "exit_price": float(getattr(pos, "exit_price")),
                    "realized_pnl": float(getattr(pos, "pnl_usd")),
                    "closed_at": float(getattr(pos, "closed_ts")),
                    "close_reason": str(getattr(pos, "close_reason")),
                    "decision_id": getattr(pos, "decision_id", None),
                    "restored_evidence_gaps": list(
                        getattr(pos, "restored_evidence_gaps", []) or []
                    ),
                }
            )

    return {
        "free_cash": capital,
        "initial_capital": initial_capital,
        "positions": sorted(positions, key=lambda row: row["trade_id"]),
        "closed_session": sorted(
            closed_session, key=lambda row: row["trade_id"]
        ),
    }


def _snapshot_ppl(simulator: Any) -> Dict[str, Any]:
    shadow = getattr(simulator, "_shadow_observer", None)
    if shadow is None:
        return {
            "status": "OFF",
            "paper_epoch_id": None,
            "last_error": None,
            "projection": None,
            "events": [],
        }

    snap = shadow.snapshot()
    status = str(_enum_value(snap.status))
    if status not in _SHADOW_STATUSES:
        status = "DEGRADED"

    projection = shadow.projection
    events = shadow.events

    if projection is None:
        projection_doc = None
    else:
        projection_doc = {
            "paper_epoch_id": projection.paper_epoch_id,
            "available_cash": float(projection.available_cash),
            "reserved_principal": float(projection.reserved_principal),
            "unresolved_capital": float(projection.unresolved_capital),
            "realized_pnl": float(projection.realized_pnl),
            "fees_paid": float(projection.fees_paid),
            "last_sequence": int(projection.last_sequence),
            "closed_trade_ids": sorted(
                str(x) for x in projection.closed_trade_ids
            ),
            "open_positions": [
                {
                    "trade_id": str(pos.trade_id),
                    "symbol": str(pos.symbol),
                    "side": str(_enum_value(pos.side)),
                    "principal": float(pos.principal),
                    "entry_price": float(pos.entry_price),
                    "entry_fee": float(pos.entry_fee),
                    "opened_sequence": int(pos.opened_sequence),
                }
                for pos in sorted(
                    projection.open_positions.values(),
                    key=lambda p: str(p.trade_id),
                )
            ],
        }

    event_docs = [
        {
            "event_id": str(event.event_id),
            "sequence": int(event.sequence),
            "event_type": str(_enum_value(event.event_type)),
            "trade_id": event.trade_id,
            "decision_id": event.decision_id,
            "timestamp": float(event.timestamp),
            "payload": _json_value(dict(event.payload)),
        }
        for event in events
    ]

    return {
        "status": status,
        "paper_epoch_id": snap.paper_epoch_id or None,
        "last_error": snap.last_error,
        "projection": projection_doc,
        "events": event_docs,
    }


def _source_pair_fingerprint(
    legacy: Dict[str, Any],
    ppl: Dict[str, Any],
) -> str:
    payload = json.dumps(
        {"legacy": legacy, "ppl": ppl},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _snapshot_sources_consistently(simulator: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Return one bounded, stable legacy+PPL source pair.

    MEXC_SIM applies its authoritative mutation before invoking the passive PPL
    observer. A comparator read can therefore land inside that short hand-off
    window. Publishing such a pair would turn scheduling latency into a false
    durable divergence. Two consecutive identical captures are required. A
    genuinely persistent divergence is stable and is still published exactly
    as observed. Continuous movement fails passively at the sidecar writer.
    """

    legacy = _snapshot_legacy(simulator)
    ppl = _snapshot_ppl(simulator)
    fingerprint = _source_pair_fingerprint(legacy, ppl)

    for _ in range(_SOURCE_STABILITY_ATTEMPTS - 1):
        time.sleep(_SOURCE_STABILITY_SLEEP_S)
        next_legacy = _snapshot_legacy(simulator)
        next_ppl = _snapshot_ppl(simulator)
        next_fingerprint = _source_pair_fingerprint(next_legacy, next_ppl)
        if next_fingerprint == fingerprint:
            return next_legacy, next_ppl
        legacy, ppl, fingerprint = next_legacy, next_ppl, next_fingerprint

    raise RuntimeError(
        "WEB-02 source pair changed during bounded coherent capture; "
        "comparison artifact withheld"
    )


def _presence(legacy_present: bool, ppl_present: bool) -> str:
    if legacy_present and ppl_present:
        return "BOTH"
    if legacy_present:
        return "LEGACY_ONLY"
    if ppl_present:
        return "PPL_ONLY"
    return "NEITHER"


def _summary(comparisons: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    rows = list(comparisons)
    return {
        "total": len(rows),
        "comparable": sum(r["classification"] == "COMPARABLE" for r in rows),
        "partial": sum(r["classification"] == "PARTIAL" for r in rows),
        "unresolved": sum(
            r["classification"] == "UNRESOLVED" for r in rows
        ),
        "equal": sum(r["relation"] == "EQUAL" for r in rows),
        "different": sum(r["relation"] == "DIFFERENT" for r in rows),
        "legacy_only": sum(r["relation"] == "LEGACY_ONLY" for r in rows),
        "ppl_only": sum(r["relation"] == "PPL_ONLY" for r in rows),
        "not_comparable": sum(
            r["relation"] == "NOT_COMPARABLE" for r in rows
        ),
    }


def build_ppl_comparison_snapshot(
    simulator: Any,
    *,
    cycle: int,
    process_instance_id: str,
    source_sha: Optional[str],
    now_fn: Callable[[], float],
) -> Dict[str, Any]:
    legacy, ppl = _snapshot_sources_consistently(simulator)
    status = ppl["status"]
    projection = ppl["projection"]
    epoch_id = ppl["paper_epoch_id"]
    active = status == "ACTIVE" and projection is not None

    comparisons: list[Dict[str, Any]] = []
    positions: list[Dict[str, Any]] = []
    closed_session: list[Dict[str, Any]] = []

    if active:
        assert projection is not None
        comparisons.append(
            _record(
                paper_epoch_id=epoch_id,
                domain="accounting",
                field="free_cash",
                trade_id=None,
                classification="COMPARABLE",
                legacy=_source(
                    legacy["free_cash"],
                    status="PRESENT",
                    provenance="MEXC_SIM._capital",
                ),
                ppl=_source(
                    projection["available_cash"],
                    status="PRESENT",
                    provenance="PPL.projection.available_cash",
                ),
                comparison_rule="numeric_abs_tol_1e-9",
                note="Primary accounting delta; delta is PPL minus legacy.",
            )
        )

        legacy_positions = {
            row["trade_id"]: row for row in legacy["positions"]
        }
        ppl_positions = {
            row["trade_id"]: row for row in projection["open_positions"]
        }
        comparisons.append(
            _record(
                paper_epoch_id=epoch_id,
                domain="positions",
                field="open_count",
                trade_id=None,
                classification="COMPARABLE",
                legacy=_source(
                    len(legacy_positions),
                    status="PRESENT",
                    provenance="MEXC_SIM._positions",
                ),
                ppl=_source(
                    len(ppl_positions),
                    status="PRESENT",
                    provenance="PPL.projection.open_positions",
                ),
            )
        )
        comparisons.append(
            _record(
                paper_epoch_id=epoch_id,
                domain="positions",
                field="reserved_principal",
                trade_id=None,
                classification="PARTIAL",
                legacy=_source(
                    sum(r["principal"] for r in legacy_positions.values()),
                    status="DERIVED_FROM_LIVE_POSITIONS",
                    provenance="sum(MEXC_SIM._positions.qty_usd)",
                ),
                ppl=_source(
                    projection["reserved_principal"],
                    status="PRESENT",
                    provenance="PPL.projection.reserved_principal",
                ),
                note=(
                    "Legacy has no explicit reserved-principal field; "
                    "no delta is asserted."
                ),
            )
        )
        comparisons.append(
            _record(
                paper_epoch_id=epoch_id,
                domain="performance",
                field="realized_pnl",
                trade_id=None,
                classification="PARTIAL",
                legacy=_source(
                    sum(r["realized_pnl"] for r in legacy["closed_session"]),
                    status="SESSION_ONLY",
                    provenance="sum(MEXC_SIM._closed.pnl_usd)",
                ),
                ppl=_source(
                    projection["realized_pnl"],
                    status="EPOCH_AGGREGATE",
                    provenance="PPL.projection.realized_pnl",
                ),
                note=(
                    "Legacy _closed is process-session-local; PPL is "
                    "epoch-wide. Raw values are shown without a delta."
                ),
            )
        )
        comparisons.append(
            _record(
                paper_epoch_id=epoch_id,
                domain="accounting",
                field="fees_paid",
                trade_id=None,
                classification="UNRESOLVED",
                legacy=_source(
                    None,
                    status="UNRESOLVED",
                    provenance=(
                        "Legacy has no complete exact cumulative fee "
                        "projection with durable exit-fee evidence"
                    ),
                ),
                ppl=_source(
                    projection["fees_paid"],
                    status="PRESENT",
                    provenance="PPL.projection.fees_paid",
                ),
                note="UNKNOWN != ZERO; no legacy fee is synthesized.",
            )
        )
        comparisons.append(
            _record(
                paper_epoch_id=epoch_id,
                domain="lifecycle",
                field="closed_count",
                trade_id=None,
                classification="PARTIAL",
                legacy=_source(
                    len(legacy["closed_session"]),
                    status="SESSION_ONLY",
                    provenance="MEXC_SIM._closed",
                ),
                ppl=_source(
                    len(projection["closed_trade_ids"]),
                    status="EPOCH_AGGREGATE",
                    provenance="PPL.projection.closed_trade_ids",
                ),
                note="Session-local legacy count is not epoch-equivalent.",
            )
        )

        if not legacy_positions and not ppl_positions:
            comparisons.append(
                _record(
                    paper_epoch_id=epoch_id,
                    domain="valuation",
                    field="unrealized_pnl",
                    trade_id=None,
                    classification="COMPARABLE",
                    legacy=_source(
                        0.0,
                        status="PRESENT",
                        provenance="MEXC_SIM zero open positions",
                    ),
                    ppl=_source(
                        0.0,
                        status="PRESENT",
                        provenance="PPL zero open positions",
                    ),
                    comparison_rule="numeric_abs_tol_1e-9",
                    note="Zero open positions makes mark coverage trivial.",
                )
            )
        else:
            comparisons.append(
                _record(
                    paper_epoch_id=epoch_id,
                    domain="valuation",
                    field="unrealized_pnl",
                    trade_id=None,
                    classification="UNRESOLVED",
                    legacy=_source(
                        None,
                        status="UNRESOLVED",
                        provenance="MEXC_SIM mark contract",
                    ),
                    ppl=_source(
                        None,
                        status="UNRESOLVED",
                        provenance="PPL mark-coverage contract",
                    ),
                    note=(
                        "V1 refuses to mix legacy zero-on-missing-price "
                        "presentation with PPL fail-closed mark coverage."
                    ),
                )
            )

        for trade_id in sorted(set(legacy_positions) | set(ppl_positions)):
            lpos = legacy_positions.get(trade_id)
            ppos = ppl_positions.get(trade_id)
            field_ids: list[str] = []
            presence = _record(
                paper_epoch_id=epoch_id,
                domain="open_position",
                field="presence",
                trade_id=trade_id,
                classification="COMPARABLE",
                legacy=_source(
                    True if lpos else None,
                    status="PRESENT" if lpos else "ABSENT",
                    provenance="MEXC_SIM._positions",
                ),
                ppl=_source(
                    True if ppos else None,
                    status="PRESENT" if ppos else "ABSENT",
                    provenance="PPL.projection.open_positions",
                ),
            )
            comparisons.append(presence)
            field_ids.append(presence["comparison_id"])

            if lpos and ppos:
                for field, rule in (
                    ("symbol", "exact"),
                    ("side", "canonical_side"),
                    ("principal", "numeric_abs_tol_1e-9"),
                    ("entry_price", "numeric_abs_tol_1e-9"),
                ):
                    row = _record(
                        paper_epoch_id=epoch_id,
                        domain="open_position",
                        field=field,
                        trade_id=trade_id,
                        classification="COMPARABLE",
                        legacy=_source(
                            lpos[field],
                            status="PRESENT",
                            provenance=f"MEXC_SIM._positions.{field}",
                        ),
                        ppl=_source(
                            ppos[field],
                            status="PRESENT",
                            provenance=f"PPL.open_positions.{field}",
                        ),
                        comparison_rule=rule,
                        note=(
                            "BUY/LONG and SELL/SHORT are canonical equivalents."
                            if field == "side"
                            else None
                        ),
                    )
                    comparisons.append(row)
                    field_ids.append(row["comparison_id"])

                fee_unknown = (
                    "fee_entry_unknown"
                    in lpos["restored_evidence_gaps"]
                )
                fee = _record(
                    paper_epoch_id=epoch_id,
                    domain="open_position",
                    field="entry_fee",
                    trade_id=trade_id,
                    classification=(
                        "UNRESOLVED" if fee_unknown else "COMPARABLE"
                    ),
                    legacy=_source(
                        lpos["entry_fee"],
                        status="UNRESOLVED" if fee_unknown else "PRESENT",
                        provenance="MEXC_SIM._positions.fee_entry_usd",
                    ),
                    ppl=_source(
                        ppos["entry_fee"],
                        status="PRESENT",
                        provenance="PPL.open_positions.entry_fee",
                    ),
                    comparison_rule="numeric_abs_tol_1e-9",
                    note=(
                        "Legacy numeric 0 is a restore fallback, not fee evidence."
                        if fee_unknown
                        else None
                    ),
                )
                comparisons.append(fee)
                field_ids.append(fee["comparison_id"])

            positions.append(
                {
                    "trade_id": trade_id,
                    "relation": _presence(lpos is not None, ppos is not None),
                    "legacy_present": lpos is not None,
                    "ppl_present": ppos is not None,
                    "field_comparison_ids": field_ids,
                }
            )

        close_events = {
            row["trade_id"]: row
            for row in ppl["events"]
            if row["event_type"] == "POSITION_CLOSED" and row["trade_id"]
        }
        legacy_closed = {
            row["trade_id"]: row for row in legacy["closed_session"]
        }

        for trade_id in sorted(set(legacy_closed) | set(close_events)):
            lrow = legacy_closed.get(trade_id)
            prow = close_events.get(trade_id)
            field_ids: list[str] = []

            exit_price = _record(
                paper_epoch_id=epoch_id,
                domain="closed_trade",
                field="exit_price",
                trade_id=trade_id,
                classification=(
                    "COMPARABLE" if lrow and prow else "PARTIAL"
                ),
                legacy=_source(
                    lrow["exit_price"] if lrow else None,
                    status="PRESENT" if lrow else "SESSION_NOT_AVAILABLE",
                    provenance="MEXC_SIM._closed.exit_price",
                ),
                ppl=_source(
                    prow["payload"].get("exit_price") if prow else None,
                    status="PRESENT" if prow else "ABSENT",
                    provenance="PPL POSITION_CLOSED payload.exit_price",
                ),
                comparison_rule="numeric_abs_tol_1e-9",
                note=(
                    None
                    if lrow and prow
                    else "Legacy closed positions are session-local after restart."
                ),
            )
            comparisons.append(exit_price)
            field_ids.append(exit_price["comparison_id"])

            exit_fee = _record(
                paper_epoch_id=epoch_id,
                domain="closed_trade",
                field="exit_fee",
                trade_id=trade_id,
                classification="UNRESOLVED",
                legacy=_source(
                    None,
                    status="UNRESOLVED",
                    provenance="MEXC_SIM closed position has no exit_fee field",
                ),
                ppl=_source(
                    prow["payload"].get("exit_fee") if prow else None,
                    status="PRESENT" if prow else "ABSENT",
                    provenance="PPL POSITION_CLOSED payload.exit_fee",
                ),
                note="Exit fee is never reconstructed from config.",
            )
            comparisons.append(exit_fee)
            field_ids.append(exit_fee["comparison_id"])

            realized = _record(
                paper_epoch_id=epoch_id,
                domain="closed_trade",
                field="realized_pnl",
                trade_id=trade_id,
                classification="PARTIAL",
                legacy=_source(
                    lrow["realized_pnl"] if lrow else None,
                    status="PRESENT" if lrow else "SESSION_NOT_AVAILABLE",
                    provenance="MEXC_SIM._closed.pnl_usd",
                ),
                ppl=_source(
                    None,
                    status="NOT_MATERIALIZED_PER_TRADE",
                    provenance=(
                        "PPL exposes epoch aggregate realized_pnl but no "
                        "per-trade realized-PnL map"
                    ),
                ),
                note="WEB-02 does not duplicate the PPL accounting formula.",
            )
            comparisons.append(realized)
            field_ids.append(realized["comparison_id"])

            closed_session.append(
                {
                    "trade_id": trade_id,
                    "relation": _presence(lrow is not None, prow is not None),
                    "legacy_present": lrow is not None,
                    "ppl_present": prow is not None,
                    "field_comparison_ids": field_ids,
                }
            )

    if active:
        unavailable_reason = None
    elif status == "OFF":
        unavailable_reason = (
            "PPL SHADOW is OFF; convergence must not be inferred."
        )
    else:
        unavailable_reason = (
            f"PPL SHADOW status={status}; comparisons are withheld rather "
            "than presenting stale/degraded state as converged."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "product": PRODUCT,
        "domain": DOMAIN,
        "authority": AUTHORITY,
        "mode": MODE,
        "generated_at_utc": _iso_utc(float(now_fn())),
        "process_instance_id": str(process_instance_id),
        "cycle": int(cycle),
        "source_sha": source_sha,
        "shadow_status": status,
        "paper_epoch_id": epoch_id,
        "comparison_available": active,
        "comparison_unavailable_reason": unavailable_reason,
        "legacy_source": {
            "source": "paper_trading.mexc_simulator.MexcSimulator",
            "authority": "PAPER_AUTHORITY",
            "scope": "live_process_state",
        },
        "ppl_source": {
            "source": "paper_trading.ppl_shadow.PPLShadowRuntime.projection",
            "authority": "NONE",
            "scope": "configured_shadow_epoch",
            "last_error": ppl["last_error"],
        },
        "summary": _summary(comparisons),
        "comparisons": comparisons,
        "positions": positions,
        "closed_session": closed_session,
        "ppl_events": ppl["events"],
    }


def write_ppl_comparison_snapshot(
    simulator: Any,
    *,
    path: Path,
    cycle: int,
    process_instance_id: str,
    source_sha: Optional[str],
    now_fn: Callable[[], float],
) -> Dict[str, Any]:
    snapshot = build_ppl_comparison_snapshot(
        simulator,
        cycle=cycle,
        process_instance_id=process_instance_id,
        source_sha=source_sha,
        now_fn=now_fn,
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
    return snapshot


__all__ = [
    "AUTHORITY",
    "DOMAIN",
    "MODE",
    "NUMERIC_ABS_TOL",
    "PRODUCT",
    "SCHEMA_VERSION",
    "build_ppl_comparison_snapshot",
    "write_ppl_comparison_snapshot",
]
