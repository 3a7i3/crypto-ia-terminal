from __future__ import annotations

import json

import pytest

from observability.operator_api.ppl_comparison_reader import (
    PplComparisonSnapshotReader,
)
from observability.ppl_comparison import write_ppl_comparison_snapshot
from paper_trading.durable_event_store import AppendStatus, DurableEventStore
from paper_trading.mexc_simulator import (
    MexcOrder,
    MexcSimulator,
    OrderSide,
    OrderStatus,
    OrderType,
)
from paper_trading.paper_authority import PaperLifecycleAuthority
from paper_trading.paper_portfolio_ledger import NegativeCashError
from paper_trading.ppl_authority_runtime import (
    AuthorityManifestError,
    CutoverQuiescence,
    PPLAuthorityRuntime,
    RollbackDisposition,
    build_authority_runtime_from_env,
    build_cutover_manifest,
    configured_rollback_disposition,
    load_authority_manifest,
    write_authority_manifest,
)


EPOCH = "PPL02E-AUTH-001"
SHADOW = "PPL02D-SHADOW-002"


def clean_quiescence() -> CutoverQuiescence:
    return CutoverQuiescence(
        legacy_open_positions=0,
        legacy_pending_orders=0,
        legacy_transitions_in_flight=0,
        legacy_process_stopped=True,
    )


def manifest(**overrides):
    values = dict(
        paper_epoch_id=EPOCH,
        created_at=10.0,
        initial_virtual_capital=100.0,
        code_sha="sha-r4",
        config_snapshot_hash="cfg-r4",
        legacy_log_bytes=b'{"event":"CLOSE","trade_id":"legacy"}\n',
        quiescence=clean_quiescence(),
        predecessor_shadow_epoch_id=SHADOW,
    )
    values.update(overrides)
    return build_cutover_manifest(**values)


def runtime(tmp_path, *, compatibility=True):
    target = tmp_path / "paper_trades.jsonl" if compatibility else None
    rt = PPLAuthorityRuntime(
        manifest=manifest(),
        store=DurableEventStore(tmp_path / "ppl"),
        compatibility_path=target,
    )
    rt.bind(now=11.0)
    return rt


@pytest.mark.parametrize(
    "quiescence",
    [
        CutoverQuiescence(1, 0, 0, True),
        CutoverQuiescence(0, 1, 0, True),
        CutoverQuiescence(0, 0, 1, True),
        CutoverQuiescence(0, 0, 0, False),
    ],
)
def test_r4_cutover_requires_exact_quiescent_boundary(quiescence):
    with pytest.raises(AuthorityManifestError, match="cutover requires"):
        manifest(quiescence=quiescence)


def test_r4_authority_epoch_cannot_reuse_shadow_epoch():
    with pytest.raises(ValueError, match="differ"):
        manifest(paper_epoch_id=SHADOW, predecessor_shadow_epoch_id=SHADOW)


def test_r4_manifest_fingerprints_legacy_boundary():
    m = manifest()
    assert m.legacy_event_count == 1
    assert len(m.legacy_boundary_sha256) == 64
    assert m.epoch_role == "PPL_AUTHORITY_TRANSITION"
    assert m.ppl_event_schema_version == 2


def test_r4_manifest_write_is_explicit_and_non_overwriting(tmp_path):
    path = tmp_path / "authority.json"
    m = manifest()
    write_authority_manifest(path, m)
    assert load_authority_manifest(path) == m

    with pytest.raises(FileExistsError):
        write_authority_manifest(path, m)


def test_r4_env_runtime_requires_manifest_store_and_exact_epoch(tmp_path):
    path = tmp_path / "authority.json"
    write_authority_manifest(path, manifest())

    with pytest.raises(AuthorityManifestError):
        build_authority_runtime_from_env(
            {
                "PPL_AUTHORITY_MANIFEST": str(path),
                "PPL_AUTHORITY_STORE_ROOT": str(tmp_path / "ppl"),
                "PPL_AUTHORITY_EPOCH_ID": "wrong-epoch",
            }
        )

    rt = build_authority_runtime_from_env(
        {
            "PPL_AUTHORITY_MANIFEST": str(path),
            "PPL_AUTHORITY_STORE_ROOT": str(tmp_path / "ppl"),
            "PPL_AUTHORITY_EPOCH_ID": EPOCH,
            "PAPER_TRADE_LOG": str(tmp_path / "paper.jsonl"),
        }
    )
    assert rt.manifest.paper_epoch_id == EPOCH


