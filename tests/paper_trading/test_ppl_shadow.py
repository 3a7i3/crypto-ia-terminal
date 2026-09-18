from __future__ import annotations

import json
import logging

import pytest

from paper_trading.durable_event_store import AppendStatus, DurableEventStore
from paper_trading.ledger_events import LedgerEventType
from paper_trading.ppl_shadow import (
    PPLShadowRuntime,
    ShadowCloseFact,
    ShadowConfigError,
    ShadowEpochManifest,
    ShadowLegacyPosition,
    ShadowManifestError,
    ShadowOpenFact,
    ShadowStatus,
    build_shadow_runtime_from_env,
    load_shadow_manifest,
)

EPOCH = "ppl-02d-shadow-test"
CREATED = 1_000.0
CAPITAL = 100.0


def manifest(*, capital: float = CAPITAL) -> ShadowEpochManifest:
    return ShadowEpochManifest(
        paper_epoch_id=EPOCH,
        created_at=CREATED,
        initial_virtual_capital=capital,
        code_sha="a" * 40,
        config_snapshot_hash="b" * 64,
    )


def runtime(tmp_path, *, capital: float = CAPITAL) -> PPLShadowRuntime:
    return PPLShadowRuntime(
        manifest=manifest(capital=capital),
        store=DurableEventStore(tmp_path / "ppl"),
    )


def open_position(*, principal: float = 10.0) -> ShadowLegacyPosition:
    return ShadowLegacyPosition(
        trade_id="trade-1",
        symbol="BTC/USDT",
        side="BUY",
        principal=principal,
        entry_price=100.0,
        entry_fee=0.01,
    )


def open_fact(*, principal: float = 10.0) -> ShadowOpenFact:
    return ShadowOpenFact(
        trade_id="trade-1",
        symbol="BTC/USDT",
        side="BUY",
        principal=principal,
        entry_price=100.0,
        entry_fee=0.01,
        timestamp=CREATED + 1,
        decision_id="dp-1",
    )


def close_fact() -> ShadowCloseFact:
    return ShadowCloseFact(
        trade_id="trade-1",
        exit_price=110.0,
        exit_fee=0.01,
        timestamp=CREATED + 2,
        decision_id="dp-1",
    )


def write_manifest(path, **overrides):
    data = {
        "schema_version": 1,
        "paper_epoch_id": EPOCH,
        "created_at": CREATED,
        "initial_virtual_capital": CAPITAL,
        "code_sha": "a" * 40,
        "config_snapshot_hash": "b" * 64,
    }
    data.update(overrides)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_d01_default_configuration_is_off_and_creates_no_store(tmp_path):
    assert build_shadow_runtime_from_env({}) is None
    assert list(tmp_path.iterdir()) == []


def test_d02_configuration_requires_manifest_and_store_together(tmp_path):
    with pytest.raises(ShadowConfigError):
        build_shadow_runtime_from_env(
            {"PPL_SHADOW_STORE_ROOT": str(tmp_path / "ppl")}
        )
    with pytest.raises(ShadowConfigError):
        build_shadow_runtime_from_env(
            {"PPL_SHADOW_MANIFEST": str(tmp_path / "m.json")}
        )


def test_manifest_is_strict_and_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1,'
        '"paper_epoch_id":"x","created_at":1,'
        '"initial_virtual_capital":100,"code_sha":"a",'
        '"config_snapshot_hash":"b"}',
        encoding="utf-8",
    )
    with pytest.raises(ShadowManifestError):
        load_shadow_manifest(path)


def test_configured_runtime_uses_only_explicit_paths(tmp_path):
    manifest_path = write_manifest(tmp_path / "manifest.json")
    store_root = tmp_path / "explicit-ppl"
    shadow = build_shadow_runtime_from_env(
        {
            "PPL_SHADOW_MANIFEST": str(manifest_path),
            "PPL_SHADOW_STORE_ROOT": str(store_root),
        }
    )
    assert shadow is not None
    assert shadow.status is ShadowStatus.WAITING_CLEAN_BOUNDARY
    assert not store_root.exists()


def test_d03_first_activation_with_open_positions_waits_without_creating_epoch(
    tmp_path,
):
    shadow = runtime(tmp_path)
    assert (
        shadow.bind_legacy_state(
            available_capital=CAPITAL,
            open_positions=[open_position()],
        )
        is False
    )
    assert shadow.status is ShadowStatus.WAITING_CLEAN_BOUNDARY
    assert shadow.events == ()
    assert not (tmp_path / "ppl").exists()


def test_d04_first_activation_capital_mismatch_degrades_without_creating_epoch(
    tmp_path,
):
    shadow = runtime(tmp_path)
    assert (
        shadow.bind_legacy_state(
            available_capital=CAPITAL - 1,
            open_positions=[],
        )
        is False
    )
    assert shadow.status is ShadowStatus.DEGRADED
    assert shadow.events == ()
    assert not (tmp_path / "ppl").exists()


