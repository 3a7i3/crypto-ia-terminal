from __future__ import annotations

import logging
import time
from types import SimpleNamespace

import advisor_loop
import pytest
from advisor_runtime_adapters import AdvisorRuntime


@pytest.fixture(autouse=True)
def _bypass_instance_lock(monkeypatch):
    """Les smoke tests exercent main() sans avoir besoin du verrou d'instance."""
    monkeypatch.setattr(advisor_loop, "_acquire_instance_lock", lambda: None)
    monkeypatch.setattr(advisor_loop, "_release_instance_lock", lambda: None)


class _Stub:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def scan(self):
        return {"candles": [], "history": {}}


class _KillSwitch:
    def __init__(self, *args, **kwargs) -> None:
        self.safe_mode = False

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def is_halted(self) -> bool:
        return False

    def is_safe_mode(self) -> bool:
        return self.safe_mode


class _ExchangeMonitor:
    def __init__(self, *args, **kwargs) -> None:
        return None

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def is_healthy(self) -> bool:
        return True

    def snapshot(self) -> dict[str, object]:
        return {
            "healthy": True,
            "last_latency_ms": 0.0,
            "uptime_pct": 100.0,
            "consecutive_failures": 0,
            "last_error": "",
        }


class _Healer:
    def __init__(self, *args, **kwargs) -> None:
        return None

    def register_simple(self, *args, **kwargs) -> None:
        return None

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


class _ExecutionEngine:
    @classmethod
    def from_env(cls) -> "_ExecutionEngine":
        return cls()

    def fetch_available_capital(self) -> float:
        return 1000.0

    def has_futures_demo(self) -> bool:
        return False

    def fetch_futures_balance(self) -> float:
        return 0.0


class _PositionManager:
    def __init__(self, *args, **kwargs) -> None:
        self._callbacks = []

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def on_close(self, fn) -> None:
        self._callbacks.append(fn)

    def get_open(self) -> list[object]:
        return []

    def stats(self) -> dict[str, float]:
        return {
            "open_count": 0,
            "closed_count": 0,
            "total_pnl_usd": 0.0,
            "win_rate": 0.0,
            "open_pnl_usd": 0.0,
        }

    def snapshot(self) -> list[dict[str, object]]:
        return []

    def update_market_data(self, *args, **kwargs) -> None:
        return None

    def add_position(self, pos) -> None:
        return None


class _Ranker:
    def auto_demote(self) -> None:
        return None

    def leaderboard(self, n: int = 20) -> list[dict[str, object]]:
        return []


class _PortfolioBrain:
    def __init__(self, total_capital: float) -> None:
        self.total_capital = total_capital

    def update_capital(self, capital: float) -> None:
        self.total_capital = capital


class _CapitalAllocationEngine:
    def __init__(self, total_capital: float) -> None:
        self.total_capital = total_capital

    def update_capital(self, capital: float) -> None:
        self.total_capital = capital


class _MistakeMemory:
    def stats(self) -> dict[str, float]:
        return {"total": 0, "rules_active": 0, "error_rate": 0.0}


class _ExecutiveOverride:
    def __init__(self, *args, **kwargs) -> None:
        return None

    def update(self, **kwargs) -> None:
        return None

    def record_trade(self) -> None:
        return None


class _BlackBox:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.decisions: list[dict[str, object]] = []

    def record_system_event(self, kind: str, message: str) -> None:
        self.events.append((kind, message))

    def record_decision(self, payload: dict[str, object], cycle: int = 0) -> None:
        self.decisions.append({"cycle": cycle, **payload})


class _MetaLearner:
    def __init__(self) -> None:
        self.memory: list[object] = []


class _MetaStrategyEngine:
    def __init__(self, **kwargs) -> None:
        pass

    def current_personality(self):
        return None


class _Watchdog:
    class _Measure:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    def measure(self, name: str):
        return self._Measure()

    def end_cycle(self, cycle: int) -> None:
        return None