def test_r4_bind_creates_only_new_schema_v2_authority_epoch(tmp_path):
    rt = runtime(tmp_path)
    view = rt.consistent_view()

    assert len(view.events) == 1
    assert view.events[0].schema_version == 2
    assert view.events[0].paper_epoch_id == EPOCH
    assert view.projection.epoch is not None
    assert view.projection.epoch.schema_version == 2
    assert rt.rollback_disposition() is RollbackDisposition.SAFE_BEFORE_FIRST_LIFECYCLE_EVENT


def test_r4_open_retry_is_idempotent_with_same_durable_sequence(tmp_path):
    rt = runtime(tmp_path)
    kwargs = dict(
        trade_id="trade-1",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        opened_at=20.0,
        tp_price=104.0,
        sl_price=98.0,
        timeout_at=30.0,
        recovery_eligible_until=40.0,
        decision_id="dp-1",
    )

    first = rt.commit_open(**kwargs)
    second = rt.commit_open(**kwargs)
    view = rt.consistent_view()

    assert first.status is AppendStatus.APPENDED
    assert second.status is AppendStatus.ALREADY_EXISTS
    assert [event.sequence for event in view.events] == [1, 2]
    assert len(view.projection.open_positions) == 1
    assert rt.rollback_disposition() is RollbackDisposition.BLOCKED_RECONCILIATION_REQUIRED


def test_r4_restart_replays_exact_open_position(tmp_path):
    rt = runtime(tmp_path)
    rt.commit_open(
        trade_id="trade-1",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        opened_at=20.0,
        tp_price=104.0,
        sl_price=98.0,
        timeout_at=30.0,
        recovery_eligible_until=40.0,
        decision_id="dp-1",
    )

    restarted = PPLAuthorityRuntime(
        manifest=manifest(),
        store=DurableEventStore(tmp_path / "ppl"),
        compatibility_path=tmp_path / "paper_trades.jsonl",
    )
    state = restarted.bind(now=25.0)
    pos = state.open_positions["trade-1"]

    assert pos.entry_price == 100.0
    assert pos.tp_price == 104.0
    assert pos.sl_price == 98.0
    assert pos.opened_at == 20.0
    assert pos.timeout_at == 30.0
    assert pos.recovery_eligible_until == 40.0


def test_r4_restart_after_recovery_window_emits_unresolved_not_fake_close(tmp_path):
    rt = runtime(tmp_path)
    rt.commit_open(
        trade_id="trade-1",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        opened_at=20.0,
        tp_price=104.0,
        sl_price=98.0,
        timeout_at=30.0,
        recovery_eligible_until=40.0,
        decision_id="dp-1",
    )

    restarted = PPLAuthorityRuntime(
        manifest=manifest(),
        store=DurableEventStore(tmp_path / "ppl"),
    )
    state = restarted.bind(now=41.0)

    assert "trade-1" not in state.open_positions
    assert "trade-1" in state.unresolved_positions
    assert state.unresolved_capital == pytest.approx(10.0)
    assert state.realized_pnl == 0.0
    assert restarted.consistent_view().events[-1].event_type.value == "POSITION_UNRESOLVED"


def test_r5_invalid_open_is_rejected_before_durable_append(tmp_path):
    rt = runtime(tmp_path)
    epoch_path = next((tmp_path / "ppl" / "epochs").iterdir())
    durable_before = epoch_path.read_bytes()
    events_before = rt.store.load_epoch(EPOCH)

    with pytest.raises(NegativeCashError, match="OPEN"):
        rt.commit_open(
            trade_id="trade-too-large",
            symbol="BTCUSDT",
            side="BUY",
            principal=100.0,
            entry_price=100.0,
            entry_fee=0.01,
            opened_at=20.0,
            tp_price=104.0,
            sl_price=98.0,
            timeout_at=30.0,
            recovery_eligible_until=40.0,
            decision_id="dp-too-large",
        )

    assert rt.store.load_epoch(EPOCH) == events_before
    assert epoch_path.read_bytes() == durable_before
    assert len(rt.consistent_view().events) == 1


