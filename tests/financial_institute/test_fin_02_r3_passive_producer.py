from __future__ import annotations

import json
import threading
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

from financial_institute.models import ValuationObservation
from financial_institute.reconciliation import ReconciliationPolicy
from financial_institute.runtime_provenance import (
    FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA,
    FinancialRuntimeSemanticInputs,
)
from observability.financial_capture import (
    capture_coherent_financial_boundary,
)
from observability.financial_producer import (
    PassiveFinancialProducerStatus,
    build_passive_financial_product,
    run_passive_financial_producer,
)
from observability.operator_api.financial_reconciliation_reader import (
    validate_financial_reconciliation_snapshot,
)
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_opened_event,
)
from paper_trading.paper_portfolio_ledger import project
from paper_trading.ppl_authority_runtime import (
    AuthorityRuntimeStatus,
    AuthorityRuntimeView,
)


EPOCH = "FIN02-R3-EPOCH"
PPL_SHA = "a" * 40
CONFIG_HASH = "b" * 64
FIN02_SHA = "d" * 40
CAPTURED_AT = Decimal("10")
GENERATED_AT = Decimal("11")


def _events():
    return (
        make_epoch_created_event(
            event_id="r3-e1",
            paper_epoch_id=EPOCH,
            sequence=1,
            timestamp=1.0,
            initial_virtual_capital=1000.0,
            code_sha=PPL_SHA,
            config_snapshot_hash=CONFIG_HASH,
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="r3-e2",
            paper_epoch_id=EPOCH,
            sequence=2,
            timestamp=2.0,
            trade_id="R3-T1",
            symbol="BTC/USDT",
            side="LONG",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            decision_id="R3-D1",
            schema_version=2,
            tp_price=110.0,
            sl_price=90.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        ),
    )


class _Runtime:
    def consistent_view(self):
        events = _events()
        return AuthorityRuntimeView(
            status=AuthorityRuntimeStatus.READY,
            paper_epoch_id=EPOCH,
            last_error=None,
            projection=project(events),
            events=events,
        )


def _position():
    return SimpleNamespace(
        pos_id="R3-T1",
        symbol="BTC/USDT",
        qty_usd=10.0,
    )


def _simulator(*, capital=989.99, positions=None):
    return SimpleNamespace(
        _lock=threading.Lock(),
        _lifecycle_authority=SimpleNamespace(
            ppl_is_authoritative=True
        ),
        _authority_runtime=_Runtime(),
        _shadow_observer=None,
        _running=True,
        _capital=capital,
        _positions=(
            {"BTC/USDT": _position()}
            if positions is None
            else positions
        ),
        _orders={},
        _legacy_transitions_in_flight=0,
        _legacy_generation=4,
    )


def _semantic_inputs():
    return FinancialRuntimeSemanticInputs(
        reconciliation_code_sha=FIN02_SHA,
        context_evidence_ref="F00_CONFIG_FREEZE:r3-fixture",
        experiment_id="F00-EXPERIMENT-R3",
        venue="MEXC_SIM",
        market_type="PAPER_LINEAR",
    )


def _valuation():
    return ValuationObservation(
        trade_id="R3-T1",
        symbol="BTC/USDT",
        source_id="R3-MARK",
        venue="MEXC",
        market_type="SPOT",
        price=Decimal("101"),
        source_timestamp=Decimal("9"),
    )


def _capture(*, capital=989.99, positions=None, with_mark=True):
    marks = (_valuation(),) if with_mark else ()
    return capture_coherent_financial_boundary(
        _simulator(capital=capital, positions=positions),
        captured_at=CAPTURED_AT,
        semantic_inputs=_semantic_inputs(),
        valuation_observations=marks,
    )


def _policy():
    return ReconciliationPolicy(
        absolute_tolerance=Decimal("0.000000000001"),
        relative_tolerance=Decimal("0"),
        stale_after_s=Decimal("90"),
    )


