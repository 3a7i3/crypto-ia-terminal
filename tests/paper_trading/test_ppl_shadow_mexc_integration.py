"""PPL-02D runtime integration proofs — MexcSimulator <-> PPL SHADOW.

These tests prove the wiring described in
``docs/contracts/PPL_02D_SHADOW_MODE.md``: MexcSimulator exposes an
OPTIONAL, default-OFF shadow observer; the observer never influences the
legacy MEXC_SIM authoritative path; and, when actually configured, the
observed OPEN/CLOSE facts project through the real PPL event-sourced
pipeline while legacy PAPER remains untouched.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

import core.advisor_loop as advisor_loop
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.ledger_events import LedgerEventType
from paper_trading.mexc_simulator import MexcSimulator, OrderSide
from paper_trading.paper_portfolio_ledger import project
from paper_trading.ppl_shadow import (
    PPLShadowRuntime,
    ShadowEpochManifest,
    ShadowStatus,
)


def _reader(price: float = 100.0) -> MagicMock:
    reader = MagicMock()
    reader.spot.fetch_ticker.return_value = {"last": price}
    return reader


def _patch_recorder_to_tmp(monkeypatch, tmp_path):
    """Redirect the legacy PaperTradeRecorder singleton to a scratch file.

    Ensures these tests never touch the real paper_trades.jsonl and lets
    assertions observe legacy writes in isolation.
    """
    import paper_trading.recorder as recorder_module

    rec = recorder_module.PaperTradeRecorder(log_path=str(tmp_path / "paper_trades.jsonl"))
    monkeypatch.setattr(recorder_module, "_recorder", rec)
    return rec


# ---------------------------------------------------------------------------
# A — DEFAULT OFF
# ---------------------------------------------------------------------------


def test_a_default_off_behavior_identical_with_and_without_observer(
    monkeypatch, tmp_path
):
    _patch_recorder_to_tmp(monkeypatch, tmp_path)

    sim_no_shadow = MexcSimulator(mexc_reader=_reader())
    sim_no_shadow._capital = 100.0
    sim_no_shadow._initial_capital = 100.0

    order = sim_no_shadow.place_market_order(
        symbol="BTC/USDT", side="BUY", qty_usd=10.0, current_price=100.0
    )
    assert order.status.value == "FILLED"
    capital_after_open_no_shadow = sim_no_shadow._capital

    sim_no_shadow._close_position("BTC/USDT", 110.0, "TP")
    capital_after_close_no_shadow = sim_no_shadow._capital

    # Same scenario with an explicit observer that is never bound/active
    # (status defaults to WAITING_CLEAN_BOUNDARY -> observe_* are no-ops)
    # must produce the identical legacy capital trajectory.
    manifest = ShadowEpochManifest(
        paper_epoch_id="off-check",
        created_at=1.0,
        initial_virtual_capital=100.0,
        code_sha="a" * 40,
        config_snapshot_hash="b" * 64,
    )
    shadow = PPLShadowRuntime(manifest=manifest, store=DurableEventStore(tmp_path / "ppl"))
    sim_with_shadow = MexcSimulator(mexc_reader=_reader(), shadow_observer=shadow)
    sim_with_shadow._capital = 100.0
    sim_with_shadow._initial_capital = 100.0

    order2 = sim_with_shadow.place_market_order(
        symbol="BTC/USDT", side="BUY", qty_usd=10.0, current_price=100.0
    )
    assert order2.status.value == "FILLED"
    assert sim_with_shadow._capital == pytest.approx(capital_after_open_no_shadow)

    sim_with_shadow._close_position("BTC/USDT", 110.0, "TP")
    assert sim_with_shadow._capital == pytest.approx(capital_after_close_no_shadow)

    # Inactive shadow observed nothing (status was never ACTIVE).
    assert shadow.status is ShadowStatus.WAITING_CLEAN_BOUNDARY
    assert shadow.events == ()


def _bound_shadow(tmp_path, epoch_id="epoch-1", capital=100.0):
    manifest = ShadowEpochManifest(
        paper_epoch_id=epoch_id,
        created_at=1.0,
        initial_virtual_capital=capital,
        code_sha="a" * 40,
        config_snapshot_hash="b" * 64,
    )
    shadow = PPLShadowRuntime(manifest=manifest, store=DurableEventStore(tmp_path / "ppl"))
    assert shadow.bind_legacy_state(available_capital=capital, open_positions=[])
    assert shadow.status is ShadowStatus.ACTIVE
    return shadow


# ---------------------------------------------------------------------------
# B — EXACT OPEN FACT
# ---------------------------------------------------------------------------


def test_b_exact_open_fact_sent_to_observer(monkeypatch, tmp_path):
    _patch_recorder_to_tmp(monkeypatch, tmp_path)
    observer = MagicMock()
    sim = MexcSimulator(mexc_reader=_reader(), shadow_observer=observer)
    sim._capital = 100.0
    sim._initial_capital = 100.0

    order = sim.place_market_order(
        symbol="ETH/USDT",
        side="BUY",
        qty_usd=10.0,
        current_price=100.0,
        decision_id="dp-abc",
    )
    assert order.status.value == "FILLED"
    pos = sim._positions["ETH/USDT"]

    observer.observe_open.assert_called_once()
    (fact,), _ = observer.observe_open.call_args
    assert fact.trade_id == pos.pos_id
    assert fact.symbol == "ETH/USDT"
    assert fact.side == OrderSide.BUY.value
    assert fact.principal == pytest.approx(pos.qty_usd)
    assert fact.entry_price == pytest.approx(pos.entry_price)
    assert fact.entry_fee == pytest.approx(pos.fee_entry_usd)
    assert fact.decision_id == "dp-abc"
    observer.observe_close.assert_not_called()


# ---------------------------------------------------------------------------
# C — EXACT CLOSE FACT
# ---------------------------------------------------------------------------


def test_c_exact_close_fact_sent_to_observer(monkeypatch, tmp_path):
    _patch_recorder_to_tmp(monkeypatch, tmp_path)
    observer = MagicMock()
    sim = MexcSimulator(mexc_reader=_reader(), shadow_observer=observer)
    sim._capital = 100.0
    sim._initial_capital = 100.0

    sim.place_market_order(
        symbol="ETH/USDT",
        side="BUY",
        qty_usd=10.0,
        current_price=100.0,
        decision_id="dp-xyz",
    )
    observer.reset_mock()

    sim._close_position("ETH/USDT", 110.0, "TP")
    closed_pos = sim._closed[-1]

    observer.observe_close.assert_called_once()
    (fact,), _ = observer.observe_close.call_args
    assert fact.trade_id == closed_pos.pos_id
    assert fact.exit_price == pytest.approx(closed_pos.exit_price)
    assert fact.exit_fee == pytest.approx(closed_pos.qty_usd * 0.001)
    assert fact.decision_id == "dp-xyz"


# ---------------------------------------------------------------------------
# D — OBSERVER OPEN FAILURE IS NON-AUTHORITATIVE
# ---------------------------------------------------------------------------


def test_d_observer_open_failure_does_not_affect_legacy_state(monkeypatch, tmp_path):
    _patch_recorder_to_tmp(monkeypatch, tmp_path)

    baseline = MexcSimulator(mexc_reader=_reader())
    baseline._capital = 100.0
    baseline._initial_capital = 100.0
    baseline_order = baseline.place_market_order(
        symbol="BTC/USDT", side="BUY", qty_usd=10.0, current_price=100.0
    )

    observer = MagicMock()
    observer.observe_open.side_effect = RuntimeError("shadow boom")
    sim = MexcSimulator(mexc_reader=_reader(), shadow_observer=observer)
    sim._capital = 100.0
    sim._initial_capital = 100.0
    order = sim.place_market_order(
        symbol="BTC/USDT", side="BUY", qty_usd=10.0, current_price=100.0
    )

    assert order.status == baseline_order.status
    assert order.fill_price == pytest.approx(baseline_order.fill_price)
    assert sim._capital == pytest.approx(baseline._capital)
    assert "BTC/USDT" in sim._positions


# ---------------------------------------------------------------------------
# E — OBSERVER CLOSE FAILURE IS NON-AUTHORITATIVE
# ---------------------------------------------------------------------------


def test_e_observer_close_failure_does_not_affect_legacy_state(monkeypatch, tmp_path):
    _patch_recorder_to_tmp(monkeypatch, tmp_path)

    baseline = MexcSimulator(mexc_reader=_reader())
    baseline._capital = 100.0
    baseline._initial_capital = 100.0
    baseline.place_market_order(
        symbol="BTC/USDT", side="BUY", qty_usd=10.0, current_price=100.0
    )
    baseline._close_position("BTC/USDT", 110.0, "TP")
    baseline_pos = baseline._closed[-1]

    observer = MagicMock()
    observer.observe_close.side_effect = RuntimeError("shadow boom")
    sim = MexcSimulator(mexc_reader=_reader(), shadow_observer=observer)
    sim._capital = 100.0
    sim._initial_capital = 100.0
    sim.place_market_order(
        symbol="BTC/USDT", side="BUY", qty_usd=10.0, current_price=100.0
    )
    sim._close_position("BTC/USDT", 110.0, "TP")
    pos = sim._closed[-1]

    assert "BTC/USDT" not in sim._positions
    assert pos.exit_price == pytest.approx(baseline_pos.exit_price)
    assert pos.pnl_usd == pytest.approx(baseline_pos.pnl_usd)
    assert pos.closed_ts != 0.0
    assert sim._capital == pytest.approx(baseline._capital)


# ---------------------------------------------------------------------------
# F — STARTUP BIND FAILURE IS NON-AUTHORITATIVE
# ---------------------------------------------------------------------------


def test_f_startup_bind_failure_does_not_prevent_legacy_start(monkeypatch, tmp_path):
    _patch_recorder_to_tmp(monkeypatch, tmp_path)

    class _FakeWallet:
        mode = "paper"

        def get_balance(self, force_refresh: bool = False) -> float:
            return 100.0

    import infra.wallet_sync as wallet_sync_module

    monkeypatch.setattr(wallet_sync_module, "get_wallet_sync", lambda: _FakeWallet())

    observer = MagicMock()
    observer.bind_legacy_state.side_effect = RuntimeError("bind boom")
    messages: list[str] = []
    sim = MexcSimulator(
        mexc_reader=_reader(), telegram_fn=messages.append, shadow_observer=observer
    )
    sim.start()
    sim._running = False

    assert sim._capital == pytest.approx(100.0)
    assert any("Compte actif" in m for m in messages)
    observer.bind_legacy_state.assert_called_once()


# ---------------------------------------------------------------------------
# G — NO POSITIONMANAGER CONTAMINATION
# ---------------------------------------------------------------------------


def test_g_no_positionmanager_recorder_feeds_ppl_shadow():
    """The only source wired into PPL shadow is MEXC_SIM.

    Structural proof: MexcSimulator (the certified MEXC_SIM domain) is the
    sole call-site of ``observe_open``/``observe_close``/``bind_legacy_state``
    in the runtime tree, and advisor_loop's independent
    PositionManager/ExecutionEngine/PaperTradeRecorder path never
    references the shadow observer at all.
    """
    import paper_trading.mexc_simulator as mexc_sim_module

    sim_source = inspect.getsource(mexc_sim_module)
    assert sim_source.count("observe_open(") >= 1
    assert sim_source.count("observe_close(") >= 1

    advisor_source = inspect.getsource(advisor_loop)
    # advisor_loop only ever constructs/wires the shadow observer into
    # MexcSimulator — it must never pass it to a PositionManager,
    # ExecutionEngine, or PaperTradeRecorder constructor/call.
    assert "shadow_observer=_ppl_shadow_observer" in advisor_source
    forbidden_targets = (
        "PositionManager(",
        "ExecutionEngine(",
        "PaperTradeRecorder(",
    )
    for line in advisor_source.splitlines():
        if "shadow_observer" in line or "_ppl_shadow_observer" in line:
            for target in forbidden_targets:
                assert target not in line


# ---------------------------------------------------------------------------
# H — REAL AUTHORITY ABSENT
# ---------------------------------------------------------------------------


def test_h_shadow_runtime_construction_confined_to_mexc_sim_paper_bootstrap():
    """build_shadow_runtime_from_env() is called only in the MEXC_SIM/PAPER
    bootstrap guarded by ``advisor_only or _paper_trading_enabled`` — never
    in a REAL execution path."""
    source = inspect.getsource(advisor_loop)
    call_marker = "build_shadow_runtime_from_env"
    assert call_marker in source

    idx = source.index(call_marker)
    preceding = source[:idx]
    # The nearest enclosing guard before the call site must be the
    # MEXC_SIM/PAPER bootstrap condition.
    guard_idx = preceding.rfind("if advisor_only or _paper_trading_enabled:")
    assert guard_idx != -1
    between = preceding[guard_idx:]
    # No other top-level (column-0) `if`/`def` interrupts the block between
    # the guard and the call site, i.e. the call is still inside that guard.
    for line in between.splitlines()[1:]:
        if line and not line[0].isspace():
            raise AssertionError(
                "build_shadow_runtime_from_env is not nested under the "
                "MEXC_SIM/PAPER bootstrap guard"
            )

    # No REAL execution module imports the PPL shadow runtime as authority.
    import glob

    for path in glob.glob("execution*/**/*.py", recursive=True) + glob.glob(
        "core/execution*.py"
    ):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "ppl_shadow" not in text, f"REAL execution module imports ppl_shadow: {path}"


# ---------------------------------------------------------------------------
# I — FULL EVENT PROJECTION
# ---------------------------------------------------------------------------


def test_i_full_event_projection_through_real_shadow_runtime(monkeypatch, tmp_path):
    rec = _patch_recorder_to_tmp(monkeypatch, tmp_path)

    shadow = _bound_shadow(tmp_path, epoch_id="epoch-full", capital=100.0)
    sim = MexcSimulator(mexc_reader=_reader(), shadow_observer=shadow)
    sim._capital = 100.0
    sim._initial_capital = 100.0

    order = sim.place_market_order(
        symbol="SOL/USDT",
        side="BUY",
        qty_usd=10.0,
        current_price=100.0,
        decision_id="dp-full",
    )
    assert order.status.value == "FILLED"
    assert shadow.status is ShadowStatus.ACTIVE

    sim._close_position("SOL/USDT", 110.0, "TP")
    assert shadow.status is ShadowStatus.ACTIVE

    events = shadow.store.load_epoch("epoch-full")
    types = [e.event_type for e in events]
    assert types == [
        LedgerEventType.EPOCH_CREATED,
        LedgerEventType.POSITION_OPENED,
        LedgerEventType.POSITION_CLOSED,
    ]

    state = project(events)
    assert state.open_positions == {}
    assert state.realized_pnl == pytest.approx(shadow.projection.realized_pnl)

    # Legacy recorder journal remains intact and independent.
    legacy_trades = rec.trades()
    assert len(legacy_trades) == 1
    assert legacy_trades[0].symbol == "SOL/USDT"
    assert not legacy_trades[0].is_open
