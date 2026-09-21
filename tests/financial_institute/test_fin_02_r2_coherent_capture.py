from __future__ import annotations

import threading
from decimal import Decimal
from types import SimpleNamespace

import pytest

from financial_institute.models import ValuationObservation
from financial_institute.runtime_provenance import (
    FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA,
    FinancialRuntimeSemanticInputs,
)
from observability.financial_capture import (
    FIN02_R2_LOCK_ORDER,
    CoherentFinancialCaptureError,
    capture_coherent_financial_boundary,
)
from observability.financial_reconciliation import (
    capture_simulator_observation,
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


EPOCH = "FIN02-R2-EPOCH"
PPL_SHA = "a" * 40
CONFIG_HASH = "b" * 64
FIN02_SHA = "d" * 40


def _events():
    return (
        make_epoch_created_event(
            event_id="r2-e1",
            paper_epoch_id=EPOCH,
            sequence=1,
            timestamp=1.0,
            initial_virtual_capital=1000.0,
            code_sha=PPL_SHA,
            config_snapshot_hash=CONFIG_HASH,
            schema_version=2,
        ),
        make_position_opened_event(
            event_id="r2-e2",
            paper_epoch_id=EPOCH,
            sequence=2,
            timestamp=2.0,
            trade_id="R2-T1",
            symbol="BTC/USDT",
            side="LONG",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            decision_id="R2-D1",
            schema_version=2,
            tp_price=110.0,
            sl_price=90.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        ),
    )


def _view(*, status=AuthorityRuntimeStatus.READY):
    events = _events()
    return AuthorityRuntimeView(
        status=status,
        paper_epoch_id=EPOCH,
        last_error=None,
        projection=project(events),
        events=events,
    )


class _Runtime:
    def __init__(self, view):
        self.view = view
        self.consistent_view_calls = 0

    def consistent_view(self):
        self.consistent_view_calls += 1
        return self.view


class _BlockingRuntime(_Runtime):
    def __init__(self, view, entered, release):
        super().__init__(view)
        self.entered = entered
        self.release = release

    def consistent_view(self):
        self.consistent_view_calls += 1
        self.entered.set()
        assert self.release.wait(timeout=2)
        return self.view


def _position():
    return SimpleNamespace(
        pos_id="R2-T1",
        symbol="BTC/USDT",
        qty_usd=10.0,
    )


def _simulator(
    runtime,
    *,
    running=True,
    capital=989.99,
    positions=None,
    transitions=0,
    generation=7,
    ppl_authority=True,
):
    return SimpleNamespace(
        _lock=threading.Lock(),
        _lifecycle_authority=SimpleNamespace(
            ppl_is_authoritative=ppl_authority
        ),
        _authority_runtime=runtime,
        _shadow_observer=None,
        _running=running,
        _capital=capital,
        _positions=(
            {"BTC/USDT": _position()}
            if positions is None
            else positions
        ),
        _orders={},
        _legacy_transitions_in_flight=transitions,
        _legacy_generation=generation,
    )


def _semantic_inputs():
    return FinancialRuntimeSemanticInputs(
        reconciliation_code_sha=FIN02_SHA,
        context_evidence_ref="F00_CONFIG_FREEZE:r2-fixture",
        experiment_id="F00-EXPERIMENT-R2",
        venue="MEXC_SIM",
        market_type="PAPER_LINEAR",
    )


def _valuation(price="101", timestamp="9"):
    return ValuationObservation(
        trade_id="R2-T1",
        symbol="BTC/USDT",
        source_id="R2-MARK",
        venue="MEXC",
        market_type="SPOT",
        price=Decimal(price),
        source_timestamp=Decimal(timestamp),
    )


def test_r2_binds_simulator_owned_authority_and_r1_provenance():
    runtime = _Runtime(_view())
    simulator = _simulator(runtime)

    capture = capture_coherent_financial_boundary(
        simulator,
        captured_at=Decimal("10"),
        semantic_inputs=_semantic_inputs(),
        valuation_observations=(_valuation(),),
    )

    assert runtime.consistent_view_calls == 1
    assert capture.lock_order == FIN02_R2_LOCK_ORDER
    assert capture.ppl_observation.paper_epoch_id == EPOCH
    assert capture.ppl_observation.last_sequence == 2
    assert capture.runtime_provenance.paper_epoch_id == EPOCH
    assert capture.runtime_provenance.ppl_source_code_sha == PPL_SHA
    assert (
        capture.runtime_provenance.fin_code_sha
        == FIN01_PAPER_V1_CERTIFIED_SOURCE_SHA
    )
    assert capture.runtime_provenance.reconciliation_code_sha == FIN02_SHA
    assert capture.simulator_generation == 7
    assert capture.simulator_observation.cash_available == Decimal("989.99")
    assert capture.simulator_observation.open_position_ids == ("R2-T1",)
    assert len(capture.valuation_observations) == 1


def test_r2_holds_sim_lock_across_ppl_and_simulator_reads():
    entered = threading.Event()
    release = threading.Event()
    mutation_attempted = threading.Event()
    mutation_acquired = threading.Event()
    runtime = _BlockingRuntime(_view(), entered, release)
    simulator = _simulator(runtime, capital=989.99)
    result = {}
    errors = []

    def capture_worker():
        try:
            result["capture"] = capture_coherent_financial_boundary(
                simulator,
                captured_at=Decimal("10"),
                semantic_inputs=_semantic_inputs(),
            )
        except Exception as exc:  # pragma: no cover - diagnostic path
            errors.append(exc)

    def mutation_worker():
        mutation_attempted.set()
        with simulator._lock:
            mutation_acquired.set()
            simulator._capital = 123.0
            simulator._legacy_generation += 1

    capture_thread = threading.Thread(target=capture_worker)
    capture_thread.start()
    assert entered.wait(timeout=2)

    mutation_thread = threading.Thread(target=mutation_worker)
    mutation_thread.start()
    assert mutation_attempted.wait(timeout=2)
    assert not mutation_acquired.is_set()

    release.set()
    capture_thread.join(timeout=2)
    mutation_thread.join(timeout=2)

    assert not errors
    assert not capture_thread.is_alive()
    assert not mutation_thread.is_alive()
    assert mutation_acquired.is_set()
    assert (
        result["capture"].simulator_observation.cash_available
        == Decimal("989.99")
    )
    assert simulator._capital == 123.0


def test_r2_preserves_independent_simulator_divergence():
    runtime = _Runtime(_view())
    simulator = _simulator(
        runtime,
        capital=777.0,
        positions={},
    )

    capture = capture_coherent_financial_boundary(
        simulator,
        captured_at=Decimal("10"),
        semantic_inputs=_semantic_inputs(),
    )

    assert capture.ppl_observation.open_position_ids == ("R2-T1",)
    assert capture.simulator_observation.open_position_ids == ()
    assert capture.simulator_observation.cash_available == Decimal("777.0")


def test_r2_missing_valuation_evidence_remains_explicitly_empty():
    runtime = _Runtime(_view())
    simulator = _simulator(runtime)

    first = capture_coherent_financial_boundary(
        simulator,
        captured_at=Decimal("10"),
        semantic_inputs=_semantic_inputs(),
    )
    second = capture_coherent_financial_boundary(
        simulator,
        captured_at=Decimal("10"),
        semantic_inputs=_semantic_inputs(),
    )

    assert first.valuation_observations == ()
    assert first.valuation_evidence_digest == second.valuation_evidence_digest
    assert first.capture_id == second.capture_id


def test_r2_valuation_evidence_changes_capture_identity():
    runtime = _Runtime(_view())
    simulator = _simulator(runtime)

    first = capture_coherent_financial_boundary(
        simulator,
        captured_at=Decimal("10"),
        semantic_inputs=_semantic_inputs(),
        valuation_observations=(_valuation("101"),),
    )
    second = capture_coherent_financial_boundary(
        simulator,
        captured_at=Decimal("10"),
        semantic_inputs=_semantic_inputs(),
        valuation_observations=(_valuation("102"),),
    )

    assert first.valuation_evidence_digest != second.valuation_evidence_digest
    assert first.capture_id != second.capture_id


def test_r2_rejects_valuation_for_non_open_trade():
    runtime = _Runtime(_view())
    simulator = _simulator(runtime)
    wrong = ValuationObservation(
        trade_id="CLOSED-T1",
        symbol="BTC/USDT",
        source_id="R2-MARK",
        venue="MEXC",
        market_type="SPOT",
        price=Decimal("101"),
        source_timestamp=Decimal("9"),
    )

    with pytest.raises(
        CoherentFinancialCaptureError,
        match="not open",
    ):
        capture_coherent_financial_boundary(
            simulator,
            captured_at=Decimal("10"),
            semantic_inputs=_semantic_inputs(),
            valuation_observations=(wrong,),
        )


@pytest.mark.parametrize(
    "simulator",
    [
        _simulator(_Runtime(_view()), running=False),
        _simulator(_Runtime(_view()), ppl_authority=False),
        _simulator(_Runtime(_view()), transitions=1),
    ],
)
def test_r2_fails_closed_on_non_certifiable_runtime_boundary(simulator):
    with pytest.raises(CoherentFinancialCaptureError):
        capture_coherent_financial_boundary(
            simulator,
            captured_at=Decimal("10"),
            semantic_inputs=_semantic_inputs(),
        )


def test_r2_rejects_degraded_authority_runtime():
    runtime = _Runtime(_view(status=AuthorityRuntimeStatus.DEGRADED))
    simulator = _simulator(runtime)

    with pytest.raises(
        CoherentFinancialCaptureError,
        match="not READY",
    ):
        capture_coherent_financial_boundary(
            simulator,
            captured_at=Decimal("10"),
            semantic_inputs=_semantic_inputs(),
        )


def test_r2_refactor_preserves_public_simulator_capture_contract():
    runtime = _Runtime(_view())
    simulator = _simulator(runtime)

    public = capture_simulator_observation(
        simulator,
        observed_at=Decimal("10"),
    )
    coherent = capture_coherent_financial_boundary(
        simulator,
        captured_at=Decimal("10"),
        semantic_inputs=_semantic_inputs(),
    )

    assert public == coherent.simulator_observation


def test_r2_rejects_projection_event_population_mismatch():
    events = _events()
    mismatched_view = AuthorityRuntimeView(
        status=AuthorityRuntimeStatus.READY,
        paper_epoch_id=EPOCH,
        last_error=None,
        projection=project(events[:1]),
        events=events,
    )
    runtime = _Runtime(mismatched_view)
    simulator = _simulator(runtime)

    with pytest.raises(
        CoherentFinancialCaptureError,
        match="projection differs",
    ):
        capture_coherent_financial_boundary(
            simulator,
            captured_at=Decimal("10"),
            semantic_inputs=_semantic_inputs(),
        )


def test_r2_rejects_shadow_observer_on_authoritative_simulator():
    runtime = _Runtime(_view())
    simulator = _simulator(runtime)
    simulator._shadow_observer = object()

    with pytest.raises(
        CoherentFinancialCaptureError,
        match="forbids an attached SHADOW observer",
    ):
        capture_coherent_financial_boundary(
            simulator,
            captured_at=Decimal("10"),
            semantic_inputs=_semantic_inputs(),
        )