def test_r5_adverse_short_close_never_poison_durable_epoch(tmp_path):
    rt = runtime(tmp_path)
    rt.commit_open(
        trade_id="trade-short",
        symbol="BTCUSDT",
        side="SELL",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        opened_at=20.0,
        tp_price=96.0,
        sl_price=102.0,
        timeout_at=30.0,
        recovery_eligible_until=40.0,
        decision_id="dp-short",
    )
    epoch_path = next((tmp_path / "ppl" / "epochs").iterdir())
    durable_before = epoch_path.read_bytes()
    events_before = rt.store.load_epoch(EPOCH)

    with pytest.raises(NegativeCashError, match="CLOSE"):
        rt.commit_close(
            trade_id="trade-short",
            exit_price=2000.0,
            exit_fee=0.01,
            closed_at=25.0,
            decision_id="dp-short",
        )

    assert rt.store.load_epoch(EPOCH) == events_before
    assert epoch_path.read_bytes() == durable_before
    view = rt.consistent_view()
    assert len(view.events) == 2
    assert "trade-short" in view.projection.open_positions

    restarted = PPLAuthorityRuntime(
        manifest=manifest(),
        store=DurableEventStore(tmp_path / "ppl"),
    )
    state = restarted.bind(now=25.0)
    assert "trade-short" in state.open_positions
    assert len(restarted.consistent_view().events) == 2


def test_r5_simulator_invalid_short_close_keeps_memory_and_durable_state(tmp_path):
    rt = runtime(tmp_path)
    sim = MexcSimulator(
        lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
        authority_runtime=rt,
    )
    sim._capital = 100.0
    sim._initial_capital = 100.0
    order = MexcOrder(
        order_id="SHORT1",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        qty_usd=10.0,
        decision_id="dp-short",
    )
    sim._fill_market(order, 100.0)
    capital_before = sim._capital
    events_before = rt.store.load_epoch(EPOCH)
    epoch_path = next((tmp_path / "ppl" / "epochs").iterdir())
    durable_before = epoch_path.read_bytes()

    with pytest.raises(NegativeCashError, match="CLOSE"):
        sim._close_position("BTCUSDT", 2000.0, "SL")

    assert "BTCUSDT" in sim._positions
    assert sim._capital == capital_before
    assert rt.store.load_epoch(EPOCH) == events_before
    assert epoch_path.read_bytes() == durable_before


def test_r4_close_retry_is_idempotent(tmp_path):
    rt = runtime(tmp_path)
    rt.commit_open(
        trade_id="trade-1",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        opened_at=20.0,
        tp_price=104.0,
        sl_price=98.0,
        timeout_at=30.0,
        recovery_eligible_until=40.0,
        decision_id="dp-1",
    )
    kwargs = dict(
        trade_id="trade-1",
        exit_price=110.0,
        exit_fee=0.01,
        closed_at=25.0,
        decision_id="dp-1",
    )

    first = rt.commit_close(**kwargs)
    second = rt.commit_close(**kwargs)

    assert first.status is AppendStatus.APPENDED
    assert second.status is AppendStatus.ALREADY_EXISTS
    assert [event.sequence for event in rt.consistent_view().events] == [1, 2, 3]
    assert rt.consistent_view().projection.available_cash == pytest.approx(100.98)


class _FailBeforeDurable:
    def commit_open(self, **_kwargs):
        raise OSError("fsync failed")


def test_r4_simulator_does_not_mutate_memory_when_ppl_open_commit_fails():
    sim = MexcSimulator(
        lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
        authority_runtime=_FailBeforeDurable(),
    )
    sim._capital = 100.0
    sim._initial_capital = 100.0
    order = MexcOrder(
        order_id="ORDER1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        qty_usd=10.0,
    )

    with pytest.raises(OSError, match="fsync failed"):
        sim._fill_market(order, 100.0)

    assert sim._capital == 100.0
    assert sim._positions == {}
    assert order.status is OrderStatus.PENDING


def test_r4_simulator_market_open_and_close_follow_ppl_projection(tmp_path):
    rt = runtime(tmp_path)
    sim = MexcSimulator(
        lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
        authority_runtime=rt,
    )
    sim._capital = 100.0
    sim._initial_capital = 100.0
    order = MexcOrder(
        order_id="ORDER1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        qty_usd=10.0,
        decision_id="dp-order",
    )

    filled = sim._fill_market(order, 100.0)
    assert filled.status is OrderStatus.FILLED
    assert "BTCUSDT" in sim._positions
    assert len(rt.consistent_view().events) == 2
    assert sim._capital == pytest.approx(rt.consistent_view().projection.available_cash)

    sim._close_position("BTCUSDT", 110.0, "TP")
    assert "BTCUSDT" not in sim._positions
    assert len(rt.consistent_view().events) == 3
    assert sim._capital == pytest.approx(rt.consistent_view().projection.available_cash)