def _runtime() -> AdvisorRuntime:
    return AdvisorRuntime(
        MarketScanner=_Stub,
        MultiTimeframeScanner=_Stub,
        LiveSignalEngine=_Stub,
        GlobalRiskGate=_Stub,
        AIAdvisor=_Stub,
        ShadowExecutionEngine=_Stub,
        PerformanceWatchdog=_Watchdog,
        StrategyMemoryStore=_Stub,
        TelegramKillSwitch=_KillSwitch,
        ExchangeMonitor=_ExchangeMonitor,
        SelfHealingBot=_Healer,
        ExecutionEngine=_ExecutionEngine,
        PositionManager=_PositionManager,
        Position=_Stub,
        tracker_finalize_position=lambda *args, **kwargs: None,
        tracker_open_position=lambda *args, **kwargs: None,
        tracker_run_cycle=lambda *args, **kwargs: {},
        MetaStrategyEngine=_MetaStrategyEngine,
        StrategyRanker=_Ranker,
        SelfAwarenessEngine=_Stub,
        DangerLevel=SimpleNamespace(WARNING=1),
        NoTradeIntelligence=_Stub,
        ConvictionEngine=_Stub,
        DecisionQualityEngine=_Stub,
        PortfolioBrain=_PortfolioBrain,
        CapitalAllocationEngine=_CapitalAllocationEngine,
        MistakeMemory=_MistakeMemory,
        ExecutiveOverride=_ExecutiveOverride,
        BlackBox=_BlackBox,
        RegretEngine=_Stub,
        ChiefOfficer=_Stub,
        ThreatRadar=_Stub,
        MetaLearner=_MetaLearner,
        FeatureEngineer=_Stub,
        AdvancedRegimeDetector=_Stub,
        ConfidenceExplainer=_Stub,
        AdaptiveThresholdEngine=_Stub,
        RegimeTransitionSmoother=_Stub,
        RegimeStateTracker=_Stub,
    )


def _force_observation_mode(monkeypatch) -> None:
    monkeypatch.setenv("V9_ADVISOR_ONLY", "true")


def _force_live_mode(monkeypatch) -> None:
    monkeypatch.setenv("V9_ADVISOR_ONLY", "false")


def test_main_runs_single_cycle_in_observation_mode(monkeypatch):
    runtime = _runtime()
    calls: list[str] = []

    _force_observation_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: calls.append(text))

    def _fake_analyze_symbol(*args, **kwargs):
        return {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        }

    monkeypatch.setattr(advisor_loop, "analyze_symbol", _fake_analyze_symbol)

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    assert any("Crypto AI Terminal demarre" in text for text in calls)


def test_main_opens_real_position_path_and_updates_tracker(monkeypatch):
    tracker_open_calls: list[dict[str, object]] = []
    refresh_calls: list[dict[str, object]] = []
    added_positions: list[object] = []

    class _LiveExecutionEngine(_ExecutionEngine):
        @classmethod
        def from_env(cls) -> "_LiveExecutionEngine":
            return cls()

        def has_futures_demo(self) -> bool:
            return True

        def create_futures_order(
            self, symbol: str, side: str, size: float
        ) -> dict[str, object]:
            return {
                "mode": "futures_demo",
                "id": "demo-order-1",
                "symbol": symbol,
                "side": side,
                "usd_size": size,
                "status": "filled",
                "price": 100.0,
                "qty": 0.5,
            }

    class _LivePositionManager(_PositionManager):
        def add_position(self, pos) -> None:
            added_positions.append(pos)

    class _PositionFactory:
        @classmethod
        def from_futures_order(
            cls,
            fut,
            sym,
            signal,
            effective_size,
            tp_pct=0.04,
            sl_pct=0.02,
            trailing=0.0,
            atr=0.0,
            volatility=0.0,
            regime="unknown",
        ):
            return SimpleNamespace(
                order_id=str(fut.get("id", "demo-order-1")),
                symbol=sym,
                side=SimpleNamespace(
                    value="long" if str(signal).upper() == "BUY" else "short"
                ),
                entry_price=float(fut.get("price", 100.0)),
                current_price=float(fut.get("price", 100.0)),
                size_usd=float(effective_size),
                opened_at=time.time(),
                leverage=1,
                qty=float(fut.get("qty", 0.0)),
                tp_pct=float(tp_pct),
                sl_pct=float(sl_pct),
                trailing_pct=float(trailing),
                atr=float(atr),
                volatility=float(volatility),
                regime=regime,
            )

    runtime = _runtime()
    runtime = AdvisorRuntime(
        **{
            **runtime.__dict__,
            "ExecutionEngine": _LiveExecutionEngine,
            "PositionManager": _LivePositionManager,
            "Position": _PositionFactory,
            "tracker_open_position": lambda **kwargs: tracker_open_calls.append(kwargs),
            "tracker_run_cycle": lambda *args, **kwargs: refresh_calls.append(
                dict(kwargs)
            ),
        }
    )

    _force_live_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "prix": 100.0,
            "signal": SimpleNamespace(
                actionable=True,
                signal="BUY",
                score=82,
                timestamp=time.time(),
                regime="bull_trend",
                confirmed=True,
                strength=0.8,
                components={},
            ),
            "gate": SimpleNamespace(allowed=True),
            "features": {"atr": 1.2, "atr_ratio": 0.03},
            "allocation": None,
            "trade_allowed": True,
            "ml_decision": {"tp": 0.03, "sl": 0.01, "trail_pct": 0.005},
            "futures_result": None,
            "regime": "bullish",
            "personality": None,
            "conviction": None,
            "decision_packet": SimpleNamespace(is_actionable=lambda: True),
        },
    )

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    assert len(added_positions) == 1
    assert len(tracker_open_calls) == 1
    assert tracker_open_calls[0]["symbol"] == "BTC/USDT"
    assert tracker_open_calls[0]["side"] == "BUY"
    assert tracker_open_calls[0]["regime"] == "bullish"
    assert tracker_open_calls[0]["source"] == "advisor_loop"
    assert refresh_calls == [{"run_optimizer": False}]


