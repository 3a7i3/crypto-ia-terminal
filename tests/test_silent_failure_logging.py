from __future__ import annotations

import builtins
import logging
from types import SimpleNamespace

from paper_trading.engine import PaperTradingEngine
from paper_trading.ledger import PaperTrade
from health.health_registry import HealthRegistry
from observability.heartbeat_system import HeartbeatSystem
from observability.metrics_bus import MetricsBus
from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine
from quant_hedge_ai.agents.execution.position_manager import (
    CloseReason,
    Position,
    PositionManager,
    PositionSide,
)
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


def test_heartbeat_errors_are_logged(monkeypatch, caplog):
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

        def simulate_monitor_failure() -> None:
            heartbeat._running = False
            raise RuntimeError("monitor boom")

        monkeypatch.setattr(heartbeat, "_check_all", simulate_monitor_failure)
        monkeypatch.setattr("observability.heartbeat_system.time.sleep", lambda _: None)
        heartbeat._running = True
        heartbeat._monitor_loop()

    assert death_seen == ["signal_engine"]
    assert revival_seen == ["signal_engine"]
    assert "Heartbeat death callback failed for signal_engine" in caplog.text
    assert "Heartbeat revival callback failed for signal_engine" in caplog.text
    assert "Heartbeat monitor loop failed" in caplog.text


def test_execution_engine_leverage_failures_are_logged(monkeypatch, caplog):
    logged_orders: list[dict] = []

    class _FakeTradeLogger:
        def __init__(self, db_path: str) -> None:
            self.db_path = db_path

        def log(self, payload: dict) -> None:
            logged_orders.append(payload)

    monkeypatch.setattr(
        "quant_hedge_ai.agents.execution.execution_engine.TradeLogger",
        _FakeTradeLogger,
    )
    engine = ExecutionEngine(live=False)

    class _FakeFuturesExchange:
        def set_leverage(self, leverage: int, symbol: str) -> None:
            raise RuntimeError("leverage boom")

        def fetch_ticker(self, symbol: str) -> dict:
            return {"last": 100.0}

        def load_markets(self) -> dict:
            return {
                "BTC/USDT:USDT": {
                    "precision": {"amount": 0.001},
                    "limits": {"amount": {"min": 0.001}},
                }
            }

        def create_order(self, symbol: str, order_type: str, side: str, qty: float) -> dict:
            return {"id": "ord-1", "symbol": symbol, "type": order_type, "side": side, "amount": qty}

    engine._exchange_futures = _FakeFuturesExchange()

    with caplog.at_level(
        logging.ERROR, logger="quant_hedge_ai.agents.execution.execution_engine"
    ):
        order = engine.create_futures_order("BTC/USDT", "BUY", 60.0, leverage=3)

    assert order["mode"] == "futures_demo"
    assert logged_orders and logged_orders[0]["mode"] == "futures_demo"
    assert "set_leverage failed for BTC/USDT:USDT (lev x3)" in caplog.text


def test_execution_engine_futures_market_metadata_fallback_is_logged(monkeypatch, caplog):
    logged_orders: list[dict] = []

    class _FakeTradeLogger:
        def __init__(self, db_path: str) -> None:
            self.db_path = db_path

        def log(self, payload: dict) -> None:
            logged_orders.append(payload)

    monkeypatch.setattr(
        "quant_hedge_ai.agents.execution.execution_engine.TradeLogger",
        _FakeTradeLogger,
    )
    engine = ExecutionEngine(live=False)

    class _FakeFuturesExchange:
        def fetch_ticker(self, symbol: str) -> dict:
            return {"last": 100.0}

        def load_markets(self) -> dict:
            raise RuntimeError("markets boom")

        def create_order(self, symbol: str, order_type: str, side: str, qty: float) -> dict:
            return {"id": "ord-2", "symbol": symbol, "type": order_type, "side": side, "amount": qty}

    engine._exchange_futures = _FakeFuturesExchange()

    with caplog.at_level(
        logging.ERROR, logger="quant_hedge_ai.agents.execution.execution_engine"
    ):
        order = engine.create_futures_order("BTC/USDT", "BUY", 60.0)

    assert order["mode"] == "futures_demo"
    assert logged_orders and logged_orders[0]["mode"] == "futures_demo"
    assert (
        "Futures market metadata unavailable for BTC/USDT:USDT; using default sizing"
        in caplog.text
    )


def test_execution_engine_live_market_metadata_fallback_is_logged(caplog):
    engine = ExecutionEngine(live=False)

    class _FakeExchange:
        def fetch_ticker(self, symbol: str) -> dict:
            return {"last": 100.0}

        def load_markets(self) -> dict:
            raise RuntimeError("live markets boom")

        def fetch_balance(self) -> dict:
            return {"free": {"USDT": 1000.0}}

        def create_order(self, symbol: str, order_type: str, side: str, qty: float) -> dict:
            return {"id": "ord-live-1", "symbol": symbol, "type": order_type, "side": side, "amount": qty}

    engine._exchange = _FakeExchange()

    with caplog.at_level(
        logging.ERROR, logger="quant_hedge_ai.agents.execution.execution_engine"
    ):
        order = engine._place_live_order("BTCUSDT", "BUY", 50.0)

    assert order["mode"] == "live"
    assert "Live market metadata unavailable for BTC/USDT; using default sizing" in caplog.text


def test_position_manager_close_callback_errors_are_logged(caplog):
    manager = PositionManager(paper_mode=True)
    position = Position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        entry_price=100.0,
        size_usd=100.0,
        qty=1.0,
    )

    seen: list[tuple[str, str]] = []

    def broken_callback(pos: Position, reason: CloseReason) -> None:
        seen.append((pos.symbol, reason.value))
        raise RuntimeError("close callback boom")

    manager.on_close(broken_callback)

    with caplog.at_level(
        logging.ERROR, logger="quant_hedge_ai.agents.execution.position_manager"
    ):
        manager._close_position(position, CloseReason.MANUAL)

    assert position.closed is True
    assert seen == [("BTCUSDT", "manual")]
    assert "Close callback failed for BTCUSDT (manual)" in caplog.text


def test_position_manager_liquidation_alert_errors_are_logged(monkeypatch, caplog):
    manager = PositionManager(paper_mode=True)
    position = Position(
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        entry_price=100.0,
        size_usd=100.0,
        qty=1.0,
        leverage=10,
    )
    position.update_price(100.0)

    class _BrokenNotifier:
        def send(self, message: str) -> None:
            raise RuntimeError("telegram boom")

    original_import = builtins.__import__

    def _import_with_broken_notifier(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "supervision.notifications.telegram_notifier":
            return SimpleNamespace(TelegramNotifier=_BrokenNotifier)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import_with_broken_notifier)

    with caplog.at_level(
        logging.ERROR, logger="quant_hedge_ai.agents.execution.position_manager"
    ):
        manager._check_liquidation_defense(position)

    assert "Telegram liquidation alert failed for ETHUSDT" in caplog.text
