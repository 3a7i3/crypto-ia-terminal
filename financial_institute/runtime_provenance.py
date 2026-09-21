"""FIN-02R1 — explicit runtime financial provenance contract.

This module does not read environment variables, git state, files, clocks,
exchange clients, simulator state or mutable runtime globals.  It binds
already-authoritative PPL lifecycle facts to explicit Financial Institute
semantic inputs.

The three source identities are deliberately separate:

- PPL/F00 source identity: carried by the authoritative PPL EPOCH_CREATED event.
- FIN-01 implementation identity: the exact certified FIN-01 source HEAD.
- FIN-02 reconciliation identity: supplied explicitly by the reconciliation
  producer that is actually executing.

None may be silently substituted for another.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from financial_institute.models import (
    PAPER_LINEAR_FUNDING_EVIDENCE_REF,
    FinancialContext,
    financial_context_digest,
)
from financial_institute.ppl_adapter import ppl_stream_digest
from financial_institute.semantics import (
    EvidenceStatus,
    FinancialModel,
    canonical_identity_hash,
)
from paper_trading.ledger_events import LedgerEvent
from paper_trading.paper_portfolio_ledger import project


FIN02_RUNTIME_PROVENANCE_SCHEMA_VERSION = 1
FIN02_RUNTIME_PROVENANCE_NAMESPACE = "FIN02_RUNTIME_PROVENANCE_V1"

# Exact source identity certified in #245 and reused by the deterministic
# runtime replay proof in #246.  This is the FIN-01 semantic implementation
# identity; it is intentionally NOT the active F00/PPL source SHA.
FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA = (
    "c639ac397122929769be2a1ce7654e3a1bc24cfe"
)
FIN01_PAPER_V1_CERTIFIED_VERDICT = (
    "FIN_01_PAPER_FINANCIAL_INSTITUTE_SOURCE_CERTIFIED"
)


class FinancialRuntimeProvenanceError(ValueError):
    """Runtime provenance is absent, ambiguous or outside certified FIN-01 v1."""


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FinancialRuntimeProvenanceError(
            f"{name} must be an explicit non-empty string"
        )
    return value.strip()


@dataclass(frozen=True)
class FinancialRuntimeSemanticInputs:
    """Explicit semantic inputs that PPL lifecycle events do not carry.

    experiment_id, venue and market_type are mandatory in FIN-02 runtime
    provenance.  They must come from an explicit governed source; this contract
    never infers them from an epoch id, a symbol or the active process.
    """

    reconciliation_code_sha: str
    experiment_id: str
    venue: str
    market_type: str
    strategy_id: Optional[str] = None
    strategy_version: Optional[str] = None
    fin_code_sha: str = FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA
    asset: str = "USDT"
    source_authority: str = "PPL_AUTHORITY"
    financial_model: FinancialModel = FinancialModel.PAPER_LINEAR_PRINCIPAL_V1
    funding_status: EvidenceStatus = EvidenceStatus.NOT_APPLICABLE
    funding_evidence_ref: Optional[str] = PAPER_LINEAR_FUNDING_EVIDENCE_REF

    def __post_init__(self) -> None:
        for name in (
            "reconciliation_code_sha",
            "experiment_id",
            "venue",
            "market_type",
            "fin_code_sha",
            "asset",
            "source_authority",
        ):
            object.__setattr__(
                self,
                name,
                _require_text(name, getattr(self, name)),
            )

        if self.fin_code_sha != FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA:
            raise FinancialRuntimeProvenanceError(
                "FIN-02R1 PAPER v1 requires the exact certified FIN-01 "
                f"source identity {FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA}"
            )
        if self.reconciliation_code_sha == self.fin_code_sha:
            raise FinancialRuntimeProvenanceError(
                "reconciliation_code_sha must identify FIN-02 separately "
                "from the certified FIN-01 implementation"
            )
        if self.asset != "USDT":
            raise FinancialRuntimeProvenanceError(
                "FIN-02R1 PAPER v1 supports asset=USDT only"
            )
        if self.source_authority != "PPL_AUTHORITY":
            raise FinancialRuntimeProvenanceError(
                "FIN-02R1 requires source_authority=PPL_AUTHORITY"
            )
        if self.financial_model is not FinancialModel.PAPER_LINEAR_PRINCIPAL_V1:
            raise FinancialRuntimeProvenanceError(
                "FIN-02R1 supports PAPER_LINEAR_PRINCIPAL_V1 only"
            )
        if self.funding_status not in {
            EvidenceStatus.NOT_APPLICABLE,
            EvidenceStatus.UNRESOLVED,
        }:
            raise FinancialRuntimeProvenanceError(
                "FIN-02R1 funding evidence must be NOT_APPLICABLE or UNRESOLVED"
            )
        if self.funding_status is EvidenceStatus.NOT_APPLICABLE:
            if self.funding_evidence_ref != PAPER_LINEAR_FUNDING_EVIDENCE_REF:
                raise FinancialRuntimeProvenanceError(
                    "NOT_APPLICABLE funding requires the certified "
                    "PAPER_LINEAR funding evidence reference"
                )
        elif self.funding_evidence_ref is not None:
            _require_text("funding_evidence_ref", self.funding_evidence_ref)

        for name in ("strategy_id", "strategy_version"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _require_text(name, value))
        if self.strategy_version and not self.strategy_id:
            raise FinancialRuntimeProvenanceError(
                "strategy_version requires an explicit strategy_id"
            )

    def financial_context(self) -> FinancialContext:
        """Materialize the exact FIN-01 context; no additional inference."""

        return FinancialContext(
            fin_code_sha=self.fin_code_sha,
            asset=self.asset,
            source_authority=self.source_authority,
            financial_model=self.financial_model,
            funding_status=self.funding_status,
            funding_evidence_ref=self.funding_evidence_ref,
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            experiment_id=self.experiment_id,
            venue=self.venue,
            market_type=self.market_type,
        )


@dataclass(frozen=True)
class FinancialRuntimeProvenance:
    """Immutable binding between one PPL population and FIN-02 semantics."""

    provenance_id: str
    schema_version: int
    paper_epoch_id: str
    source_stream_digest: str
    last_source_sequence: int
    ppl_source_code_sha: str
    ppl_config_hash: str
    fin_code_sha: str
    fin_certified_verdict: str
    reconciliation_code_sha: str
    semantic_context_digest: str
    asset: str
    source_authority: str
    financial_model: FinancialModel
    funding_status: EvidenceStatus
    funding_evidence_ref: Optional[str]
    experiment_id: str
    strategy_id: Optional[str]
    strategy_version: Optional[str]
    venue: str
    market_type: str

    def as_dict(self) -> dict[str, object]:
        return {
            "provenance_id": self.provenance_id,
            "schema_version": self.schema_version,
            "paper_epoch_id": self.paper_epoch_id,
            "source_stream_digest": self.source_stream_digest,
            "last_source_sequence": self.last_source_sequence,
            "ppl_source_code_sha": self.ppl_source_code_sha,
            "ppl_config_hash": self.ppl_config_hash,
            "fin_code_sha": self.fin_code_sha,
            "fin_certified_verdict": self.fin_certified_verdict,
            "reconciliation_code_sha": self.reconciliation_code_sha,
            "semantic_context_digest": self.semantic_context_digest,
            "asset": self.asset,
            "source_authority": self.source_authority,
            "financial_model": self.financial_model.value,
            "funding_status": self.funding_status.value,
            "funding_evidence_ref": self.funding_evidence_ref,
            "experiment_id": self.experiment_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "venue": self.venue,
            "market_type": self.market_type,
        }


def bind_financial_runtime_provenance(
    events: Sequence[LedgerEvent],
    semantic_inputs: FinancialRuntimeSemanticInputs,
) -> FinancialRuntimeProvenance:
    """Bind explicit FIN semantics to one authoritative durable PPL stream.

    PPL-owned identity fields are read only from the projected authoritative
    event population.  Caller-supplied duplicate copies of epoch/source/config
    identity are deliberately not accepted, preventing two competing sources
    of truth.
    """

    if not events:
        raise FinancialRuntimeProvenanceError(
            "authoritative PPL event stream must not be empty"
        )

    state = project(events)
    if state.epoch is None:
        raise FinancialRuntimeProvenanceError(
            "authoritative PPL stream has no EPOCH_CREATED fact"
        )

    context = semantic_inputs.financial_context()
    context_digest = financial_context_digest(context)
    stream_digest = ppl_stream_digest(events)

    identity_fields = {
        "schema_version": FIN02_RUNTIME_PROVENANCE_SCHEMA_VERSION,
        "paper_epoch_id": state.paper_epoch_id,
        "source_stream_digest": stream_digest,
        "last_source_sequence": state.last_sequence,
        "ppl_source_code_sha": state.epoch.code_sha,
        "ppl_config_hash": state.epoch.config_snapshot_hash,
        "fin_code_sha": semantic_inputs.fin_code_sha,
        "fin_certified_verdict": FIN01_PAPER_V1_CERTIFIED_VERDICT,
        "reconciliation_code_sha": semantic_inputs.reconciliation_code_sha,
        "semantic_context_digest": context_digest,
        "asset": semantic_inputs.asset,
        "source_authority": semantic_inputs.source_authority,
        "financial_model": semantic_inputs.financial_model.value,
        "funding_status": semantic_inputs.funding_status.value,
        "funding_evidence_ref": semantic_inputs.funding_evidence_ref,
        "experiment_id": semantic_inputs.experiment_id,
        "strategy_id": semantic_inputs.strategy_id,
        "strategy_version": semantic_inputs.strategy_version,
        "venue": semantic_inputs.venue,
        "market_type": semantic_inputs.market_type,
    }
    provenance_id = canonical_identity_hash(
        FIN02_RUNTIME_PROVENANCE_NAMESPACE,
        identity_fields,
    )

    return FinancialRuntimeProvenance(
        provenance_id=provenance_id,
        schema_version=FIN02_RUNTIME_PROVENANCE_SCHEMA_VERSION,
        paper_epoch_id=state.paper_epoch_id,
        source_stream_digest=stream_digest,
        last_source_sequence=state.last_sequence,
        ppl_source_code_sha=state.epoch.code_sha,
        ppl_config_hash=state.epoch.config_snapshot_hash,
        fin_code_sha=semantic_inputs.fin_code_sha,
        fin_certified_verdict=FIN01_PAPER_V1_CERTIFIED_VERDICT,
        reconciliation_code_sha=semantic_inputs.reconciliation_code_sha,
        semantic_context_digest=context_digest,
        asset=semantic_inputs.asset,
        source_authority=semantic_inputs.source_authority,
        financial_model=semantic_inputs.financial_model,
        funding_status=semantic_inputs.funding_status,
        funding_evidence_ref=semantic_inputs.funding_evidence_ref,
        experiment_id=semantic_inputs.experiment_id,
        strategy_id=semantic_inputs.strategy_id,
        strategy_version=semantic_inputs.strategy_version,
        venue=semantic_inputs.venue,
        market_type=semantic_inputs.market_type,
    )


__all__ = [
    "FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA",
    "FIN01_PAPER_V1_CERTIFIED_VERDICT",
    "FIN02_RUNTIME_PROVENANCE_SCHEMA_VERSION",
    "FinancialRuntimeProvenance",
    "FinancialRuntimeProvenanceError",
    "FinancialRuntimeSemanticInputs",
    "bind_financial_runtime_provenance",
]