def test_r4_limit_and_stop_limit_remain_fail_closed_under_ppl_authority(tmp_path):
    rt = runtime(tmp_path)
    sim = MexcSimulator(
        lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
        authority_runtime=rt,
    )

    limit_order = sim.place_limit_order("BTCUSDT", "BUY", 10.0, 100.0)
    stop_order = sim.place_stop_limit_order("ETHUSDT", "BUY", 10.0, 101.0, 100.0)

    assert limit_order.status is OrderStatus.REJECTED
    assert stop_order.status is OrderStatus.REJECTED
    assert len(rt.consistent_view().events) == 1


def test_r4_web02_reports_true_authority_after_cutover(tmp_path):
    rt = runtime(tmp_path)
    sim = MexcSimulator(
        lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
        authority_runtime=rt,
    )
    path = tmp_path / "comparison.json"

    doc = write_ppl_comparison_snapshot(
        sim,
        path=path,
        cycle=7,
        process_instance_id="proc-r4",
        source_sha="sha-r4",
        now_fn=lambda: 12.0,
    )

    assert doc["mode"] == "AUTHORITY_STATUS"
    assert doc["comparison_available"] is False
    assert doc["legacy_source"]["authority"] == "NONE"
    assert doc["ppl_source"]["authority"] == "PAPER_AUTHORITY"
    assert doc["paper_epoch_id"] == EPOCH
    assert len(doc["ppl_events"]) == 1

    result = PplComparisonSnapshotReader(
        path,
        stale_after_s=90.0,
        now_fn=lambda: 12.0,
    ).read()
    assert result.ok is True
    assert result.snapshot["mode"] == "AUTHORITY_STATUS"


def test_r4_compatibility_projection_is_downstream_only(tmp_path):
    rt = runtime(tmp_path)
    rt.commit_open(
        trade_id="trade-1",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        opened_at=20.0,
        tp_price=104.0,
        sl_price=98.0,
        timeout_at=30.0,
        recovery_eligible_until=40.0,
        decision_id="dp-1",
    )
    count = rt.sync_compatibility()
    second = rt.sync_compatibility()
    rows = [
        json.loads(line)
        for line in (tmp_path / "paper_trades.jsonl").read_text().splitlines()
        if line.strip()
    ]

    assert count == 1
    assert second == 0
    assert rows[0]["source_authority"] == "PPL"
    assert rows[0]["paper_epoch_id"] == EPOCH


def test_r4_configured_rollback_guard_is_safe_before_lifecycle_and_blocks_after(tmp_path):
    path = tmp_path / "authority.json"
    store_root = tmp_path / "ppl"
    write_authority_manifest(path, manifest())
    env = {
        "PPL_AUTHORITY_MANIFEST": str(path),
        "PPL_AUTHORITY_STORE_ROOT": str(store_root),
        "PPL_AUTHORITY_EPOCH_ID": EPOCH,
    }

    assert (
        configured_rollback_disposition(env)
        is RollbackDisposition.SAFE_BEFORE_FIRST_LIFECYCLE_EVENT
    )

    rt = build_authority_runtime_from_env(env)
    rt.bind(now=11.0)
    assert (
        configured_rollback_disposition(env)
        is RollbackDisposition.SAFE_BEFORE_FIRST_LIFECYCLE_EVENT
    )

    rt.commit_open(
        trade_id="trade-rollback",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        opened_at=20.0,
        tp_price=104.0,
        sl_price=98.0,
        timeout_at=30.0,
        recovery_eligible_until=40.0,
        decision_id="dp-rb",
    )
    assert (
        configured_rollback_disposition(env)
        is RollbackDisposition.BLOCKED_RECONCILIATION_REQUIRED
    )


def test_r4_partial_authority_config_is_not_treated_as_safe_rollback(tmp_path):
    with pytest.raises(AuthorityManifestError, match="partial"):
        configured_rollback_disposition(
            {"PPL_AUTHORITY_STORE_ROOT": str(tmp_path / "ppl")}
        )