def test_r3_builds_fin01_and_fin02_only_from_r2_capture():
    capture = _capture()

    product = build_passive_financial_product(
        capture,
        policy=_policy(),
        generated_at=GENERATED_AT,
        max_mark_age_s=Decimal("30"),
    )

    financial = product.financial_snapshot
    reconciliation = product.reconciliation_snapshot

    assert product.capture_id == capture.capture_id
    assert (
        product.runtime_provenance_id
        == capture.runtime_provenance.provenance_id
    )
    assert financial.paper_epoch_id == EPOCH
    assert financial.source_stream_digest == (
        capture.ppl_observation.source_stream_digest
    )
    assert financial.last_source_sequence == 2
    assert financial.fin_code_sha == FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA
    assert financial.source_code_sha == PPL_SHA
    assert financial.config_hash == CONFIG_HASH
    assert financial.semantic_context_digest == (
        capture.runtime_provenance.semantic_context_digest
    )
    assert reconciliation.reconciliation_code_sha == FIN02_SHA
    assert reconciliation.financial_snapshot_id == financial.snapshot_id
    assert validate_financial_reconciliation_snapshot(product.document)


def test_r3_missing_mark_stays_unavailable_without_fabricated_equity():
    product = build_passive_financial_product(
        _capture(with_mark=False),
        policy=_policy(),
        generated_at=GENERATED_AT,
        max_mark_age_s=Decimal("30"),
    )

    financial = product.financial_snapshot
    assert financial.unrealized_pnl is None
    assert financial.certified_equity is None
    assert [status.value for status in financial.valuation_statuses] == [
        "UNAVAILABLE"
    ]


def test_r3_preserves_simulator_divergence_for_reconciliation():
    product = build_passive_financial_product(
        _capture(capital=777.0, positions={}),
        policy=_policy(),
        generated_at=GENERATED_AT,
        max_mark_age_s=Decimal("30"),
    )

    assert product.reconciliation_snapshot.overall_status.value == "DIVERGENT"
    assert product.document["sources"]["simulator"]["cash_available"] == "777.0"
    assert product.document["sources"]["simulator"]["open_position_ids"] == []


def test_r3_rejects_tampered_r1_semantic_context(tmp_path):
    capture = _capture()
    bad_provenance = replace(
        capture.runtime_provenance,
        semantic_context_digest="f" * 64,
    )
    tampered = replace(
        capture,
        runtime_provenance=bad_provenance,
    )

    result = run_passive_financial_producer(
        tampered,
        policy=_policy(),
        generated_at=GENERATED_AT,
        max_mark_age_s=Decimal("30"),
        artifact_path=tmp_path / "financial.json",
    )

    assert result.status is PassiveFinancialProducerStatus.FAILED
    assert result.product is None
    assert result.error_type == "PassiveFinancialProducerError"


def test_r3_rejects_generation_time_before_capture(tmp_path):
    capture = _capture()
    target = tmp_path / "financial.json"
    target.write_text("last-good", encoding="utf-8")

    result = run_passive_financial_producer(
        capture,
        policy=_policy(),
        generated_at=Decimal("9"),
        max_mark_age_s=Decimal("30"),
        artifact_path=target,
    )

    assert result.status is PassiveFinancialProducerStatus.FAILED
    assert result.product is None
    assert target.read_text(encoding="utf-8") == "last-good"


def test_r3_success_writes_closed_schema_artifact(tmp_path):
    target = tmp_path / "financial.json"
    capture = _capture()

    result = run_passive_financial_producer(
        capture,
        policy=_policy(),
        generated_at=GENERATED_AT,
        max_mark_age_s=Decimal("30"),
        artifact_path=target,
    )

    assert result.status is PassiveFinancialProducerStatus.WRITTEN
    assert result.ok
    assert result.product is not None
    assert result.capture_id == capture.capture_id
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc == result.product.document
    assert validate_financial_reconciliation_snapshot(doc)


