"""Synthetic source proofs only. Historical bytes never come from production."""
import hashlib
import multiprocessing
from dataclasses import replace

import pytest

from paper_trading.burn_in_admission import BURN_IN_EPOCH_ID, PPLAdmissionClosedError
from paper_trading.durable_event_store import (
    AppendStatus, DurableEventStore, StoreCorruptionError, StoreEpochMismatchError,
    _canonical_line,
)
from paper_trading.ledger_events import make_epoch_created_event, make_position_opened_event
from paper_trading.mexc_simulator import MexcSimulator, OrderStatus
from paper_trading.paper_authority import PaperLifecycleAuthority
from paper_trading.ppl_authority_runtime import (
    CutoverQuiescence, PPLAuthorityRuntime, build_cutover_manifest,
)


def history(root):
    store = DurableEventStore(root)
    birth = make_epoch_created_event(
        event_id="birth", paper_epoch_id=BURN_IN_EPOCH_ID, sequence=1,
        timestamp=10.0, initial_virtual_capital=100.0, code_sha="synthetic",
        config_snapshot_hash="synthetic-config", schema_version=2,
    )
    opened = make_position_opened_event(
        event_id="historical-open", paper_epoch_id=BURN_IN_EPOCH_ID, sequence=2,
        timestamp=20.0, trade_id="old", symbol="BTCUSDT", side="BUY",
        principal=10.0, entry_price=100.0, entry_fee=0.01, schema_version=2,
        tp_price=104.0, sl_price=98.0, timeout_at=30.0, recovery_eligible_until=40.0,
    )
    # Simulate pre-existing baseline history, not a new admitted OPEN.
    store.append(BURN_IN_EPOCH_ID, birth)
    store._epoch_path(BURN_IN_EPOCH_ID).write_bytes(_canonical_line(birth) + _canonical_line(opened))
    return store, opened


def request(store):
    events = store.load_epoch(BURN_IN_EPOCH_ID)
    return dict(
        expected_sequence=events[-1].sequence,
        expected_stream_sha256=hashlib.sha256(b"".join(map(_canonical_line, events))).hexdigest(),
        decision_url="https://github.com/3a7i3/crypto-ia-terminal/issues/286",
        operator="synthetic-operator", decided_at="2026-10-10T00:00:00Z",
    )


def runtime(store):
    manifest = build_cutover_manifest(
        paper_epoch_id=BURN_IN_EPOCH_ID, created_at=10.0, initial_virtual_capital=100.0,
        code_sha="synthetic", config_snapshot_hash="synthetic-config", legacy_log_bytes=b"",
        quiescence=CutoverQuiescence(0, 0, 0, True),
    )
    rt = PPLAuthorityRuntime(manifest=manifest, store=store)
    rt.bind(now=25.0)
    return rt


@pytest.mark.parametrize("receipt", ["missing", "valid", "corrupt", "deleted", "symlink"])
def test_receipt_never_grants_open_and_close_survives_restart(tmp_path, receipt):
    store, opened = history(tmp_path)
    before = store._epoch_path(BURN_IN_EPOCH_ID).read_bytes()
    path = tmp_path / "burn-in-drain-receipt.json"
    if receipt in {"valid", "deleted"}:
        store.seal_burn_in_admission(**request(store))
        if receipt == "deleted":
            path.unlink()
    elif receipt == "corrupt":
        path.write_bytes(b"partial")
    elif receipt == "symlink":
        path.symlink_to("missing")
    fresh = DurableEventStore(tmp_path)
    with pytest.raises(PPLAdmissionClosedError):
        fresh.append(BURN_IN_EPOCH_ID, replace(opened, event_id="new-open", trade_id="new", sequence=3))
    assert fresh.append(BURN_IN_EPOCH_ID, opened).status is AppendStatus.ALREADY_EXISTS
    assert store._epoch_path(BURN_IN_EPOCH_ID).read_bytes() == before
    rt = runtime(fresh)
    result = rt.commit_close(trade_id="old", exit_price=110.0, exit_fee=0.01,
                             closed_at=26.0, decision_id=None)
    assert result.status is AppendStatus.APPENDED
    restarted = runtime(DurableEventStore(tmp_path))
    assert not restarted.consistent_view().projection.open_positions
    assert restarted.consistent_view().projection.realized_pnl == pytest.approx(0.98)


def test_receipt_is_write_once_and_boundary_compare_and_set(tmp_path):
    store, _ = history(tmp_path)
    kwargs = request(store)
    before = store._epoch_path(BURN_IN_EPOCH_ID).read_bytes()
    receipt = store.seal_burn_in_admission(**kwargs)
    assert receipt["state"] == "DRAIN_ONLY"
    assert store.seal_burn_in_admission(**kwargs) == receipt
    with pytest.raises(StoreCorruptionError):
        store.seal_burn_in_admission(**{**kwargs, "operator": "different"})
    with pytest.raises(StoreEpochMismatchError):
        store.seal_burn_in_admission(**{**kwargs, "expected_stream_sha256": "0" * 64})
    assert store._epoch_path(BURN_IN_EPOCH_ID).read_bytes() == before


