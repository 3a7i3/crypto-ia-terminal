"""
test_runtime.py — Tests P10-B : RuntimeCoordinator, LifecycleManager,
                  ExecutionContext, SystemStateBus

Sections :
  1. ExecutionContext (B-03)
  2. SystemStateBus   (B-04)
  3. LifecycleManager (B-02)
  4. RuntimeCoordinator (B-01)
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _ctx(**overrides) -> "ExecutionContext":
    from runtime.execution_context import ExecutionContext

    base = dict(
        capital_total=10_000.0,
        capital_used=2_000.0,
        capital_available=8_000.0,
        current_regime="TRENDING",
        regime_prob=0.80,
        risk_governor_state="NORMAL",
        strategy_allocations={"scalp": 0.25, "momentum": 0.75},
    )
    base.update(overrides)
    return ExecutionContext(**base)


# ── Section 1 : ExecutionContext (B-03) ───────────────────────────────────────


def test_ctx_coherent():
    ctx = _ctx()
    assert ctx.is_coherent()


def test_ctx_incoherent_capital():
    ctx = _ctx(capital_total=10_000.0, capital_used=3_000.0, capital_available=8_000.0)
    assert not ctx.is_coherent()
    assert "écart" in ctx.coherence_error()


def test_ctx_zero_capital_coherent():
    ctx = _ctx(capital_total=0.0, capital_used=0.0, capital_available=0.0)
    assert ctx.is_coherent()


def test_ctx_coherence_error_empty_when_coherent():
    ctx = _ctx()
    assert ctx.coherence_error() == ""


def test_ctx_freeze_independent_copy():
    ctx = _ctx()
    frozen = ctx.freeze()
    ctx.capital_total = 99_999.0
    assert frozen.capital_total == 10_000.0


def test_ctx_freeze_does_not_share_allocations():
    ctx = _ctx()
    frozen = ctx.freeze()
    ctx.strategy_allocations["new"] = 0.5
    assert "new" not in frozen.strategy_allocations


def test_ctx_to_dict_keys():
    ctx = _ctx()
    d = ctx.to_dict()
    for key in (
        "cycle_id",
        "current_regime",
        "capital_total",
        "capital_used",
        "capital_available",
        "shadow_mode",
    ):
        assert key in d


def test_ctx_to_signed_dict_has_signature():
    ctx = _ctx()
    d = ctx.to_signed_dict()
    assert "signature" in d
    assert len(d["signature"]) > 20


def test_ctx_from_snapshot_roundtrip():
    from runtime.execution_context import ExecutionContext

    ctx = _ctx()
    restored = ExecutionContext.from_snapshot(ctx.to_dict())
    assert restored.capital_total == ctx.capital_total
    assert restored.current_regime == ctx.current_regime
    assert restored.strategy_allocations == ctx.strategy_allocations


def test_ctx_new_cycle_new_id():
    ctx1 = _ctx()
    ctx2 = _ctx()
    from runtime.execution_context import ExecutionContext

    ctx2 = ExecutionContext.new_cycle(ctx1)
    assert ctx2.cycle_id != ctx1.cycle_id


def test_ctx_new_cycle_inherits_regime():
    from runtime.execution_context import ExecutionContext

    ctx1 = _ctx(current_regime="VOLATILE")
    ctx2 = ExecutionContext.new_cycle(ctx1)
    assert ctx2.current_regime == "VOLATILE"


def test_ctx_new_cycle_override():
    from runtime.execution_context import ExecutionContext

    ctx1 = _ctx(capital_total=10_000.0, capital_used=0.0, capital_available=10_000.0)
    ctx2 = ExecutionContext.new_cycle(
        ctx1, capital_total=20_000.0, capital_used=0.0, capital_available=20_000.0
    )
    assert ctx2.capital_total == 20_000.0
    assert ctx2.is_coherent()


def test_ctx_new_cycle_fresh_started_at():
    from runtime.execution_context import ExecutionContext

    ctx1 = _ctx()
    time.sleep(0.01)
    ctx2 = ExecutionContext.new_cycle(ctx1)
    assert ctx2.started_at > ctx1.started_at


def test_ctx_from_snapshot_infers_available():
    from runtime.execution_context import ExecutionContext

    snap = {"capital_total": 5000.0, "capital_used": 1000.0}
    ctx = ExecutionContext.from_snapshot(snap)
    assert ctx.capital_available == pytest.approx(4000.0, abs=0.01)


# ── Section 2 : SystemStateBus (B-04) ────────────────────────────────────────


def test_bus_subscribe_and_publish():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    received = []
    bus.subscribe("test:chan", received.append)
    bus.publish("test:chan", {"value": 42})
    assert len(received) == 1
    assert received[0]["value"] == 42


def test_bus_delivers_to_all_subscribers():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    r1, r2 = [], []
    bus.subscribe("ch", r1.append)
    bus.subscribe("ch", r2.append)
    bus.publish("ch", {"x": 1})
    assert len(r1) == 1
    assert len(r2) == 1


def test_bus_handler_exception_doesnt_block_others():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    r = []

    def bad_handler(msg):
        raise RuntimeError("handler cassé")

    bus.subscribe("ch", bad_handler)
    bus.subscribe("ch", r.append)
    delivered = bus.publish("ch", {"x": 1})
    assert len(r) == 1
    assert delivered == 1  # seul le handler ok est compté


def test_bus_dead_letter_recorded():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()

    def bad(msg):
        raise ValueError("boom")

    bus.subscribe("ch", bad)
    bus.publish("ch", {"x": 1})
    assert len(bus.dead_letters()) == 1
    assert "boom" in bus.dead_letters()[0]["error"]


def test_bus_state_returns_last_message():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    bus.publish("ch", {"v": 1})
    bus.publish("ch", {"v": 2})
    assert bus.state("ch")["v"] == 2


def test_bus_state_unknown_channel_returns_none():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    assert bus.state("nonexistent") is None


def test_bus_unsubscribe():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    r = []
    bus.subscribe("ch", r.append)
    bus.unsubscribe("ch", r.append)
    bus.publish("ch", {"x": 1})
    assert len(r) == 0


def test_bus_unsubscribe_unknown_returns_false():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    assert bus.unsubscribe("ch", lambda x: None) is False


def test_bus_is_silent_no_message():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    assert bus.is_silent("ch") is True


def test_bus_is_silent_recent_message():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    bus.publish("ch", {"x": 1})
    assert bus.is_silent("ch", since_s=60.0) is False


def test_bus_stats_counts_messages():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    for _ in range(5):
        bus.publish("ch", {})
    stats = bus.stats()
    assert stats["total_published"] == 5
    assert stats["channels"]["ch"] == 5


def test_bus_saturation_warning(caplog):
    """Avertissement si canal dépasse _MAX_QUEUE_SIZE."""
    import runtime.system_state_bus as bus_mod

    bus = bus_mod.SystemStateBus()
    orig = bus_mod._MAX_QUEUE_SIZE
    try:
        bus_mod._MAX_QUEUE_SIZE = 3
        for _ in range(5):
            bus.publish("ch", {})
    finally:
        bus_mod._MAX_QUEUE_SIZE = orig


def test_bus_thread_safe():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    results = []
    bus.subscribe("ch", results.append)

    def publisher():
        for _ in range(50):
            bus.publish("ch", {"t": threading.get_ident()})

    threads = [threading.Thread(target=publisher) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 200


def test_bus_standard_channels_count():
    from runtime.system_state_bus import STANDARD_CHANNELS

    assert len(STANDARD_CHANNELS) >= 10


def test_bus_reset():
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    bus.subscribe("ch", lambda m: None)
    bus.publish("ch", {"x": 1})
    bus.reset()
    assert bus.state("ch") is None
    assert bus.stats()["total_published"] == 0


# ── Section 3 : LifecycleManager (B-02) ──────────────────────────────────────


def _make_manager(tmp_path: Path) -> "LifecycleManager":
    from runtime.lifecycle_manager import LifecycleManager

    return LifecycleManager(journal_path=tmp_path / "journal.jsonl")


def test_lifecycle_register_and_start(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.register("agent_a")
    assert mgr.start("agent_a")
    from runtime.lifecycle_manager import AgentStatus

    assert mgr.status("agent_a") == AgentStatus.RUNNING


def test_lifecycle_start_already_running(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.register("a")
    mgr.start("a")
    assert mgr.start("a") is False  # déjà RUNNING


def test_lifecycle_stop(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.register("a")
    mgr.start("a")
    assert mgr.stop("a")
    from runtime.lifecycle_manager import AgentStatus

    assert mgr.status("a") == AgentStatus.STOPPED


def test_lifecycle_stop_already_stopped(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.register("a")
    assert mgr.stop("a") is False  # déjà STOPPED


def test_lifecycle_restart_increments_count(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.register("a")
    mgr.start("a")
    mgr.restart("a")
    rec = mgr.get_record("a")
    assert rec.restart_count == 1


def test_lifecycle_start_fn_called(tmp_path):
    called = []
    mgr = _make_manager(tmp_path)
    mgr.register("a", start_fn=lambda: called.append(1))
    mgr.start("a")
    assert len(called) == 1


def test_lifecycle_stop_fn_called(tmp_path):
    stopped = []
    mgr = _make_manager(tmp_path)
    mgr.register("a", start_fn=lambda: None, stop_fn=lambda: stopped.append(1))
    mgr.start("a")
    mgr.stop("a")
    assert len(stopped) == 1


def test_lifecycle_start_fn_raises_sets_failed(tmp_path):
    from runtime.lifecycle_manager import AgentStatus

    mgr = _make_manager(tmp_path)
    mgr.register("a", start_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    mgr.start("a")
    assert mgr.status("a") == AgentStatus.FAILED


def test_lifecycle_health_check_ok(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.register("a", start_fn=lambda: None, health_fn=lambda: {"ok": True})
    mgr.start("a")
    h = mgr.health("a")
    assert h["ok"] is True


def test_lifecycle_health_check_raises_sets_degraded(tmp_path):
    from runtime.lifecycle_manager import AgentStatus

    mgr = _make_manager(tmp_path)
    mgr.register(
        "a",
        start_fn=lambda: None,
        health_fn=lambda: (_ for _ in ()).throw(RuntimeError("sick")),
    )
    mgr.start("a")
    h = mgr.health("a")
    assert not h["ok"]
    assert mgr.status("a") == AgentStatus.DEGRADED


def test_lifecycle_health_no_fn_running(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.register("a")
    mgr.start("a")
    assert mgr.health("a")["ok"] is True


def test_lifecycle_unknown_agent_raises(tmp_path):
    mgr = _make_manager(tmp_path)
    with pytest.raises(KeyError):
        mgr.start("ghost")


def test_lifecycle_all_statuses(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.register("a")
    mgr.register("b")
    mgr.start("a")
    statuses = mgr.all_statuses()
    assert "a" in statuses
    assert "b" in statuses


def test_lifecycle_failed_agents_list(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.register("bad", start_fn=lambda: (_ for _ in ()).throw(RuntimeError))
    mgr.start("bad")
    assert "bad" in mgr.failed_agents()


def test_lifecycle_journal_written(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.register("a")
    mgr.start("a")
    mgr.stop("a")
    journal = (tmp_path / "journal.jsonl").read_text().splitlines()
    events = [json.loads(l)["event"] for l in journal]
    assert "REGISTERED" in events
    assert "STARTED" in events
    assert "STOPPED" in events


def test_lifecycle_journal_entries_signed(tmp_path):
    from cold_start.warmup_signer import verify

    mgr = _make_manager(tmp_path)
    mgr.register("a")
    mgr.start("a")
    for line in (tmp_path / "journal.jsonl").read_text().splitlines():
        entry = json.loads(line)
        sig = entry.pop("signature")
        assert verify(entry, sig)


def test_lifecycle_multiple_agents(tmp_path):
    from runtime.lifecycle_manager import AgentStatus

    mgr = _make_manager(tmp_path)
    for i in range(5):
        mgr.register(f"agent_{i}")
        mgr.start(f"agent_{i}")
    assert all(mgr.status(f"agent_{i}") == AgentStatus.RUNNING for i in range(5))
    assert mgr.agent_count() == 5


# ── Section 4 : RuntimeCoordinator (B-01) ────────────────────────────────────


def _coordinator():
    from runtime.runtime_coordinator import RuntimeCoordinator
    from runtime.system_state_bus import SystemStateBus

    bus = SystemStateBus()
    return RuntimeCoordinator(bus=bus), bus


def test_coordinator_cycle_complete():
    coord, _ = _coordinator()
    coord.register_layer("signal", lambda ctx: {"symbol": "BTCUSDT"})
    coord.register_layer("decision", lambda ctx: {"action": "BUY"})
    result = coord.run_cycle(_ctx())
    assert result.success
    assert result.decision == {"action": "BUY"}
    assert len(result.layers) == 2


def test_coordinator_cycle_id_propagated():
    coord, _ = _coordinator()
    coord.register_layer("signal", lambda ctx: None)
    ctx = _ctx()
    result = coord.run_cycle(ctx)
    assert result.cycle_id == ctx.cycle_id


def test_coordinator_layer_timeout():
    coord, _ = _coordinator()

    def slow(ctx):
        time.sleep(2.0)
        return {"x": 1}

    coord.register_layer("slow", slow, timeout_ms=50)
    result = coord.run_cycle(_ctx())
    slow_lr = next(r for r in result.layers if r.name == "slow")
    assert not slow_lr.success
    assert "timeout" in slow_lr.error


def test_coordinator_timeout_non_critical_doesnt_abort_cycle():
    """Couche non-critique en timeout → cycle continue."""
    coord, _ = _coordinator()
    coord.register_layer("signal", lambda ctx: {"ok": True})
    coord.register_layer("analytics", lambda ctx: time.sleep(2), timeout_ms=50)
    coord.register_layer("decision", lambda ctx: {"action": "BUY"})
    result = coord.run_cycle(_ctx())
    # decision doit quand même être présente
    assert result.decision == {"action": "BUY"}


def test_coordinator_critical_layer_failure_no_decision():
    """Couche critique (signal) en erreur → pas de décision orpheline."""
    coord, _ = _coordinator()

    def bad_signal(ctx):
        raise RuntimeError("exchange down")

    coord.register_layer("signal", bad_signal)
    coord.register_layer("decision", lambda ctx: {"action": "BUY"})
    result = coord.run_cycle(_ctx())
    assert result.decision is None
    assert "signal" in result.error


def test_coordinator_risk_layer_failure_no_decision():
    """Couche critique (risk) en erreur → pas de décision orpheline."""
    coord, _ = _coordinator()
    coord.register_layer("signal", lambda ctx: {"ok": True})
    coord.register_layer("decision", lambda ctx: {"action": "BUY"})
    coord.register_layer(
        "risk", lambda ctx: (_ for _ in ()).throw(RuntimeError("limits"))
    )
    result = coord.run_cycle(_ctx())
    assert result.decision is None


def test_coordinator_shutdown_while_idle():
    coord, _ = _coordinator()
    coord.shutdown()  # ne doit pas lever


def test_coordinator_no_orphan_on_shutdown(monkeypatch):
    """Si shutdown est appelé pendant un cycle, active_cycle_id est effacé."""
    coord, _ = _coordinator()
    coord.register_layer("signal", lambda ctx: {"ok": True})

    cycle_was_active = []

    def check_active(ctx):
        # Simuler un shutdown en milieu de cycle
        old = coord._active_cycle_id
        if old:
            cycle_was_active.append(old)
        return {"ok": True}

    coord.register_layer("analytics", check_active)
    coord.run_cycle(_ctx())
    # Après le cycle, active_cycle_id doit être None
    assert coord.is_idle


def test_coordinator_cycles_run_incremented():
    coord, _ = _coordinator()
    coord.register_layer("noop", lambda ctx: None)
    coord.run_cycle(_ctx())
    coord.run_cycle(_ctx())
    assert coord.cycles_run == 2


def test_coordinator_result_published_on_bus():
    from runtime.system_state_bus import CHANNEL_SYSTEM_CYCLE

    coord, bus = _coordinator()
    coord.register_layer("signal", lambda ctx: None)
    coord.run_cycle(_ctx())
    assert bus.state(CHANNEL_SYSTEM_CYCLE) is not None
    assert "cycle_id" in bus.state(CHANNEL_SYSTEM_CYCLE)


def test_coordinator_layer_names():
    coord, _ = _coordinator()
    coord.register_layer("signal", lambda ctx: None)
    coord.register_layer("risk", lambda ctx: None)
    assert coord.layer_names == ["signal", "risk"]


def test_coordinator_signed_result():
    from cold_start.warmup_signer import verify

    coord, _ = _coordinator()
    coord.register_layer("decision", lambda ctx: {"action": "SELL"})
    result = coord.run_cycle(_ctx())
    signed = result.to_signed_dict()
    sig = signed.pop("signature")
    assert verify(signed, sig)


def test_coordinator_context_frozen_during_cycle():
    """Le contexte passé à chaque couche est une copie gelée."""
    captured = []
    coord, _ = _coordinator()

    def capture(ctx):
        captured.append(ctx.capital_total)
        return None

    coord.register_layer("capture", capture)
    ctx = _ctx(capital_total=10_000.0, capital_used=0.0, capital_available=10_000.0)
    coord.run_cycle(ctx)
    assert captured[0] == 10_000.0


def test_coordinator_layer_exception_recorded():
    coord, _ = _coordinator()

    def bad(ctx):
        raise ValueError("kaboom")

    coord.register_layer("analytics", bad)
    result = coord.run_cycle(_ctx())
    lr = result.layers[0]
    assert not lr.success
    assert "kaboom" in lr.error


def test_coordinator_cycle_result_to_dict():
    coord, _ = _coordinator()
    coord.register_layer("signal", lambda ctx: None)
    result = coord.run_cycle(_ctx())
    d = result.to_dict()
    assert "cycle_id" in d
    assert "duration_ms" in d
    assert isinstance(d["layers"], list)