def test_r3_write_failure_is_fail_passive(monkeypatch, tmp_path):
    import observability.financial_producer as producer

    capture = _capture()
    target = tmp_path / "financial.json"

    def _boom(*args, **kwargs):
        raise OSError("artifact disk unavailable")

    monkeypatch.setattr(
        producer,
        "write_financial_reconciliation_document",
        _boom,
    )

    result = producer.run_passive_financial_producer(
        capture,
        policy=_policy(),
        generated_at=GENERATED_AT,
        max_mark_age_s=Decimal("30"),
        artifact_path=target,
    )

    assert result.status is PassiveFinancialProducerStatus.FAILED
    assert not result.ok
    assert result.product is None
    assert result.error_type == "OSError"
    assert result.error_message == "artifact disk unavailable"
    assert not target.exists()


def test_r3_product_identity_is_deterministic():
    capture = _capture()
    kwargs = {
        "policy": _policy(),
        "generated_at": GENERATED_AT,
        "max_mark_age_s": Decimal("30"),
    }

    first = build_passive_financial_product(capture, **kwargs)
    second = build_passive_financial_product(capture, **kwargs)

    assert first.product_id == second.product_id
    assert first.financial_snapshot == second.financial_snapshot
    assert first.reconciliation_snapshot == second.reconciliation_snapshot
    assert first.document == second.document


def test_r3_generated_at_changes_reconciliation_and_product_identity():
    capture = _capture()

    first = build_passive_financial_product(
        capture,
        policy=_policy(),
        generated_at=Decimal("11"),
        max_mark_age_s=Decimal("30"),
    )
    second = build_passive_financial_product(
        capture,
        policy=_policy(),
        generated_at=Decimal("12"),
        max_mark_age_s=Decimal("30"),
    )

    assert first.product_id != second.product_id
    assert (
        first.reconciliation_snapshot.reconciliation_id
        != second.reconciliation_snapshot.reconciliation_id
    )
    assert first.financial_snapshot.snapshot_id == (
        second.financial_snapshot.snapshot_id
    )


def test_r3_invalid_artifact_path_is_fail_passive():
    class _InvalidPath:
        pass

    result = run_passive_financial_producer(
        _capture(),
        policy=_policy(),
        generated_at=GENERATED_AT,
        max_mark_age_s=Decimal("30"),
        artifact_path=_InvalidPath(),
    )

    assert result.status is PassiveFinancialProducerStatus.FAILED
    assert not result.ok
    assert result.product is None
    assert result.error_type == "TypeError"


def test_r3_failure_diagnostics_cannot_escape_fail_passive(tmp_path):
    class _HostileCapture:
        @property
        def capture_id(self):
            raise RuntimeError("capture id unavailable")

        @property
        def runtime_provenance(self):
            raise RuntimeError("provenance unavailable")

    result = run_passive_financial_producer(
        _HostileCapture(),
        policy=_policy(),
        generated_at=GENERATED_AT,
        max_mark_age_s=Decimal("30"),
        artifact_path=tmp_path / "financial.json",
    )

    assert result.status is PassiveFinancialProducerStatus.FAILED
    assert result.capture_id == ""
    assert result.runtime_provenance_id == ""
    assert result.error_type == "PassiveFinancialProducerError"


def test_r3_reconciliation_age_uses_generation_time_not_capture_time():
    product = build_passive_financial_product(
        _capture(),
        policy=ReconciliationPolicy(
            absolute_tolerance=Decimal("0.000000000001"),
            relative_tolerance=Decimal("0"),
            stale_after_s=Decimal("90"),
        ),
        generated_at=Decimal("101"),
        max_mark_age_s=Decimal("30"),
    )

    source_records = [
        row
        for row in product.reconciliation_snapshot.records
        if row.source_kind.value in {"PPL", "SIMULATOR"}
    ]
    assert source_records
    assert any(row.freshness.value == "STALE" for row in source_records)
