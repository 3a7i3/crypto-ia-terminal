"""FIN-02R3 — fail-passive Financial Institute producer.

R3 consumes one already-certified R2 coherent capture and composes the existing
FIN-01 snapshot + FIN-02 reconciliation + FIN-02 presentation artifact.

The module has no exchange client, no runtime bootstrap, no wall-clock read and
no execution dependency. All temporal and semantic inputs are explicit.

build_passive_financial_product() is pure and writes nothing.
run_passive_financial_producer() owns only the presentation artifact write and
converts every ordinary failure into a FAILED result instead of propagating it
toward the trading runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional

from financial_institute.models import (
    FinancialContext,
    FinancialSnapshot,
    financial_context_digest,
)
from financial_institute.reconciliation import (
    ExternalFinancialObservation,
    FinancialReconciliationSnapshot,
    ReconciliationPolicy,
    reconcile_financial_snapshot,
)
from financial_institute.semantics import (
    canonical_decimal,
    canonical_identity_hash,
)
from financial_institute.snapshot import build_financial_snapshot
from observability.financial_capture import (
    FIN02_R2_CAPTURE_SCHEMA_VERSION,
    FIN02_R2_LOCK_ORDER,
    CoherentFinancialCapture,
)
from observability.financial_reconciliation import (
    build_financial_reconciliation_document,
    write_financial_reconciliation_document,
)


FIN02_R3_PRODUCT_SCHEMA_VERSION = 1
FIN02_R3_PRODUCT_NAMESPACE = "FIN02_PASSIVE_FINANCIAL_PRODUCT_V1"


class PassiveFinancialProducerError(ValueError):
    """R3 cannot derive a trustworthy passive financial product."""


class PassiveFinancialProducerStatus(str, Enum):
    WRITTEN = "WRITTEN"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PassiveFinancialProduct:
    """Pure R3 product before artifact I/O."""

    product_id: str
    schema_version: int
    capture_id: str
    runtime_provenance_id: str
    generated_at: Decimal
    financial_snapshot: FinancialSnapshot
    reconciliation_snapshot: FinancialReconciliationSnapshot
    document: dict[str, object]


@dataclass(frozen=True)
class PassiveFinancialProducerResult:
    """Fail-passive write outcome suitable for a future runtime caller."""

    status: PassiveFinancialProducerStatus
    capture_id: str
    runtime_provenance_id: str
    artifact_path: str
    product: Optional[PassiveFinancialProduct] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is PassiveFinancialProducerStatus.WRITTEN


def _context_from_capture(
    capture: CoherentFinancialCapture,
) -> FinancialContext:
    provenance = capture.runtime_provenance
    context = FinancialContext(
        fin_code_sha=provenance.fin_code_sha,
        asset=provenance.asset,
        source_authority=provenance.source_authority,
        financial_model=provenance.financial_model,
        funding_status=provenance.funding_status,
        funding_evidence_ref=provenance.funding_evidence_ref,
        strategy_id=provenance.strategy_id,
        strategy_version=provenance.strategy_version,
        experiment_id=provenance.experiment_id,
        venue=provenance.venue,
        market_type=provenance.market_type,
    )
    digest = financial_context_digest(context)
    if digest != provenance.semantic_context_digest:
        raise PassiveFinancialProducerError(
            "R1 semantic context digest does not match reconstructed FIN context"
        )
    return context


def _assert_capture_contract(capture: CoherentFinancialCapture) -> None:
    if not isinstance(capture, CoherentFinancialCapture):
        raise PassiveFinancialProducerError(
            "R3 requires a CoherentFinancialCapture"
        )
    if capture.schema_version != FIN02_R2_CAPTURE_SCHEMA_VERSION:
        raise PassiveFinancialProducerError(
            "R3 requires the certified FIN-02R2 capture schema"
        )
    if capture.lock_order != FIN02_R2_LOCK_ORDER:
        raise PassiveFinancialProducerError(
            "R3 requires the certified FIN-02R2 lock order"
        )

    provenance = capture.runtime_provenance
    ppl = capture.ppl_observation
    if provenance.paper_epoch_id != ppl.paper_epoch_id:
        raise PassiveFinancialProducerError(
            "R1 provenance epoch differs from R2 PPL observation"
        )
    if provenance.source_stream_digest != ppl.source_stream_digest:
        raise PassiveFinancialProducerError(
            "R1 provenance digest differs from R2 PPL observation"
        )
    if provenance.last_source_sequence != ppl.last_sequence:
        raise PassiveFinancialProducerError(
            "R1 provenance sequence differs from R2 PPL observation"
        )


def _assert_financial_binding(
    capture: CoherentFinancialCapture,
    financial: FinancialSnapshot,
) -> None:
    provenance = capture.runtime_provenance
    if financial.paper_epoch_id != provenance.paper_epoch_id:
        raise PassiveFinancialProducerError(
            "FIN snapshot epoch differs from R1/R2 capture"
        )
    if financial.source_stream_digest != provenance.source_stream_digest:
        raise PassiveFinancialProducerError(
            "FIN snapshot source digest differs from R1/R2 capture"
        )
    if financial.last_source_sequence != provenance.last_source_sequence:
        raise PassiveFinancialProducerError(
            "FIN snapshot sequence differs from R1/R2 capture"
        )
    if financial.semantic_context_digest != provenance.semantic_context_digest:
        raise PassiveFinancialProducerError(
            "FIN snapshot semantic context differs from R1 provenance"
        )
    if financial.fin_code_sha != provenance.fin_code_sha:
        raise PassiveFinancialProducerError(
            "FIN snapshot code identity differs from R1 provenance"
        )
    if financial.source_code_sha != provenance.ppl_source_code_sha:
        raise PassiveFinancialProducerError(
            "FIN snapshot PPL source identity differs from R1 provenance"
        )
    if financial.config_hash != provenance.ppl_config_hash:
        raise PassiveFinancialProducerError(
            "FIN snapshot config identity differs from R1 provenance"
        )


def build_passive_financial_product(
    capture: CoherentFinancialCapture,
    *,
    policy: ReconciliationPolicy,
    generated_at: Decimal,
    max_mark_age_s: Decimal,
    external: Optional[ExternalFinancialObservation] = None,
) -> PassiveFinancialProduct:
    """Compose the complete FIN-02 artifact from one immutable R2 capture."""

    _assert_capture_contract(capture)
    generated = canonical_decimal("generated_at", generated_at)
    max_mark_age = canonical_decimal("max_mark_age_s", max_mark_age_s)
    if max_mark_age < 0:
        raise PassiveFinancialProducerError(
            "max_mark_age_s must be >= 0"
        )
    if generated < capture.captured_at:
        raise PassiveFinancialProducerError(
            "generated_at cannot precede the R2 capture"
        )

    context = _context_from_capture(capture)
    financial = build_financial_snapshot(
        capture.ppl_events,
        context,
        capture.valuation_observations,
        valuation_as_of=capture.captured_at,
        max_mark_age_s=max_mark_age,
    )
    _assert_financial_binding(capture, financial)

    reconciliation = reconcile_financial_snapshot(
        financial,
        capture.ppl_observation,
        reconciliation_code_sha=(
            capture.runtime_provenance.reconciliation_code_sha
        ),
        policy=policy,
        as_of=generated,
        simulator=capture.simulator_observation,
        external=external,
    )

    document = build_financial_reconciliation_document(
        financial,
        reconciliation,
        ppl=capture.ppl_observation,
        generated_at=generated,
        simulator=capture.simulator_observation,
        external=external,
    )

    if document["financial_snapshot_id"] != financial.snapshot_id:
        raise PassiveFinancialProducerError(
            "artifact financial snapshot identity mismatch"
        )
    if document["reconciliation_id"] != reconciliation.reconciliation_id:
        raise PassiveFinancialProducerError(
            "artifact reconciliation identity mismatch"
        )
    if (
        document["source_stream_digest"]
        != capture.runtime_provenance.source_stream_digest
    ):
        raise PassiveFinancialProducerError(
            "artifact source digest differs from R1/R2 capture"
        )

    product_id = canonical_identity_hash(
        FIN02_R3_PRODUCT_NAMESPACE,
        {
            "schema_version": FIN02_R3_PRODUCT_SCHEMA_VERSION,
            "capture_id": capture.capture_id,
            "runtime_provenance_id": (
                capture.runtime_provenance.provenance_id
            ),
            "financial_snapshot_id": financial.snapshot_id,
            "reconciliation_id": reconciliation.reconciliation_id,
            "generated_at": format(generated, "f"),
            "max_mark_age_s": format(max_mark_age, "f"),
            "absolute_tolerance": format(
                policy.absolute_tolerance,
                "f",
            ),
            "relative_tolerance": format(
                policy.relative_tolerance,
                "f",
            ),
            "stale_after_s": format(policy.stale_after_s, "f"),
        },
    )

    return PassiveFinancialProduct(
        product_id=product_id,
        schema_version=FIN02_R3_PRODUCT_SCHEMA_VERSION,
        capture_id=capture.capture_id,
        runtime_provenance_id=capture.runtime_provenance.provenance_id,
        generated_at=generated,
        financial_snapshot=financial,
        reconciliation_snapshot=reconciliation,
        document=document,
    )


def run_passive_financial_producer(
    capture: CoherentFinancialCapture,
    *,
    policy: ReconciliationPolicy,
    generated_at: Decimal,
    max_mark_age_s: Decimal,
    artifact_path: Path,
    external: Optional[ExternalFinancialObservation] = None,
) -> PassiveFinancialProducerResult:
    """Build and atomically publish one FIN-02 artifact, never raising.

    The only owned mutation is replacement of artifact_path by the existing
    atomic FIN-02 presentation writer. PPL, FIN ledger, simulator, exchange,
    strategy, risk, sizing and execution state are never written here.
    """

    path = Path(artifact_path)
    capture_id = str(getattr(capture, "capture_id", "") or "")
    provenance = getattr(capture, "runtime_provenance", None)
    provenance_id = str(
        getattr(provenance, "provenance_id", "") or ""
    )

    try:
        product = build_passive_financial_product(
            capture,
            policy=policy,
            generated_at=generated_at,
            max_mark_age_s=max_mark_age_s,
            external=external,
        )
        write_financial_reconciliation_document(
            product.document,
            path=path,
        )
    except Exception as exc:
        return PassiveFinancialProducerResult(
            status=PassiveFinancialProducerStatus.FAILED,
            capture_id=capture_id,
            runtime_provenance_id=provenance_id,
            artifact_path=str(path),
            product=None,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    return PassiveFinancialProducerResult(
        status=PassiveFinancialProducerStatus.WRITTEN,
        capture_id=product.capture_id,
        runtime_provenance_id=product.runtime_provenance_id,
        artifact_path=str(path),
        product=product,
    )


__all__ = [
    "FIN02_R3_PRODUCT_SCHEMA_VERSION",
    "PassiveFinancialProduct",
    "PassiveFinancialProducerError",
    "PassiveFinancialProducerResult",
    "PassiveFinancialProducerStatus",
    "build_passive_financial_product",
    "run_passive_financial_producer",
]