def test_main_opens_position_when_paper_execution_is_used(monkeypatch):
    tracker_open_calls: list[dict[str, object]] = []
    added_positions: list[object] = []
    order_calls: list[tuple[str, str, float]] = []

    class _PaperExecutionEngine(_ExecutionEngine):
        @classmethod
        def from_env(cls) -> "_PaperExecutionEngine":
            return cls()

        def has_futures_demo(self) -> bool:
            return False

        def create_order(
            self, symbol: str, side: str, size: float
        ) -> dict[str, object]:
            order_calls.append((symbol, side, size))
            return {
                "mode": "paper",
                "id": "paper-order-1",
                "symbol": symbol,
                "action": side,
                "size": size,
                "price": 101.5,
            }

    class _LivePositionManager(_PositionManager):
        def add_position(self, pos) -> None:
            added_positions.append(pos)

    class _PositionFactory:
        @classmethod
        def from_futures_order(
            cls,
            fut,
            sym,
            signal,
            effective_size,
            tp_pct=0.04,
            sl_pct=0.02,
            trailing=0.0,
            atr=0.0,
            volatility=0.0,
            regime="unknown",
        ):
            entry_price = float(fut.get("price", 0.0))
            qty = float(
                fut.get("amount", 0.0)
                or (effective_size / entry_price if entry_price else 0.0)
            )
            return SimpleNamespace(
                order_id=str(fut.get("id", "paper-order-1")),
                symbol=sym,
                side=SimpleNamespace(
                    value="long" if str(signal).upper() == "BUY" else "short"
                ),
                entry_price=entry_price,
                current_price=entry_price,
                size_usd=float(effective_size),
                opened_at=time.time(),
                leverage=1,
                qty=qty,
                tp_pct=float(tp_pct),
                sl_pct=float(sl_pct),
                trailing_pct=float(trailing),
                atr=float(atr),
                volatility=float(volatility),
                regime=regime,
            )

    runtime = _runtime()
    runtime = AdvisorRuntime(
        **{
            **runtime.__dict__,
            "ExecutionEngine": _PaperExecutionEngine,
            "PositionManager": _LivePositionManager,
            "Position": _PositionFactory,
            "tracker_open_position": lambda **kwargs: tracker_open_calls.append(kwargs),
        }
    )

    _force_live_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=True,
                signal="BUY",
                score=82,
                timestamp=time.time(),
                regime="bull_trend",
                confirmed=True,
                strength=0.8,
                components={},
            ),
            "gate": SimpleNamespace(allowed=True),
            "features": {"atr": 1.2, "atr_ratio": 0.03},
            "allocation": None,
            "trade_allowed": True,
            "ml_decision": {"tp": 0.03, "sl": 0.01, "trail_pct": 0.005},
            "futures_result": None,
            "regime": "bullish",
            "personality": None,
            "conviction": None,
            "prix": 101.5,
            "decision_packet": SimpleNamespace(is_actionable=lambda: True),
        },
    )

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    # L'order validator ajuste la qty (step_size MEXC) — tolérance ±1 USD
    assert len(order_calls) == 1
    assert order_calls[0][0] == "BTC/USDT"
    assert order_calls[0][1] == "BUY"
    assert abs(order_calls[0][2] - 10.0) < 1.0
    assert len(added_positions) == 1
    assert len(tracker_open_calls) == 1
    assert tracker_open_calls[0]["price"] == 101.5
    assert tracker_open_calls[0]["side"] == "BUY"
    assert tracker_open_calls[0]["source"] == "advisor_loop"