@pytest.mark.parametrize("override", [
    {"decision_url": "https://example.com/approved"}, {"operator": ""},
    {"decided_at": "now"}, {"expected_sequence": True},
])
def test_invalid_governance_request_has_no_receipt(tmp_path, override):
    store, _ = history(tmp_path)
    with pytest.raises(ValueError):
        store.seal_burn_in_admission(**{**request(store), **override})
    assert not (tmp_path / "burn-in-drain-receipt.json").exists()


def test_receipt_fsync_failure_stays_closed_and_retry_confirms(tmp_path, monkeypatch):
    import paper_trading.durable_event_store as module
    store, opened = history(tmp_path)
    kwargs = request(store)
    original = module.os.fsync
    with monkeypatch.context() as patch:
        patch.setattr(module.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("synthetic fsync")))
        with pytest.raises(OSError, match="synthetic fsync"):
            store.seal_burn_in_admission(**kwargs)
    assert module.os.fsync is original
    with pytest.raises(PPLAdmissionClosedError):
        store.append(BURN_IN_EPOCH_ID, replace(opened, event_id="new-open", trade_id="new", sequence=3))
    assert store.seal_burn_in_admission(**kwargs)["state"] == "DRAIN_ONLY"


def test_simulator_rejects_without_capital_mutation_and_still_closes(tmp_path, monkeypatch):
    store, _ = history(tmp_path)
    rt = runtime(store)
    sim = MexcSimulator(lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
                        authority_runtime=rt)
    monkeypatch.setattr("paper_trading.mexc_simulator.time.time", lambda: 25.0)
    monkeypatch.setattr("paper_trading.mexc_simulator.threading.Thread.start", lambda thread: None)
    sim.start()
    before = rt.consistent_view().events
    capital = sim._capital
    monkeypatch.setattr(sim, "_fetch_price", lambda symbol: 100.0)
    result = sim.place_market_order("ETHUSDT", "BUY", qty_usd=10.0, current_price=100.0)
    assert result.status is OrderStatus.REJECTED
    assert sim._capital == capital
    assert rt.consistent_view().events == before
    sim._close_position("BTCUSDT", 110.0, "TP")
    assert not rt.consistent_view().projection.open_positions


def _race_worker(root, action, start, queue):
    start.wait(10)
    try:
        store = DurableEventStore(root)
        if action == "seal":
            store.seal_burn_in_admission(**request(store))
        elif action == "close":
            runtime(store).commit_close(trade_id="old", exit_price=110.0,
                                       exit_fee=0.01, closed_at=26.0, decision_id=None)
        else:
            events = store.load_epoch(BURN_IN_EPOCH_ID)
            store.append(BURN_IN_EPOCH_ID, replace(events[1], event_id="new-open", trade_id="new", sequence=3))
        queue.put((action, "ok"))
    except (PPLAdmissionClosedError, StoreEpochMismatchError) as exc:
        queue.put((action, type(exc).__name__))