def test_d05_clean_activation_creates_exactly_one_epoch_event(tmp_path):
    shadow = runtime(tmp_path)
    assert shadow.bind_legacy_state(available_capital=CAPITAL, open_positions=[])
    assert shadow.status is ShadowStatus.ACTIVE
    assert len(shadow.events) == 1
    birth = shadow.events[0]
    assert birth.sequence == 1
    assert birth.event_type is LedgerEventType.EPOCH_CREATED
    assert birth.paper_epoch_id == EPOCH
    assert birth.trade_id is None
    assert shadow.projection is not None
    assert shadow.projection.available_cash == pytest.approx(CAPITAL)


def test_d07_d08_exact_open_close_facts_project_independently(tmp_path):
    shadow = runtime(tmp_path)
    assert shadow.bind_legacy_state(available_capital=CAPITAL, open_positions=[])

    opened = shadow.observe_open(open_fact())
    assert opened is not None
    assert opened.status is AppendStatus.APPENDED
    assert opened.sequence == 2
    state = shadow.projection
    assert state is not None
    assert state.available_cash == pytest.approx(89.99)
    assert state.reserved_principal == pytest.approx(10.0)
    assert state.fees_paid == pytest.approx(0.01)
    assert set(state.open_positions) == {"trade-1"}

    closed = shadow.observe_close(close_fact())
    assert closed is not None
    assert closed.status is AppendStatus.APPENDED
    assert closed.sequence == 3
    state = shadow.projection
    assert state is not None
    assert state.available_cash == pytest.approx(100.98)
    assert state.reserved_principal == pytest.approx(0.0)
    assert state.realized_pnl == pytest.approx(0.98)
    assert state.fees_paid == pytest.approx(0.02)
    assert state.open_positions == {}


def test_d09_duplicate_semantic_retry_is_idempotent(tmp_path):
    shadow = runtime(tmp_path)
    assert shadow.bind_legacy_state(available_capital=CAPITAL, open_positions=[])

    first = shadow.observe_open(open_fact())
    second = shadow.observe_open(open_fact())
    assert first is not None and first.status is AppendStatus.APPENDED
    assert second is not None and second.status is AppendStatus.ALREADY_EXISTS
    assert len(shadow.events) == 2

    first_close = shadow.observe_close(close_fact())
    second_close = shadow.observe_close(close_fact())
    assert first_close is not None and first_close.status is AppendStatus.APPENDED
    assert second_close is not None
    assert second_close.status is AppendStatus.ALREADY_EXISTS
    assert len(shadow.events) == 3


def test_d10_same_deterministic_identity_with_different_facts_degrades(tmp_path):
    shadow = runtime(tmp_path)
    assert shadow.bind_legacy_state(available_capital=CAPITAL, open_positions=[])
    assert shadow.observe_open(open_fact(principal=10.0)) is not None

    assert shadow.observe_open(open_fact(principal=11.0)) is None
    assert shadow.status is ShadowStatus.DEGRADED
    assert shadow.last_error is not None
    assert "ShadowIdentityCollisionError" in shadow.last_error
    assert len(shadow.store.load_epoch(EPOCH)) == 2


def test_d06_restart_reuses_epoch_and_reconciles_open_position(tmp_path):
    first = runtime(tmp_path)
    assert first.bind_legacy_state(available_capital=CAPITAL, open_positions=[])
    assert first.observe_open(open_fact()) is not None

    second = runtime(tmp_path)
    assert second.bind_legacy_state(
        available_capital=12.34,
        open_positions=[open_position()],
    )
    assert second.status is ShadowStatus.ACTIVE
    assert len(second.events) == 2
    assert (
        sum(
            event.event_type is LedgerEventType.EPOCH_CREATED
            for event in second.events
        )
        == 1
    )


def test_d13_restart_position_mismatch_fails_shadow_closed(tmp_path):
    first = runtime(tmp_path)
    assert first.bind_legacy_state(available_capital=CAPITAL, open_positions=[])
    assert first.observe_open(open_fact()) is not None

    second = runtime(tmp_path)
    assert (
        second.bind_legacy_state(
            available_capital=12.34,
            open_positions=[open_position(principal=11.0)],
        )
        is False
    )
    assert second.status is ShadowStatus.DEGRADED
    assert second.last_error is not None
    assert "principal mismatch" in second.last_error
    assert len(second.store.load_epoch(EPOCH)) == 2