def test_main_refreshes_tracker_pipeline_on_position_close(monkeypatch):
    refresh_calls: list[dict[str, object]] = []

    class _CapturingPositionManager(_PositionManager):
        last_instance: "_CapturingPositionManager | None" = None

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            _CapturingPositionManager.last_instance = self

    runtime = _runtime()
    runtime = AdvisorRuntime(
        **{
            **runtime.__dict__,
            "PositionManager": _CapturingPositionManager,
            "tracker_run_cycle": lambda *args, **kwargs: refresh_calls.append(
                dict(kwargs)
            ),
        }
    )

    _force_observation_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        },
    )

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    manager = _CapturingPositionManager.last_instance
    assert manager is not None
    assert len(manager._callbacks) >= 1

    position = SimpleNamespace(
        order_id="pos-1",
        symbol="BTC/USDT",
        current_price=101.0,
        entry_price=100.0,
        pnl_usd=1.0,
        pnl_pct=0.01,
        subaccount="main",
        opened_at=time.time() - 60,
        side=SimpleNamespace(value="long"),
        size_usd=10.0,
        signal_score=80.0,
        highest_price=101.0,
        lowest_price=99.5,
    )

    manager._callbacks[0](position, SimpleNamespace(value="tp"))

    assert refresh_calls == [{"run_optimizer": False}]


def test_main_uses_configured_1h_scanner_limit(monkeypatch):
    created: list[dict[str, object]] = []

    class _RecorderScanner(_Stub):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            created.append(kwargs)

    runtime = _runtime()
    runtime = AdvisorRuntime(**{**runtime.__dict__, "MarketScanner": _RecorderScanner})

    _force_observation_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "ADVISOR_1H_LIMIT", 96)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        },
    )

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    one_hour_scanners = [item for item in created if item.get("timeframe") == "1h"]
    assert one_hour_scanners
    assert one_hour_scanners[0]["limit"] == 96


def test_main_prewarms_one_hour_scanners(monkeypatch):
    scan_calls: list[str] = []

    class _WarmScanner(_Stub):
        def scan(self):
            timeframe = self.kwargs.get("timeframe")
            if timeframe == "1h":
                scan_calls.append("1h")
            return {"candles": [], "history": {"BTC/USDT": []}}

    runtime = _runtime()
    runtime = AdvisorRuntime(**{**runtime.__dict__, "MarketScanner": _WarmScanner})

    _force_observation_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "ADVISOR_PREWARM_1H", True)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        },
    )

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    # prewarm boot + parallel pre-scan par cycle = au moins 2 appels 1h
    assert scan_calls.count("1h") >= 2


def test_main_skips_live_execution_bootstrap_in_observation_mode(monkeypatch):
    events: list[str] = []

    class _ExecEngineNoLive(_ExecutionEngine):
        def __init__(self) -> None:
            events.append("ctor")

        @classmethod
        def from_env(cls):
            events.append("from_env")
            return cls()

    runtime = _runtime()
    runtime = AdvisorRuntime(
        **{**runtime.__dict__, "ExecutionEngine": _ExecEngineNoLive}
    )

    _force_observation_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "ADVISOR_LIVE_EXECUTION_BOOTSTRAP", False)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        },
    )

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    assert events == ["ctor"]


def test_main_skips_background_position_watch_in_observation_mode(monkeypatch):
    events: list[str] = []

    class _SilentPositionManager(_PositionManager):
        def start(self) -> None:
            events.append("start")

    runtime = _runtime()
    runtime = AdvisorRuntime(
        **{**runtime.__dict__, "PositionManager": _SilentPositionManager}
    )

    _force_observation_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "ADVISOR_BACKGROUND_POSITION_WATCH", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_LIVE_EXECUTION_BOOTSTRAP", False)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        },
    )

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    assert events == []


