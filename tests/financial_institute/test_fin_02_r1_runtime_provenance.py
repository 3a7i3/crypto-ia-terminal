from __future__ import annotations

from dataclasses import replace

import pytest

from financial_institute.models import (
    PAPER_LINEAR_FUNDING_EVIDENCE_REF,
    financial_context_digest,
)
from financial_institute.runtime_provenance import (
    FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA,
    FIN01_PAPER_V1_CERTIFIED_VERDICT,
    FinancialRuntimeProvenanceError,
    FinancialRuntimeSemanticInputs,
    bind_financial_runtime_provenance,
)
from financial_institute.semantics import EvidenceStatus
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_opened_event,
)


EPOCH = "FIN02-R1-EPOCH"
PPL_SOURCE_SHA = "a" * 40
CONFIG_HASH = "b" * 64
FIN02_SHA = "d" * 40


def _events():
    return (
        make_epoch_created_event(
            event_id="r1-e1",
            paper_epoch_id=EPOCH,
            sequence=1,
            timestamp=1.0,
            initial_virtual_capital=1000.0,
            code_sha=PPL_SOURCE_SHA,
            config_snapshot_hash=CONFIG_HASH,
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="r1-e2",
            paper_epoch_id=EPOCH,
            sequence=2,
            timestamp=2.0,
            trade_id="R1-T1",
            symbol="BTC/USDT",
            side="LONG",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            decision_id="R1-D1",
            schema_version=2,
            tp_price=110.0,
            sl_price=90.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        ),
    )


def _inputs(**overrides):
    values = {
        "reconciliation_code_sha": FIN02_SHA,
        "context_evidence_ref": "F00_CONFIG_FREEZE:fixture-r1",
        "experiment_id": "F00-EXPERIMENT-R1",
        "venue": "MEXC_SIM",
        "market_type": "PAPER_LINEAR",
    }
    values.update(overrides)
    return FinancialRuntimeSemanticInputs(**values)


def test_r1_binds_three_source_identities_without_substitution():
    provenance = bind_financial_runtime_provenance(_events(), _inputs())

    assert provenance.paper_epoch_id == EPOCH
    assert provenance.ppl_source_code_sha == PPL_SOURCE_SHA
    assert provenance.ppl_config_hash == CONFIG_HASH
    assert provenance.fin_code_sha == FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA
    assert provenance.fin_certified_verdict == FIN01_PAPER_V1_CERTIFIED_VERDICT
    assert provenance.reconciliation_code_sha == FIN02_SHA

    assert provenance.ppl_source_code_sha != provenance.fin_code_sha
    assert provenance.reconciliation_code_sha != provenance.fin_code_sha


def test_r1_context_digest_is_exact_fin01_semantic_context():
    inputs = _inputs(
        strategy_id="strategy-alpha",
        strategy_version="v1",
    )
    provenance = bind_financial_runtime_provenance(_events(), inputs)

    assert provenance.semantic_context_digest == financial_context_digest(
        inputs.financial_context()
    )
    assert provenance.funding_status is EvidenceStatus.NOT_APPLICABLE
    assert (
        provenance.funding_evidence_ref
        == PAPER_LINEAR_FUNDING_EVIDENCE_REF
    )


@pytest.mark.parametrize(
    "field",
    [
        "context_evidence_ref",
        "experiment_id",
        "venue",
        "market_type",
        "reconciliation_code_sha",
    ],
)
def test_r1_mandatory_runtime_semantics_fail_closed(field):
    with pytest.raises(FinancialRuntimeProvenanceError):
        _inputs(**{field: ""})


def test_r1_rejects_uncertified_fin_source_identity():
    with pytest.raises(
        FinancialRuntimeProvenanceError,
        match="exact certified FIN-01 source identity",
    ):
        _inputs(fin_code_sha="e" * 40)


def test_r1_rejects_fin02_identity_aliasing_fin01_identity():
    with pytest.raises(
        FinancialRuntimeProvenanceError,
        match="identify FIN-02 separately",
    ):
        _inputs(
            reconciliation_code_sha=FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA
        )


def test_r1_unresolved_funding_remains_explicit():
    inputs = _inputs(
        funding_status=EvidenceStatus.UNRESOLVED,
        funding_evidence_ref=None,
    )
    provenance = bind_financial_runtime_provenance(_events(), inputs)

    assert provenance.funding_status is EvidenceStatus.UNRESOLVED
    assert provenance.funding_evidence_ref is None


def test_r1_provenance_identity_is_deterministic_and_semantically_bound():
    events = _events()
    base = _inputs()

    first = bind_financial_runtime_provenance(events, base)
    second = bind_financial_runtime_provenance(events, base)
    changed_experiment = bind_financial_runtime_provenance(
        events,
        replace(base, experiment_id="F00-EXPERIMENT-OTHER"),
    )
    changed_reconciliation_code = bind_financial_runtime_provenance(
        events,
        replace(base, reconciliation_code_sha="f" * 40),
    )
    changed_context_evidence = bind_financial_runtime_provenance(
        events,
        replace(base, context_evidence_ref="F00_CONFIG_FREEZE:other"),
    )

    assert first == second
    assert first.provenance_id == second.provenance_id
    assert changed_experiment.provenance_id != first.provenance_id
    assert changed_experiment.semantic_context_digest != first.semantic_context_digest
    assert changed_reconciliation_code.provenance_id != first.provenance_id
    assert (
        changed_reconciliation_code.semantic_context_digest
        == first.semantic_context_digest
    )
    assert changed_context_evidence.provenance_id != first.provenance_id
    assert (
        changed_context_evidence.semantic_context_digest
        == first.semantic_context_digest
    )


def test_r1_ppl_population_change_changes_binding_not_fin_semantics():
    one_event = _events()[:1]
    two_events = _events()
    inputs = _inputs()

    before = bind_financial_runtime_provenance(one_event, inputs)
    after = bind_financial_runtime_provenance(two_events, inputs)

    assert before.paper_epoch_id == after.paper_epoch_id
    assert before.ppl_source_code_sha == after.ppl_source_code_sha
    assert before.ppl_config_hash == after.ppl_config_hash
    assert before.last_source_sequence == 1
    assert after.last_source_sequence == 2
    assert before.source_stream_digest != after.source_stream_digest
    assert before.provenance_id != after.provenance_id
    assert before.semantic_context_digest == after.semantic_context_digest


def test_r1_strategy_version_cannot_exist_without_strategy_identity():
    with pytest.raises(
        FinancialRuntimeProvenanceError,
        match="strategy_version requires",
    ):
        _inputs(strategy_version="v1")


def test_r1_binding_requires_authoritative_epoch_fact():
    with pytest.raises(
        FinancialRuntimeProvenanceError,
        match="must not be empty",
    ):
        bind_financial_runtime_provenance((), _inputs())
