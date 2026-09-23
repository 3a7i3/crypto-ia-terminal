"""FIN-02R2 — coherent passive financial capture boundary.

R2 freezes one observational instant across the already-running authoritative
PAPER stack.  The capture owns no runtime authority and performs no writes.

Critical lock order is inherited from MexcSimulator's authoritative OPEN/CLOSE
paths:

    MEXC_SIM._lock -> PPLAuthorityRuntime._lock

R2 acquires the same simulator lock first, asks the simulator-owned authority
runtime for one consistent durable view, then reads simulator accounting fields
before releasing the simulator lock.

The authority runtime is intentionally discovered from the simulator.  Callers
cannot inject a second PPL runtime into this boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from financial_institute.models import ValuationObservation
from financial_institute.reconciliation import (
    PPLFinancialObservation,
    SimulatorFinancialObservation,
    ppl_observation_from_events,
)
from financial_institute.runtime_provenance import (
    FinancialRuntimeProvenance,
    FinancialRuntimeSemanticInputs,
    bind_financial_runtime_provenance,
)
from financial_institute.semantics import (
    canonical_decimal,
    canonical_identity_hash,
)
from observability.financial_reconciliation import (
    _capture_simulator_observation_locked,
)
from paper_trading.ledger_events import LedgerEvent
from paper_trading.paper_portfolio_ledger import project


FIN02_R2_CAPTURE_SCHEMA_VERSION = 1
FIN02_R2_CAPTURE_NAMESPACE = "FIN02_COHERENT_PASSIVE_CAPTURE_V1"
FIN02_R2_LOCK_ORDER = "MEXC_SIM_LOCK_THEN_PPL_RUNTIME_LOCK"


class CoherentFinancialCaptureError(ValueError):
    """The requested observation cannot prove a coherent passive boundary."""


def _decimal_text(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else format(value, "f")


def _status_text(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _normalize_valuation_evidence(
    observations: Sequence[ValuationObservation],
    *,
    open_positions: Mapping[str, object],
) -> tuple[ValuationObservation, ...]:
    """Freeze explicit mark evidence without inventing missing observations."""

    normalized: list[ValuationObservation] = []
    seen: set[str] = set()

    for observation in observations:
        if not isinstance(observation, ValuationObservation):
            raise CoherentFinancialCaptureError(
                "valuation evidence must contain ValuationObservation values"
            )
        if observation.trade_id in seen:
            raise CoherentFinancialCaptureError(
                "duplicate valuation observation for "
                f"trade_id={observation.trade_id!r}"
            )
        seen.add(observation.trade_id)

        position = open_positions.get(observation.trade_id)
        if position is None:
            raise CoherentFinancialCaptureError(
                "valuation observation references a trade that is not open "
                f"in the captured PPL view: {observation.trade_id!r}"
            )
        symbol = str(getattr(position, "symbol"))
        if observation.symbol != symbol:
            raise CoherentFinancialCaptureError(
                "valuation symbol does not match captured PPL position for "
                f"trade_id={observation.trade_id!r}"
            )

        price = (
            None
            if observation.price is None
            else canonical_decimal("valuation.price", observation.price)
        )
        source_timestamp = (
            None
            if observation.source_timestamp is None
            else canonical_decimal(
                "valuation.source_timestamp",
                observation.source_timestamp,
            )
        )
        normalized.append(
            ValuationObservation(
                trade_id=observation.trade_id,
                symbol=observation.symbol,
                source_id=observation.source_id,
                venue=observation.venue,
                market_type=observation.market_type,
                price=price,
                source_timestamp=source_timestamp,
            )
        )

    return tuple(sorted(normalized, key=lambda item: item.trade_id))


def _valuation_evidence_digest(
    observations: Sequence[ValuationObservation],
) -> str:
    return canonical_identity_hash(
        "FIN02_R2_VALUATION_EVIDENCE_V1",
        {
            "observations": [
                {
                    "trade_id": item.trade_id,
                    "symbol": item.symbol,
                    "source_id": item.source_id,
                    "venue": item.venue,
                    "market_type": item.market_type,
                    "price": _decimal_text(item.price),
                    "source_timestamp": _decimal_text(
                        item.source_timestamp
                    ),
                }
                for item in observations
            ]
        },
    )


@dataclass(frozen=True)
class CoherentFinancialCapture:
    """One immutable R2 observation bundle."""

    capture_id: str
    schema_version: int
    captured_at: Decimal
    lock_order: str
    authority_status: str
    authority_last_error: Optional[str]
    simulator_generation: int
    runtime_provenance: FinancialRuntimeProvenance
    ppl_events: tuple[LedgerEvent, ...]
    ppl_observation: PPLFinancialObservation
    simulator_observation: SimulatorFinancialObservation
    valuation_observations: tuple[ValuationObservation, ...]
    valuation_evidence_digest: str


def capture_coherent_financial_boundary(
    simulator: Any,
    *,
    captured_at: Decimal,
    semantic_inputs: FinancialRuntimeSemanticInputs,
    valuation_observations: Sequence[ValuationObservation] = (),
) -> CoherentFinancialCapture:
    """Capture PPL + simulator + valuation evidence without runtime mutation.

    The simulator lock is held continuously while:
    1. the simulator-owned PPL runtime returns a locked consistent view; and
    2. MEXC_SIM accounting fields are copied.

    No execution, exchange, PPL append, FIN ledger or wall-clock method is
    called by this boundary.
    """

    observed_at = canonical_decimal("captured_at", captured_at)
    valuation_inputs = tuple(valuation_observations)

    lifecycle_authority = getattr(
        simulator,
        "_lifecycle_authority",
        None,
    )
    if not bool(
        getattr(lifecycle_authority, "ppl_is_authoritative", False)
    ):
        raise CoherentFinancialCaptureError(
            "R2 requires simulator lifecycle authority=PPL_AUTHORITY"
        )

    if getattr(simulator, "_shadow_observer", None) is not None:
        raise CoherentFinancialCaptureError(
            "R2 PPL_AUTHORITY capture forbids an attached SHADOW observer"
        )

    runtime = getattr(simulator, "_authority_runtime", None)
    if runtime is None:
        raise CoherentFinancialCaptureError(
            "R2 requires the simulator-owned PPL authority runtime"
        )

    lock = getattr(simulator, "_lock", None)
    if lock is None:
        raise CoherentFinancialCaptureError(
            "MEXC_SIM exposes no lock for coherent capture"
        )

    with lock:
        if getattr(simulator, "_running", None) is not True:
            raise CoherentFinancialCaptureError(
                "R2 capture requires an already-running MEXC_SIM"
            )

        generation_before = getattr(
            simulator,
            "_legacy_generation",
            None,
        )
        if (
            not isinstance(generation_before, int)
            or isinstance(generation_before, bool)
            or generation_before < 0
        ):
            raise CoherentFinancialCaptureError(
                "MEXC_SIM generation is unavailable"
            )

        view = runtime.consistent_view()
        authority_status = _status_text(getattr(view, "status", ""))
        if authority_status != "READY":
            raise CoherentFinancialCaptureError(
                "PPL authority runtime is not READY"
            )

        simulator_observation = _capture_simulator_observation_locked(
            simulator,
            observed_at=observed_at,
        )

        generation_after = getattr(
            simulator,
            "_legacy_generation",
            None,
        )
        if generation_after != generation_before:
            raise CoherentFinancialCaptureError(
                "MEXC_SIM generation changed inside the R2 critical section"
            )
        if simulator_observation.lifecycle_transitions_in_flight != 0:
            raise CoherentFinancialCaptureError(
                "R2 requires zero lifecycle transitions in flight"
            )

        events = tuple(getattr(view, "events", ()))
        projection = getattr(view, "projection", None)
        paper_epoch_id = str(getattr(view, "paper_epoch_id", "") or "")
        last_error = getattr(view, "last_error", None)

    if not events:
        raise CoherentFinancialCaptureError(
            "PPL authority view contains no durable events"
        )
    if projection is None:
        raise CoherentFinancialCaptureError(
            "PPL authority view contains no projection"
        )
    if projection != project(events):
        raise CoherentFinancialCaptureError(
            "PPL authority projection differs from captured event replay"
        )

    ppl_observation = ppl_observation_from_events(
        events,
        observed_at=observed_at,
    )
    runtime_provenance = bind_financial_runtime_provenance(
        events,
        semantic_inputs,
    )

    if paper_epoch_id != ppl_observation.paper_epoch_id:
        raise CoherentFinancialCaptureError(
            "PPL view epoch differs from replayed event population"
        )
    if (
        runtime_provenance.paper_epoch_id
        != ppl_observation.paper_epoch_id
    ):
        raise CoherentFinancialCaptureError(
            "R1 provenance epoch differs from captured PPL population"
        )
    if (
        runtime_provenance.source_stream_digest
        != ppl_observation.source_stream_digest
    ):
        raise CoherentFinancialCaptureError(
            "R1 provenance digest differs from captured PPL population"
        )
    if (
        runtime_provenance.last_source_sequence
        != ppl_observation.last_sequence
    ):
        raise CoherentFinancialCaptureError(
            "R1 provenance sequence differs from captured PPL population"
        )

    open_positions = getattr(projection, "open_positions", None)
    if not isinstance(open_positions, Mapping):
        raise CoherentFinancialCaptureError(
            "captured PPL projection has no open-position mapping"
        )
    valuations = _normalize_valuation_evidence(
        valuation_inputs,
        open_positions=open_positions,
    )
    valuation_digest = _valuation_evidence_digest(valuations)

    capture_id = canonical_identity_hash(
        FIN02_R2_CAPTURE_NAMESPACE,
        {
            "schema_version": FIN02_R2_CAPTURE_SCHEMA_VERSION,
            "captured_at": _decimal_text(observed_at),
            "lock_order": FIN02_R2_LOCK_ORDER,
            "authority_status": authority_status,
            "authority_last_error": last_error,
            "simulator_generation": generation_before,
            "runtime_provenance_id": runtime_provenance.provenance_id,
            "paper_epoch_id": ppl_observation.paper_epoch_id,
            "source_stream_digest": ppl_observation.source_stream_digest,
            "last_source_sequence": ppl_observation.last_sequence,
            "simulator": {
                "source_id": simulator_observation.source_id,
                "provenance": simulator_observation.provenance,
                "cash_available": _decimal_text(
                    simulator_observation.cash_available
                ),
                "capital_reserved": _decimal_text(
                    simulator_observation.capital_reserved
                ),
                "open_position_ids": (
                    None
                    if simulator_observation.open_position_ids is None
                    else list(simulator_observation.open_position_ids)
                ),
                "lifecycle_transitions_in_flight": (
                    simulator_observation.lifecycle_transitions_in_flight
                ),
                "pending_order_count": (
                    simulator_observation.pending_order_count
                ),
            },
            "valuation_evidence_digest": valuation_digest,
        },
    )

    return CoherentFinancialCapture(
        capture_id=capture_id,
        schema_version=FIN02_R2_CAPTURE_SCHEMA_VERSION,
        captured_at=observed_at,
        lock_order=FIN02_R2_LOCK_ORDER,
        authority_status=authority_status,
        authority_last_error=last_error,
        simulator_generation=generation_before,
        runtime_provenance=runtime_provenance,
        ppl_events=events,
        ppl_observation=ppl_observation,
        simulator_observation=simulator_observation,
        valuation_observations=valuations,
        valuation_evidence_digest=valuation_digest,
    )


__all__ = [
    "FIN02_R2_CAPTURE_SCHEMA_VERSION",
    "FIN02_R2_LOCK_ORDER",
    "CoherentFinancialCapture",
    "CoherentFinancialCaptureError",
    "capture_coherent_financial_boundary",
]