def test_main_defers_optional_intel_in_observation_hold_cycle(monkeypatch):
    events: list[str] = []

    class _DeferredMistakeMemory(_MistakeMemory):
        def __init__(self) -> None:
            events.append("mistake")

    class _DeferredRegretEngine(_Stub):
        def __init__(self, *args, **kwargs) -> None:
            events.append("regret")

    class _DeferredChiefOfficer(_Stub):
        def __init__(self, *args, **kwargs) -> None:
            events.append("chief")

    runtime = _runtime()
    runtime = AdvisorRuntime(
        **{
            **runtime.__dict__,
            "MistakeMemory": _DeferredMistakeMemory,
            "RegretEngine": _DeferredRegretEngine,
            "ChiefOfficer": _DeferredChiefOfficer,
        }
    )

    _force_observation_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "ADVISOR_DEFER_OPTIONAL_INTEL", True)
    monkeypatch.setattr(advisor_loop, "ADVISOR_BACKGROUND_POSITION_WATCH", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_LIVE_EXECUTION_BOOTSTRAP", False)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        },
    )

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    assert events == []


def test_main_reports_bootstrap_detail(monkeypatch, caplog):
    runtime = _runtime()

    _force_observation_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "ADVISOR_PREWARM_1H", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_BACKGROUND_POSITION_WATCH", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_LIVE_EXECUTION_BOOTSTRAP", False)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        },
    )

    with caplog.at_level(logging.INFO, logger="advisor_loop"):
        advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    assert any(
        record.message.startswith("[Timing] Bootstrap detail:")
        for record in caplog.records
    )


def test_main_defers_post_cycle_services_for_single_observation_cycle(monkeypatch):
    events: list[str] = []

    class _DeferredExchangeMonitor(_ExchangeMonitor):
        def start(self) -> None:
            events.append("exchange_start")

    class _DeferredHealer(_Healer):
        def start(self) -> None:
            events.append("healer_start")

    runtime = _runtime()
    runtime = AdvisorRuntime(
        **{
            **runtime.__dict__,
            "ExchangeMonitor": _DeferredExchangeMonitor,
            "SelfHealingBot": _DeferredHealer,
        }
    )

    _force_observation_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "ADVISOR_DEFER_POST_CYCLE_SERVICES", True)
    monkeypatch.setattr(advisor_loop, "ADVISOR_PREWARM_1H", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_BACKGROUND_POSITION_WATCH", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_LIVE_EXECUTION_BOOTSTRAP", False)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        },
    )

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    assert events == []


def test_main_starts_kill_switch_after_first_cycle_when_deferred(monkeypatch):
    events: list[str] = []
    analyze_calls = {"count": 0}

    class _DeferredKillSwitch(_KillSwitch):
        def start(self) -> None:
            events.append("kill_switch_start")

    runtime = _runtime()
    runtime = AdvisorRuntime(
        **{
            **runtime.__dict__,
            "TelegramKillSwitch": _DeferredKillSwitch,
        }
    )

    _force_observation_mode(monkeypatch)
    monkeypatch.setenv("UNIVERSE_ENABLED", "false")
    monkeypatch.setattr(advisor_loop, "ADVISOR_DEFER_POST_CYCLE_SERVICES", True)
    monkeypatch.setattr(advisor_loop, "ADVISOR_PREWARM_1H", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_BACKGROUND_POSITION_WATCH", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_LIVE_EXECUTION_BOOTSTRAP", False)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)

    def _fake_analyze_symbol(*args, **kwargs):
        analyze_calls["count"] += 1
        events.append(f"analyze_{analyze_calls['count']}")
        return {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        }

    monkeypatch.setattr(advisor_loop, "analyze_symbol", _fake_analyze_symbol)

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=2, runtime=runtime)

    assert events == ["analyze_1", "kill_switch_start", "analyze_2"]


