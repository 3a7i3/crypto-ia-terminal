"""FIN-02 passive financial reconciliation artifact.

The producer receives already-established FIN/PPL truth plus explicit read-only
observations, serializes them without recomputing accounting in the API/UI, and
optionally writes one atomic JSON artifact.

No function in this module submits orders, changes balances, starts runtime
components, or calls an exchange.
"""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from financial_institute.models import FinancialSnapshot
from financial_institute.reconciliation import (
    ExternalFinancialObservation,
    FinancialReconciliationSnapshot,
    PPLFinancialObservation,
    ReconciliationRecord,
    SimulatorFinancialObservation,
)


SCHEMA_VERSION = "1.0.0"
PRODUCT = "FIN02FinancialCockpit"
DOMAIN = "financial_reconciliation"
AUTHORITY = "FINANCIAL_OBSERVATION"
DEFAULT_FINANCIAL_RECONCILIATION_PATH = Path(
    os.getenv(
        "FINANCIAL_RECONCILIATION_SNAPSHOT_PATH",
        "databases/financial_reconciliation_snapshot.json",
    )
)


def _decimal_text(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else format(value, "f")


def _iso_utc_from_decimal(value: Decimal) -> str:
    from datetime import datetime, timezone

    return (
        datetime.fromtimestamp(float(value), tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def capture_simulator_observation(
    simulator: Any,
    *,
    observed_at: Decimal,
) -> SimulatorFinancialObservation:
    """Capture MEXC_SIM state coherently under its existing lock.

    This is intentionally a direct observation of already-existing state.
    No simulator method capable of mutation is called.
    """

    lock = getattr(simulator, "_lock", None)
    if lock is None:
        raise ValueError("MEXC_SIM exposes no lock for coherent observation")

    with lock:
        cash = Decimal(str(getattr(simulator, "_capital")))
        positions_obj = getattr(simulator, "_positions", None)
        if not isinstance(positions_obj, dict):
            raise ValueError("MEXC_SIM positions are unavailable")

        position_ids: list[str] = []
        reserved = Decimal("0")
        for position in positions_obj.values():
            trade_id = str(getattr(position, "pos_id"))
            principal = Decimal(str(getattr(position, "qty_usd")))
            if principal < 0:
                raise ValueError("simulator position principal must be >= 0")
            position_ids.append(trade_id)
            reserved += principal

        transitions_raw = getattr(
            simulator,
            "_legacy_transitions_in_flight",
            None,
        )
        transitions = (
            transitions_raw
            if isinstance(transitions_raw, int)
            and not isinstance(transitions_raw, bool)
            and transitions_raw >= 0
            else None
        )

        orders = getattr(simulator, "_orders", None)
        if isinstance(orders, dict):
            pending = 0
            for order in orders.values():
                raw_status = getattr(order, "status", "")
                status = getattr(raw_status, "value", raw_status)
                if str(status).upper() == "PENDING":
                    pending += 1
        else:
            pending = None

    return SimulatorFinancialObservation(
        observed_at=observed_at,
        cash_available=cash,
        capital_reserved=reserved,
        open_position_ids=tuple(position_ids),
        lifecycle_transitions_in_flight=transitions,
        pending_order_count=pending,
        source_id="MEXC_SIM",
        provenance=(
            "MEXC_SIM._capital + sum(_positions.qty_usd) + "
            "_orders/_legacy_transitions_in_flight under simulator lock"
        ),
    )


def _record_doc(record: ReconciliationRecord) -> dict[str, Any]:
    return {
        "record_id": record.record_id,
        "source_kind": record.source_kind.value,
        "source_id": record.source_id,
        "field": record.field,
        "projected_value": _decimal_text(record.projected_value),
        "observed_value": _decimal_text(record.observed_value),
        "delta_observed_minus_projected": _decimal_text(
            record.delta_observed_minus_projected
        ),
        "unreconciled_amount": _decimal_text(
            record.unreconciled_amount
        ),
        "status": record.status.value,
        "comparability": record.comparability.value,
        "freshness": record.freshness.value,
        "observed_at": _decimal_text(record.observed_at),
        "projected_provenance": record.projected_provenance,
        "observed_provenance": record.observed_provenance,
        "note": record.note,
    }


def _ppl_doc(observation: PPLFinancialObservation) -> dict[str, Any]:
    return {
        "paper_epoch_id": observation.paper_epoch_id,
        "source_stream_digest": observation.source_stream_digest,
        "last_sequence": observation.last_sequence,
        "observed_at": _decimal_text(observation.observed_at),
        "cash_available": _decimal_text(observation.cash_available),
        "capital_reserved": _decimal_text(observation.capital_reserved),
        "capital_unresolved": _decimal_text(
            observation.capital_unresolved
        ),
        "lifecycle_realized_pnl": _decimal_text(
            observation.lifecycle_realized_pnl
        ),
        "fees_paid": _decimal_text(observation.fees_paid),
        "open_position_ids": list(observation.open_position_ids),
        "closed_trade_ids": list(observation.closed_trade_ids),
        "unresolved_position_ids": list(
            observation.unresolved_position_ids
        ),
        "provenance": observation.provenance,
    }


def _simulator_doc(
    observation: Optional[SimulatorFinancialObservation],
) -> Optional[dict[str, Any]]:
    if observation is None:
        return None
    return {
        "source_id": observation.source_id,
        "observed_at": _decimal_text(observation.observed_at),
        "cash_available": _decimal_text(observation.cash_available),
        "capital_reserved": _decimal_text(
            observation.capital_reserved
        ),
        "open_position_ids": (
            None
            if observation.open_position_ids is None
            else list(observation.open_position_ids)
        ),
        "lifecycle_transitions_in_flight": (
            observation.lifecycle_transitions_in_flight
        ),
        "pending_order_count": observation.pending_order_count,
        "provenance": observation.provenance,
    }


def _external_doc(
    observation: Optional[ExternalFinancialObservation],
) -> Optional[dict[str, Any]]:
    if observation is None:
        return None
    return {
        "source_id": observation.source_id,
        "observed_at": _decimal_text(observation.observed_at),
        "asset": observation.asset,
        "free_cash": _decimal_text(observation.free_cash),
        "equity": _decimal_text(observation.equity),
        "applicability": observation.applicability.value,
        "provenance": observation.provenance,
    }


def build_financial_reconciliation_document(
    financial: FinancialSnapshot,
    reconciliation: FinancialReconciliationSnapshot,
    *,
    ppl: PPLFinancialObservation,
    generated_at: Decimal,
    simulator: Optional[SimulatorFinancialObservation] = None,
    external: Optional[ExternalFinancialObservation] = None,
) -> dict[str, Any]:
    """Materialize a closed presentation document without financial math."""

    if financial.snapshot_id != reconciliation.financial_snapshot_id:
        raise ValueError("financial/reconciliation snapshot identity mismatch")
    if financial.paper_epoch_id != reconciliation.paper_epoch_id:
        raise ValueError("financial/reconciliation epoch mismatch")
    if financial.source_stream_digest != ppl.source_stream_digest:
        raise ValueError("financial/PPL source digest mismatch")

    return {
        "schema_version": SCHEMA_VERSION,
        "product": PRODUCT,
        "domain": DOMAIN,
        "authority": AUTHORITY,
        "generated_at_utc": _iso_utc_from_decimal(generated_at),
        "reconciliation_id": reconciliation.reconciliation_id,
        "paper_epoch_id": reconciliation.paper_epoch_id,
        "financial_snapshot_id": financial.snapshot_id,
        "reconciliation_code_sha": reconciliation.reconciliation_code_sha,
        "source_stream_digest": financial.source_stream_digest,
        "last_source_sequence": financial.last_source_sequence,
        "fin_schema_version": financial.fin_schema_version,
        "fin_code_sha": financial.fin_code_sha,
        "source_code_sha": financial.source_code_sha,
        "config_hash": financial.config_hash,
        "financial_model": financial.financial_model.value,
        "asset": financial.asset,
        "financial": {
            "initial_epoch_capital": _decimal_text(
                financial.initial_epoch_capital
            ),
            "cash_available": _decimal_text(financial.cash_available),
            "capital_reserved": _decimal_text(
                financial.capital_reserved
            ),
            "capital_deployed": _decimal_text(
                financial.capital_deployed
            ),
            "capital_unresolved": _decimal_text(
                financial.capital_unresolved
            ),
            "gross_realized_price_pnl": _decimal_text(
                financial.gross_realized_price_pnl
            ),
            "fees_paid": _decimal_text(financial.fees_paid),
            "funding_net": _decimal_text(financial.funding_net),
            "funding_status": financial.funding_status.value,
            "funding_evidence_ref": financial.funding_evidence_ref,
            "realized_pnl": _decimal_text(financial.realized_pnl),
            "known_unrealized_pnl": _decimal_text(
                financial.known_unrealized_pnl
            ),
            "unrealized_pnl": _decimal_text(
                financial.unrealized_pnl
            ),
            "certified_equity": _decimal_text(
                financial.certified_equity
            ),
            "evidence_status": financial.evidence_status.value,
            "reconciliation_status": (
                financial.reconciliation_status.value
            ),
            "valuation_as_of": _decimal_text(
                financial.valuation_as_of
            ),
            "valuation_statuses": [
                status.value for status in financial.valuation_statuses
            ],
            "open_position_count": financial.open_position_count,
            "settled_position_count": (
                financial.settled_position_count
            ),
            "unresolved_position_count": (
                financial.unresolved_position_count
            ),
        },
        "reconciliation": {
            "overall_status": reconciliation.overall_status.value,
            "as_of": _decimal_text(reconciliation.as_of),
            "unresolved_capital": _decimal_text(
                reconciliation.unresolved_capital
            ),
            "unreconciled_capital": _decimal_text(
                reconciliation.unreconciled_capital
            ),
            "policy": {
                "absolute_tolerance": _decimal_text(
                    reconciliation.policy.absolute_tolerance
                ),
                "relative_tolerance": _decimal_text(
                    reconciliation.policy.relative_tolerance
                ),
                "stale_after_s": _decimal_text(
                    reconciliation.policy.stale_after_s
                ),
            },
            "ppl_observation_digest": (
                reconciliation.ppl_observation_digest
            ),
            "simulator_observation_digest": (
                reconciliation.simulator_observation_digest
            ),
            "external_observation_digest": (
                reconciliation.external_observation_digest
            ),
        },
        "sources": {
            "ppl": _ppl_doc(ppl),
            "simulator": _simulator_doc(simulator),
            "external": _external_doc(external),
        },
        "records": [
            _record_doc(record)
            for record in reconciliation.records
        ],
    }


def write_financial_reconciliation_document(
    document: dict[str, Any],
    *,
    path: Path = DEFAULT_FINANCIAL_RECONCILIATION_PATH,
) -> None:
    """Atomically replace one presentation artifact.

    This writer owns only its target artifact.  It never writes PPL, FIN ledger
    state, simulator state or exchange state.
    """

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


__all__ = [
    "AUTHORITY",
    "DEFAULT_FINANCIAL_RECONCILIATION_PATH",
    "DOMAIN",
    "PRODUCT",
    "SCHEMA_VERSION",
    "build_financial_reconciliation_document",
    "capture_simulator_observation",
    "write_financial_reconciliation_document",
]
