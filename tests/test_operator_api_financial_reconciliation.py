from __future__ import annotations

import json
from decimal import Decimal

from fastapi.testclient import TestClient

from financial_institute.models import (
    PAPER_LINEAR_FUNDING_EVIDENCE_REF,
    FinancialContext,
)
from financial_institute.reconciliation import (
    ReconciliationPolicy,
    SimulatorFinancialObservation,
    ppl_observation_from_events,
    reconcile_financial_snapshot,
)
from financial_institute.semantics import EvidenceStatus
from financial_institute.snapshot import build_financial_snapshot
from observability.financial_reconciliation import (
    build_financial_reconciliation_document,
)
from observability.operator_api import app as api_app
from observability.operator_api.financial_reconciliation_reader import (
    FinancialReconciliationSnapshotReader,
    validate_financial_reconciliation_snapshot,
)
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_opened_event,
)
from paper_trading.paper_portfolio_ledger import project


EPOCH = "FIN02-API-TEST"


def _events():
    return (
        make_epoch_created_event(
            event_id="e1",
            paper_epoch_id=EPOCH,
            sequence=1,
            timestamp=1.0,
            initial_virtual_capital=1000.0,
            code_sha="source-sha",
            config_snapshot_hash="cfg",
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="e2",
            paper_epoch_id=EPOCH,
            sequence=2,
            timestamp=2.0,
            trade_id="trade-1",
            symbol="BTC/USDT",
            side="LONG",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.1,
            decision_id="d1",
            schema_version=2,
            tp_price=110.0,
            sl_price=90.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        ),
    )


def _doc():
    events = _events()
    context = FinancialContext(
        fin_code_sha="fin02",
        funding_status=EvidenceStatus.NOT_APPLICABLE,
        funding_evidence_ref=PAPER_LINEAR_FUNDING_EVIDENCE_REF,
    )
    financial = build_financial_snapshot(
        events,
        context,
        [],
        valuation_as_of=Decimal("10"),
        max_mark_age_s=Decimal("5"),
    )
    ppl = ppl_observation_from_events(events, observed_at=Decimal("10"))
    state = project(events)
    simulator = SimulatorFinancialObservation(
        observed_at=Decimal("10"),
        cash_available=Decimal(str(state.available_cash)),
        capital_reserved=Decimal(str(state.reserved_principal)),
        open_position_ids=tuple(state.open_positions),
        lifecycle_transitions_in_flight=0,
        pending_order_count=0,
    )
    reconciliation = reconcile_financial_snapshot(
        financial,
        ppl,
        reconciliation_code_sha="fin02-reconciliation-code",
        policy=ReconciliationPolicy(
            absolute_tolerance=Decimal("0.000000000001"),
            relative_tolerance=Decimal("0"),
            stale_after_s=Decimal("30"),
        ),
        as_of=Decimal("10"),
        simulator=simulator,
    )
    return build_financial_reconciliation_document(
        financial,
        reconciliation,
        ppl=ppl,
        simulator=simulator,
        generated_at=Decimal("10"),
    )


def test_closed_schema_accepts_real_fin02_producer_document():
    assert validate_financial_reconciliation_snapshot(_doc())


def test_reader_rejects_unknown_top_level_field(tmp_path):
    doc = _doc()
    doc["invented_equity"] = "999999"
    path = tmp_path / "financial.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    result = FinancialReconciliationSnapshotReader(
        path,
        now_fn=lambda: 20.0,
    ).read()
    assert not result.ok
    assert result.error_code == "FINANCIAL_RECONCILIATION_INVALID_SCHEMA"


def test_reader_rejects_non_finite_json_constant(tmp_path):
    path = tmp_path / "financial.json"
    path.write_text('{"schema_version": NaN}', encoding="utf-8")

    result = FinancialReconciliationSnapshotReader(
        path,
        now_fn=lambda: 20.0,
    ).read()
    assert not result.ok
    assert result.error_code == "FINANCIAL_RECONCILIATION_MALFORMED_JSON"


def test_reader_exposes_staleness_without_rewriting_payload(tmp_path):
    doc = _doc()
    path = tmp_path / "financial.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    result = FinancialReconciliationSnapshotReader(
        path,
        stale_after_s=5.0,
        now_fn=lambda: 20.0,
    ).read()

    assert result.ok
    assert result.snapshot == doc
    assert result.snapshot_age_s == 10.0
    assert result.freshness_classification == "STALE"


def test_api_transports_exact_financial_strings_without_recomputation(tmp_path):
    doc = _doc()
    path = tmp_path / "financial.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    api_app.configure_financial_reconciliation_reader(
        path,
        stale_after_s=90.0,
        now_fn=lambda: 20.0,
    )

    response = TestClient(api_app.app).get(
        "/api/operator/v1/financial-reconciliation"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["financial"]["cash_available"] == doc["financial"]["cash_available"]
    assert body["financial"]["certified_equity"] is None
    assert (
        body["reconciliation"]["unreconciled_capital"]
        == doc["reconciliation"]["unreconciled_capital"]
    )
    assert body["snapshot_age_s"] == 10.0
    assert body["freshness_classification"] == "FRESH"


def test_api_missing_artifact_is_honest_503(tmp_path):
    api_app.configure_financial_reconciliation_reader(
        tmp_path / "missing.json",
        now_fn=lambda: 20.0,
    )

    response = TestClient(api_app.app).get(
        "/api/operator/v1/financial-reconciliation"
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == (
        "FINANCIAL_RECONCILIATION_SNAPSHOT_MISSING"
    )