def test_shadow_append_failure_degrades_without_fabricating_success(
    tmp_path,
    monkeypatch,
):
    shadow = runtime(tmp_path)
    assert shadow.bind_legacy_state(available_capital=CAPITAL, open_positions=[])

    def boom(*_args, **_kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(shadow.store, "append", boom)
    assert shadow.observe_open(open_fact()) is None
    assert shadow.status is ShadowStatus.DEGRADED
    assert shadow.last_error is not None
    assert "disk failure" in shadow.last_error
    assert len(DurableEventStore(tmp_path / "ppl").load_epoch(EPOCH)) == 1


def test_real_shadow_degradation_is_observable_and_stops_on_first_transition(
    tmp_path,
    monkeypatch,
    caplog,
):
    """Blocker 3 (MASTER review): a real durable-store failure inside
    PPLShadowRuntime must produce an explicit, one-time [PPL-02D] DEGRADED
    log — the outer MexcSimulator try/except never sees this exception (it
    is deliberately swallowed to stay non-authoritative), so this is the
    only observability point for the transition.

    Uses a REAL PPLShadowRuntime backed by a REAL DurableEventStore (only
    ``store.append`` is monkeypatched to fail) — not a MagicMock observer —
    to prove the actual production `_degrade()` path, not a test double's
    behavior.
    """
    shadow = runtime(tmp_path)

    # 1. Clean shadow activation succeeds.
    assert shadow.bind_legacy_state(available_capital=CAPITAL, open_positions=[])
    assert shadow.status is ShadowStatus.ACTIVE

    # 2. Induce a real shadow failure on the durable-store append path.
    def boom(*_args, **_kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(shadow.store, "append", boom)

    # 3./4. Call observe_open(): result is None, no exception propagates.
    with caplog.at_level(logging.ERROR, logger="paper_trading.ppl_shadow"):
        result = shadow.observe_open(open_fact())
    assert result is None

    # 5./6. status == DEGRADED and last_error carries the actual failure.
    assert shadow.status is ShadowStatus.DEGRADED
    assert shadow.last_error is not None
    assert "OSError" in shadow.last_error
    assert "disk failure" in shadow.last_error

    # 7. caplog contains exactly one explicit PPL-02D DEGRADED log, carrying
    # the PPL-02D identifier, DEGRADED, the exception type/message, and the
    # paper_epoch_id.
    degraded_records = [
        r
        for r in caplog.records
        if "[PPL-02D]" in r.message and "DEGRADED" in r.message
    ]
    assert len(degraded_records) == 1
    message = degraded_records[0].message
    assert "OSError" in message
    assert "disk failure" in message
    assert EPOCH in message

    events_before = len(shadow.store.load_epoch(EPOCH))
    caplog.clear()

    # 8. Repeating another observation while already DEGRADED must not
    # append events and must not produce another transition log (the
    # guard clause at the top of observe_close short-circuits before the
    # still-broken store.append is ever reached).
    with caplog.at_level(logging.ERROR, logger="paper_trading.ppl_shadow"):
        result_2 = shadow.observe_close(close_fact())
    assert result_2 is None
    assert shadow.status is ShadowStatus.DEGRADED
    assert len(shadow.store.load_epoch(EPOCH)) == events_before
    repeated_degraded_records = [
        r
        for r in caplog.records
        if "[PPL-02D]" in r.message and "DEGRADED" in r.message
    ]
    assert repeated_degraded_records == []


def test_generation_ack_only_advances_on_contiguous_prefix(tmp_path):
    """(4) PPL arriving out of order -> the ack advances only once the
    missing prefix generation also lands (WEB-02 causal-coherence gate)."""
    shadow = runtime(tmp_path)
    assert shadow.bind_legacy_state(available_capital=CAPITAL, open_positions=[])

    fact_b = ShadowOpenFact(
        trade_id="trade-B",
        symbol="ETH/USDT",
        side="BUY",
        principal=5.0,
        entry_price=50.0,
        entry_fee=0.005,
        timestamp=CREATED + 1,
        legacy_generation=2,
    )
    assert shadow.observe_open(fact_b) is not None
    # Generation 2 landed but 1 is still outstanding — never announced as
    # fully acknowledged yet.
    assert shadow.consistent_view().observed_legacy_generation == 0

    fact_a = ShadowOpenFact(
        trade_id="trade-A",
        symbol="BTC/USDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        timestamp=CREATED + 2,
        legacy_generation=1,
    )
    assert shadow.observe_open(fact_a) is not None
    # The contiguous prefix [1, 2] is now complete.
    assert shadow.consistent_view().observed_legacy_generation == 2


def test_manifest_rejects_non_finite_capital(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"schema_version":1,"paper_epoch_id":"x","created_at":1,'
        '"initial_virtual_capital":NaN,"code_sha":"a",'
        '"config_snapshot_hash":"b"}',
        encoding="utf-8",
    )
    with pytest.raises(ShadowManifestError):
        load_shadow_manifest(path)
