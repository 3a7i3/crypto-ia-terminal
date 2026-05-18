from __future__ import annotations

import builtins
import logging

from paper_trading.engine import PaperTradingEngine
from paper_trading.ledger import PaperTrade
from health.health_registry import HealthRegistry
from observability.heartbeat_system import HeartbeatSystem
from observability.metrics_bus import MetricsBus
from health.recovery_manager import RecoveryManager, RecoveryOutcome, RecoveryStrategy
from system.module_registry import ModulePriority, ModuleRegistry, ModuleStatus
from system.state_manager import StateManager, SystemState


class _SuccessStrategy(RecoveryStrategy):
    @property
    def name(self) -> str:
        return "success"

    def execute(self, module: str, attempt: int) -> RecoveryOutcome:
        return RecoveryOutcome.SUCCESS


def test_state_transition_listener_errors_are_logged(caplog):
    manager = StateManager()
    transitions: list[tuple[SystemState, SystemState, str]] = []

    def listener(old: SystemState, new: SystemState, reason: str) -> None:
        transitions.append((old, new, reason))
        raise RuntimeError("listener boom")

    manager.on_transition(listener)

    with caplog.at_level(logging.ERROR, logger="system.state_manager"):
        manager.transition(SystemState.SYNCING, "boot sequence")

    assert manager.state == SystemState.SYNCING
    assert transitions == [(SystemState.BOOTING, SystemState.SYNCING, "boot sequence")]
    assert "State transition listener failed for BOOTING -> SYNCING" in caplog.text


def test_module_status_listener_errors_are_logged(caplog):
    registry = ModuleRegistry()
    seen: list[tuple[str, ModuleStatus]] = []

    def listener(name: str, status: ModuleStatus) -> None:
        seen.append((name, status))
        raise RuntimeError("status boom")

    registry.on_status_change(listener)
    registry.register("risk_engine", priority=ModulePriority.CRITICAL)

    with caplog.at_level(logging.ERROR, logger="system.module_registry"):
        registry.set_status("risk_engine", ModuleStatus.HEALTHY, "booted")

    assert registry.get("risk_engine").status == ModuleStatus.HEALTHY
    assert seen == [("risk_engine", ModuleStatus.HEALTHY)]
    assert "Module status listener failed for risk_engine -> HEALTHY" in caplog.text


def test_recovery_callback_errors_are_logged(caplog):
    manager = RecoveryManager()
    manager.register_strategy("signal_engine", _SuccessStrategy())

    def broken_callback(event) -> None:
        raise RuntimeError("callback boom")

    manager.on_recovery_event(broken_callback)

    with caplog.at_level(logging.ERROR, logger="health.recovery_manager"):
        outcome = manager.recover("signal_engine", "listener failed")

    assert outcome == RecoveryOutcome.SUCCESS
    assert "Recovery callback failed for signal_engine (SUCCESS)" in caplog.text


def test_health_registry_loop_errors_are_logged(monkeypatch, caplog):
    registry = HealthRegistry()
    calls = {"count": 0}

    def boom() -> None:
        calls["count"] += 1
        registry._running = False
        raise RuntimeError("check loop boom")

    monkeypatch.setattr(registry, "check_all", boom)
    monkeypatch.setattr("health.health_registry.time.sleep", lambda _: None)
    registry._running = True

    with caplog.at_level(logging.ERROR, logger="health.health_registry"):
        registry._run_loop()

    assert calls["count"] == 1
    assert "Health registry polling loop failed" in caplog.text


def test_paper_trading_audit_failures_are_logged(monkeypatch, tmp_path, caplog):
    engine = PaperTradingEngine(simulator=object(), log_path=str(tmp_path / "paper.jsonl"))
    trade = PaperTrade(
        trade_id="abc123",
        symbol="BTCUSDT",
        side="buy",
        size_usd=100.0,
        signal_price=100.0,
        entry_price=100.0,
        entry_slippage_bps=0.0,
        entry_latency_ms=0.0,
        entry_fee_usd=0.0,
        entry_ts=1.0,
    )

    def broken_open(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(builtins, "open", broken_open)

    with caplog.at_level(logging.ERROR, logger="paper_trading.engine"):
        engine._log(trade)

    assert "Failed to append paper trading audit log for BTCUSDT (abc123)" in caplog.text


def test_metrics_bus_listener_errors_are_logged(caplog):
    bus = MetricsBus()

    def broken_listener(module: str, metric: str, value: float) -> None:
        raise RuntimeError("metrics boom")

    bus.subscribe(broken_listener)

    with caplog.at_level(logging.ERROR, logger="observability.metrics_bus"):
        bus.gauge("signal_engine", "score", 0.91)

    assert "Metrics listener failed for signal_engine.score" in caplog.text


def test_heartbeat_system_loop_and_callbacks_are_logged(monkeypatch, caplog):
    heartbeat = HeartbeatSystem()
    heartbeat.register("signal_engine", timeout_sec=0.1)

    death_seen: list[str] = []
    revival_seen: list[str] = []

    def broken_death(module: str) -> None:
        death_seen.append(module)
        raise RuntimeError("death boom")

    def broken_revival(module: str) -> None:
        revival_seen.append(module)
        raise RuntimeError("revival boom")

    heartbeat.on_death(broken_death)
    heartbeat.on_revival(broken_revival)

    with caplog.at_level(logging.ERROR, logger="observability.heartbeat_system"):
        heartbeat._on_death("signal_engine")
        heartbeat._on_revival("signal_engine")

        def boom() -> None:
            heartbeat._running = False
            raise RuntimeError("monitor boom")

        monkeypatch.setattr(heartbeat, "_check_all", boom)
        monkeypatch.setattr("observability.heartbeat_system.time.sleep", lambda _: None)
        heartbeat._running = True
        heartbeat._monitor_loop()

    assert death_seen == ["signal_engine"]
    assert revival_seen == ["signal_engine"]
    assert "Heartbeat death callback failed for signal_engine" in caplog.text
    assert "Heartbeat revival callback failed for signal_engine" in caplog.text
    assert "Heartbeat monitor loop failed" in caplog.text