def test_processes_race_seal_open_close(tmp_path):
    history(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    start, queue = ctx.Event(), ctx.Queue()
    processes = [ctx.Process(target=_race_worker, args=(tmp_path, action, start, queue))
                 for action in ("seal", "open", "close")]
    for process in processes:
        process.start()
    start.set()
    results = dict(queue.get(timeout=30) for _ in processes)
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0
    assert results["open"] == "PPLAdmissionClosedError"
    assert results["close"] == "ok"
    assert results["seal"] in {"ok", "StoreEpochMismatchError"}
    assert len(DurableEventStore(tmp_path).load_epoch(BURN_IN_EPOCH_ID)) == 3


def test_other_epoch_is_not_sealed(tmp_path):
    store, opened = history(tmp_path)
    other = "PAPER-STRESS-SYNTHETIC-NOT-ACTIVATED"
    birth = replace(store.load_epoch(BURN_IN_EPOCH_ID)[0], paper_epoch_id=other, event_id="other-birth")
    store.append(other, birth)
    assert store.append(other, replace(opened, paper_epoch_id=other, event_id="other-open")).status is AppendStatus.APPENDED


def test_partial_receipt_is_preserved_and_blocks_publication(tmp_path):
    store, _ = history(tmp_path)
    path = tmp_path / "burn-in-drain-receipt.json"
    path.write_bytes(b'{"schema_version":')
    with pytest.raises(StoreCorruptionError):
        store.seal_burn_in_admission(**request(store))
    assert path.read_bytes() == b'{"schema_version":'


def test_directory_sync_failure_requires_retry(tmp_path, monkeypatch):
    store, _ = history(tmp_path)
    kwargs = request(store)
    with monkeypatch.context() as patch:
        patch.setattr(store, "_fsync_directory", lambda path: (_ for _ in ()).throw(OSError("directory sync")))
        with pytest.raises(OSError, match="directory sync"):
            store.seal_burn_in_admission(**kwargs)
    assert store.seal_burn_in_admission(**kwargs)["state"] == "DRAIN_ONLY"


def test_expired_restart_preserves_unresolved_truth(tmp_path):
    store, _ = history(tmp_path)
    rt = runtime(store)
    state = rt.bind(now=50.0)
    assert not state.open_positions
    assert "old" in state.unresolved_positions
    assert state.unresolved_capital == 10.0
    assert state.realized_pnl == 0.0
    assert len(store.load_epoch(BURN_IN_EPOCH_ID)) == 3
    assert rt.bind(now=51.0) == state


def test_drained_boundary_ppl_fin_replay_is_exact(tmp_path):
    from decimal import Decimal
    from financial_institute.models import FinancialContext, PAPER_LINEAR_FUNDING_EVIDENCE_REF
    from financial_institute.recovery import certify_recovery_replay
    from financial_institute.semantics import EvidenceStatus

    store, _ = history(tmp_path)
    store.seal_burn_in_admission(**request(store))
    runtime(store).commit_close(trade_id="old", exit_price=110.0, exit_fee=0.01,
                               closed_at=26.0, decision_id=None)
    proof = certify_recovery_replay(
        root_dir=tmp_path, paper_epoch_id=BURN_IN_EPOCH_ID,
        context=FinancialContext(fin_code_sha="synthetic-fin",
            funding_status=EvidenceStatus.NOT_APPLICABLE,
            funding_evidence_ref=PAPER_LINEAR_FUNDING_EVIDENCE_REF,
            strategy_id="synthetic", strategy_version="v1", experiment_id="synthetic",
            venue="MEXC_SIM", market_type="PAPER_SWAP_MODEL"),
        observations=[], valuation_as_of=Decimal("27"), max_mark_age_s=Decimal("5"),
        restart_now=27.0,
    )
    assert proof.exact_replay_equivalent
    assert proof.source_event_count == 3

@pytest.mark.parametrize("receipt", ["missing", "valid", "corrupt", "deleted"])
def test_approved_policy_denied_by_ppl_is_not_insufficient_capital(
    tmp_path, monkeypatch, receipt,
):
    import json

    from paper_trading.admission_ledger import reset_admission_ledger_singleton
    from paper_trading.admission_types import (
        AdmissionBlocker, AdmissionDecision, AdmissionLevel, AdmissionVerdict,
    )

    ledger_path = tmp_path / "admission.jsonl"
    monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(ledger_path))
    reset_admission_ledger_singleton()
    try:
        store, _ = history(tmp_path / "ppl")
        path = store._root / "burn-in-drain-receipt.json"
        if receipt in {"valid", "deleted"}:
            store.seal_burn_in_admission(**request(store))
            if receipt == "deleted":
                path.unlink()
        elif receipt == "corrupt":
            path.write_bytes(b"partial")
        rt = runtime(DurableEventStore(store._root))
        sim = MexcSimulator(
            lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
            authority_runtime=rt,
        )
        monkeypatch.setattr("paper_trading.mexc_simulator.time.time", lambda: 25.0)
        monkeypatch.setattr("paper_trading.mexc_simulator.threading.Thread.start", lambda thread: None)
        monkeypatch.setattr(sim, "_fetch_price", lambda symbol: 100.0)
        sim.start()
        before = store._epoch_path(BURN_IN_EPOCH_ID).read_bytes()
        capital = sim._capital
        verdict = AdmissionVerdict(
            decision=AdmissionDecision.APPROVED, level=AdmissionLevel.A,
            n_at_check=1, hard_max_at_check=5, blocker=AdmissionBlocker.NONE,
            reason="synthetic approved policy", checked_by="test",
        )
        result = sim.place_market_order(
            "ETHUSDT", "BUY", qty_usd=10.0, current_price=100.0,
            admission=verdict, cycle_id="synthetic-deny",
        )
        assert result.status is OrderStatus.REJECTED
        assert result.rejection_code == "PPL_ADMISSION_DENIED"
        assert sim._capital == capital
        assert "ETHUSDT" not in sim._positions
        assert store._epoch_path(BURN_IN_EPOCH_ID).read_bytes() == before
        attempt, outcome = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        assert outcome["attempt_id"] == attempt["attempt_id"]
        assert outcome["write_result"] == "REJECTED_ADMISSION"
        assert outcome["anomaly"] == "PPL_ADMISSION_DENIED"
        assert attempt["n_before"] == outcome["n_after"] == 1
        sim._close_position("BTCUSDT", 110.0, "TP")
        assert not rt.consistent_view().projection.open_positions
        assert store._epoch_path(BURN_IN_EPOCH_ID).read_bytes().startswith(before)
    finally:
        reset_admission_ledger_singleton()