def test_main_startup_light_overrides_heavy_observation_flags(monkeypatch):
    events: list[str] = []

    class _ExecEngineNoLive(_ExecutionEngine):
        def __init__(self) -> None:
            events.append("ctor")

        @classmethod
        def from_env(cls):
            events.append("from_env")
            return cls()

    class _SilentPositionManager(_PositionManager):
        def start(self) -> None:
            events.append("position_start")

    class _DeferredMistakeMemory(_MistakeMemory):
        def __init__(self) -> None:
            events.append("mistake")

    class _DeferredRegretEngine(_Stub):
        def __init__(self, *args, **kwargs) -> None:
            events.append("regret")

    class _DeferredExchangeMonitor(_ExchangeMonitor):
        def start(self) -> None:
            events.append("exchange_start")

    class _DeferredHealer(_Healer):
        def start(self) -> None:
            events.append("healer_start")

    runtime = _runtime()
    runtime = AdvisorRuntime(
        **{
            **runtime.__dict__,
            "ExecutionEngine": _ExecEngineNoLive,
            "PositionManager": _SilentPositionManager,
            "MistakeMemory": _DeferredMistakeMemory,
            "RegretEngine": _DeferredRegretEngine,
            "ExchangeMonitor": _DeferredExchangeMonitor,
            "SelfHealingBot": _DeferredHealer,
        }
    )

    _force_observation_mode(monkeypatch)
    monkeypatch.setattr(advisor_loop, "ADVISOR_STARTUP_LIGHT", True)
    monkeypatch.setattr(advisor_loop, "ADVISOR_LIVE_EXECUTION_BOOTSTRAP", True)
    monkeypatch.setattr(advisor_loop, "ADVISOR_BACKGROUND_POSITION_WATCH", True)
    monkeypatch.setattr(advisor_loop, "ADVISOR_DEFER_OPTIONAL_INTEL", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_DEFER_POST_CYCLE_SERVICES", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_PREWARM_1H", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_PREWARM_MTF", True)
    monkeypatch.setattr(advisor_loop, "ADVISOR_PERSISTENT_WARMUP", True)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)
    monkeypatch.setattr(
        advisor_loop,
        "analyze_symbol",
        lambda *args, **kwargs: {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        },
    )

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=1, runtime=runtime)

    assert events == ["ctor"]


def test_main_throttles_threat_radar_by_cycle(monkeypatch):
    threat_radar_by_cycle: list[object | None] = []
    runtime = _runtime()

    _force_observation_mode(monkeypatch)
    monkeypatch.setenv("UNIVERSE_ENABLED", "false")
    monkeypatch.setattr(advisor_loop, "ADVISOR_STARTUP_LIGHT", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_PREWARM_1H", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_BACKGROUND_POSITION_WATCH", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_LIVE_EXECUTION_BOOTSTRAP", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_DEFER_POST_CYCLE_SERVICES", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_THREAT_RADAR_EVERY", 2)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)

    def _fake_analyze_symbol(*args, **kwargs):
        threat_radar_by_cycle.append(kwargs.get("threat_radar"))
        return {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        }

    monkeypatch.setattr(advisor_loop, "analyze_symbol", _fake_analyze_symbol)

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=2, runtime=runtime)

    assert threat_radar_by_cycle[0] is None
    assert threat_radar_by_cycle[1] is not None


def test_main_sheds_optional_work_after_over_budget_cycle(monkeypatch):
    threat_radar_by_cycle: list[object | None] = []
    runtime = _runtime()

    _force_observation_mode(monkeypatch)
    monkeypatch.setenv(
        "UNIVERSE_ENABLED", "false"
    )  # évite injection symboles MEXC depuis perp_universe.json
    monkeypatch.setattr(advisor_loop, "ADVISOR_STARTUP_LIGHT", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_PREWARM_1H", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_BACKGROUND_POSITION_WATCH", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_LIVE_EXECUTION_BOOTSTRAP", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_DEFER_POST_CYCLE_SERVICES", False)
    monkeypatch.setattr(advisor_loop, "ADVISOR_THREAT_RADAR_EVERY", 1)
    monkeypatch.setattr(advisor_loop, "ADVISOR_CYCLE_BUDGET_SECONDS", 0.001)
    monkeypatch.setattr(advisor_loop, "ADVISOR_LOAD_SHED_CYCLES", 1)
    monkeypatch.setattr(advisor_loop, "NOTIFY_EVERY", 99)
    monkeypatch.setattr(advisor_loop, "_telegram", lambda text: None)

    def _fake_analyze_symbol(*args, **kwargs):
        threat_radar_by_cycle.append(kwargs.get("threat_radar"))
        time.sleep(0.01)
        return {
            "symbol": "BTC/USDT",
            "signal": SimpleNamespace(
                actionable=False, signal="HOLD", score=40, timestamp=time.time()
            ),
            "gate": SimpleNamespace(allowed=False),
            "features": {},
            "allocation": None,
            "trade_allowed": False,
            "ml_decision": {},
            "futures_result": None,
        }

    monkeypatch.setattr(advisor_loop, "analyze_symbol", _fake_analyze_symbol)

    advisor_loop.main(["BTC/USDT"], interval=0, max_cycles=2, runtime=runtime)

    assert threat_radar_by_cycle[0] is not None
    assert threat_radar_by_cycle[1] is None
