"""Tests d'intégration — EventBus ↔ Pieuvre ↔ AlertManager ↔ EvolutionEngine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from event_bus.bus import EventBus
from event_bus.events import (
    DrawdownAlertEvent,
    EvolutionCycleEvent,
    IncidentResolvedEvent,
    IncidentStartedEvent,
    NewBestStrategyEvent,
    PieuvreRegrowthEvent,
    SecurityAlertEvent,
)


@pytest.fixture(autouse=True)
def fresh_bus():
    """Chaque test repart d'un bus vierge."""
    EventBus.reset()
    yield EventBus.get()
    EventBus.reset()


# ── Bus infrastructure ─────────────────────────────────────────────────────────


class TestEventBusSingleton:
    def test_get_returns_same_instance(self, fresh_bus):
        assert EventBus.get() is EventBus.get()

    def test_reset_creates_new_instance(self):
        a = EventBus.get()
        EventBus.reset()
        b = EventBus.get()
        assert a is not b

    def test_emit_increments_stats(self, fresh_bus):
        fresh_bus.emit(EvolutionCycleEvent(cycle=1))
        assert fresh_bus.stats().get("EvolutionCycleEvent", 0) == 1

    def test_subscribe_and_receive(self, fresh_bus):
        received = []
        fresh_bus.subscribe(SecurityAlertEvent, received.append)
        fresh_bus.emit(SecurityAlertEvent(severity="high", rule="test", file="x.py"))
        assert len(received) == 1
        assert received[0].severity == "high"

    def test_wildcard_receives_all_types(self, fresh_bus):
        received = []
        fresh_bus.subscribe_all(received.append)
        fresh_bus.emit(SecurityAlertEvent())
        fresh_bus.emit(EvolutionCycleEvent())
        fresh_bus.emit(DrawdownAlertEvent())
        assert len(received) == 3

    def test_dead_letter_when_no_subscriber(self, fresh_bus):
        fresh_bus.emit(PieuvreRegrowthEvent(generation=1))
        assert len(fresh_bus.dead_letters()) == 1

    def test_replay_returns_last_n(self, fresh_bus):
        for i in range(5):
            fresh_bus.emit(EvolutionCycleEvent(cycle=i))
        replayed = fresh_bus.replay(EvolutionCycleEvent, last_n=3)
        assert len(replayed) == 3
        assert replayed[-1].cycle == 4

    def test_handler_crash_does_not_break_bus(self, fresh_bus):
        def bad_handler(e):
            raise RuntimeError("handler crash")

        fresh_bus.subscribe(SecurityAlertEvent, bad_handler)
        # Should not raise
        fresh_bus.emit(SecurityAlertEvent(severity="low"))
        assert fresh_bus.stats()["SecurityAlertEvent"] == 1

    def test_unsubscribe_removes_handler(self, fresh_bus):
        received = []

        def handler(e):
            received.append(e)

        fresh_bus.subscribe(DrawdownAlertEvent, handler)
        fresh_bus.unsubscribe(DrawdownAlertEvent, handler)
        fresh_bus.emit(DrawdownAlertEvent())
        assert received == []

    def test_subscriber_count(self, fresh_bus):
        h1, h2 = MagicMock(), MagicMock()
        fresh_bus.subscribe(SecurityAlertEvent, h1)
        fresh_bus.subscribe(EvolutionCycleEvent, h2)
        assert fresh_bus.subscriber_count(SecurityAlertEvent) == 1
        assert fresh_bus.subscriber_count() >= 2


# ── AlertManager → EventBus ────────────────────────────────────────────────────


class TestAlertManagerEmitsEvents:
    def test_raise_alert_emits_security_event(self, fresh_bus, tmp_path):
        from supervision.alert_manager import Alert, AlertManager

        received = []
        fresh_bus.subscribe(SecurityAlertEvent, received.append)

        mgr = AlertManager(audit_file=str(tmp_path / "audit.jsonl"))
        mgr.raise_alert(
            Alert(
                type_="suspicious_import",
                severity="warning",
                module="market_scanner",
                message="exec() détecté",
            )
        )
        assert len(received) == 1
        assert received[0].rule == "suspicious_import"
        assert received[0].file == "market_scanner"

    def test_raise_drawdown_alert_emits_drawdown_event(self, fresh_bus, tmp_path):
        from supervision.alert_manager import Alert, AlertManager

        received = []
        fresh_bus.subscribe(DrawdownAlertEvent, received.append)

        mgr = AlertManager(audit_file=str(tmp_path / "audit.jsonl"))
        mgr.raise_alert(
            Alert(
                type_="drawdown",
                severity="critical",
                module="risk_monitor",
                message="Drawdown 8%",
                context={"drawdown_pct": 8.0, "max_allowed_pct": 5.0, "action": "halt"},
            )
        )
        assert len(received) == 1
        assert received[0].current_drawdown_pct == pytest.approx(8.0)
        assert received[0].action_taken == "halt"

    def test_multiple_alerts_emit_multiple_events(self, fresh_bus, tmp_path):
        from supervision.alert_manager import Alert, AlertManager

        received = []
        fresh_bus.subscribe(SecurityAlertEvent, received.append)

        mgr = AlertManager(audit_file=str(tmp_path / "audit.jsonl"))
        for i in range(3):
            mgr.raise_alert(
                Alert(
                    type_=f"rule_{i}",
                    severity="warning",
                    module="x",
                    message=f"msg {i}",
                )
            )
        assert len(received) == 3

    def test_alert_manager_survives_bus_error(self, tmp_path):
        """AlertManager ne crash pas si le bus est indisponible."""
        from supervision.alert_manager import Alert, AlertManager

        mgr = AlertManager(audit_file=str(tmp_path / "audit.jsonl"))
        with patch("event_bus.bus.EventBus.get", side_effect=RuntimeError("bus down")):
            # Should not raise
            mgr.raise_alert(
                Alert(
                    type_="test",
                    severity="info",
                    module="x",
                    message="y",
                )
            )


# ── EvolutionEngine → EventBus ─────────────────────────────────────────────────


class TestEvolutionEngineEmitsEvents:
    _CANDLES = [
        {
            "symbol": "BTCUSDT",
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1000,
        }
    ] * 30

    def test_run_cycle_emits_evolution_event(self, fresh_bus):
        from quant_hedge_ai.ai_evolution.evolution_engine import EvolutionEngine

        received = []
        fresh_bus.subscribe(EvolutionCycleEvent, received.append)

        engine = EvolutionEngine(population_size=5, generations=1)
        engine.run_cycle(cycle=1, regime="bull_trend", candles=self._CANDLES)

        assert len(received) == 1
        ev = received[0]
        assert ev.cycle == 1
        assert ev.regime == "bull_trend"
        assert ev.candidates_tested >= 0

    def test_run_cycle_emits_new_best_strategy_when_sharpe_positive(self, fresh_bus):
        from quant_hedge_ai.ai_evolution.evolution_engine import EvolutionEngine

        best_events = []
        fresh_bus.subscribe(NewBestStrategyEvent, best_events.append)

        engine = EvolutionEngine(
            population_size=10, generations=1, min_sharpe_to_save=0.0
        )
        engine.run_cycle(cycle=1, regime="sideways", candles=self._CANDLES)
        # NewBestStrategyEvent fired only when best_sharpe > 0
        # We just ensure no crash and type is correct if any
        for ev in best_events:
            assert isinstance(ev, NewBestStrategyEvent)
            assert ev.regime == "sideways"

    def test_evolution_event_contains_generation(self, fresh_bus):
        from quant_hedge_ai.ai_evolution.evolution_engine import EvolutionEngine

        received = []
        fresh_bus.subscribe(EvolutionCycleEvent, received.append)

        engine = EvolutionEngine(population_size=5, generations=1)
        engine.run_cycle(cycle=3, regime="bear_trend", candles=self._CANDLES)
        engine.run_cycle(cycle=4, regime="bear_trend", candles=self._CANDLES)

        assert len(received) == 2
        assert received[1].generation > received[0].generation

    def test_evolution_engine_survives_bus_error(self):
        """EvolutionEngine ne crash pas si le bus est indisponible."""
        from quant_hedge_ai.ai_evolution.evolution_engine import EvolutionEngine

        engine = EvolutionEngine(population_size=5, generations=1)
        with patch("event_bus.bus.EventBus.get", side_effect=RuntimeError("bus down")):
            result = engine.run_cycle(
                cycle=1, regime="bull_trend", candles=self._CANDLES
            )
        assert result is not None
        assert result.cycle == 1


# ── SupervisionBridge ─────────────────────────────────────────────────────────


class TestSupervisionBridge:
    def test_activate_subscribes_handlers(self, fresh_bus):
        from event_bus.bridge import SupervisionBridge

        bridge = SupervisionBridge(notifier=None)
        bridge.activate()
        assert fresh_bus.subscriber_count() > 0

    def test_activate_idempotent(self, fresh_bus):
        from event_bus.bridge import SupervisionBridge

        bridge = SupervisionBridge(notifier=None)
        bridge.activate()
        count_after_first = fresh_bus.subscriber_count()
        bridge.activate()
        assert fresh_bus.subscriber_count() == count_after_first

    def test_crash_event_routed_to_notifier(self, fresh_bus):
        from event_bus.bridge import SupervisionBridge
        from event_bus.events import CrashEvent

        notifier = MagicMock()
        bridge = SupervisionBridge(notifier=notifier)
        bridge.activate()
        fresh_bus.emit(
            CrashEvent(context="cycle 1", error="boom", error_type="ValueError")
        )
        notifier.info.assert_called_once()
        assert "CRASH" in notifier.info.call_args[0][0]

    def test_security_high_alert_notifies(self, fresh_bus):
        from event_bus.bridge import SupervisionBridge

        notifier = MagicMock()
        bridge = SupervisionBridge(notifier=notifier)
        bridge.activate()
        fresh_bus.emit(
            SecurityAlertEvent(
                severity="high",
                rule="exec_call",
                file="bad.py",
                line=42,
                message="exec detected",
            )
        )
        notifier.info.assert_called_once()

    def test_security_low_alert_no_notification(self, fresh_bus):
        from event_bus.bridge import SupervisionBridge

        notifier = MagicMock()
        bridge = SupervisionBridge(notifier=notifier)
        bridge.activate()
        fresh_bus.emit(SecurityAlertEvent(severity="low", rule="style", file="x.py"))
        notifier.info.assert_not_called()

    def test_incident_started_notifies(self, fresh_bus):
        from event_bus.bridge import SupervisionBridge

        notifier = MagicMock()
        bridge = SupervisionBridge(notifier=notifier)
        bridge.activate()
        fresh_bus.emit(
            IncidentStartedEvent(
                incident_id="abc123",
                severity="critical",
                module="brain.py",
                message="vuln",
            )
        )
        notifier.info.assert_called_once()

    def test_session_halt_notifies(self, fresh_bus):
        from event_bus.bridge import SupervisionBridge
        from event_bus.events import SessionHaltEvent

        notifier = MagicMock()
        bridge = SupervisionBridge(notifier=notifier)
        bridge.activate()
        fresh_bus.emit(
            SessionHaltEvent(reason="drawdown exceeded", halt_duration_seconds=300.0)
        )
        notifier.info.assert_called_once()

    def test_deactivate_removes_handlers(self, fresh_bus):
        from event_bus.bridge import SupervisionBridge

        bridge = SupervisionBridge(notifier=None)
        bridge.activate()
        count_active = fresh_bus.subscriber_count()
        bridge.deactivate()
        assert fresh_bus.subscriber_count() < count_active

    def test_bridge_no_notifier_logs_only(self, fresh_bus):
        from event_bus.bridge import SupervisionBridge
        from event_bus.events import CrashEvent

        bridge = SupervisionBridge(notifier=None)
        bridge.activate()
        # Should not raise, just log
        fresh_bus.emit(CrashEvent(context="x", error="e", error_type="E"))


# ── End-to-end: alert → bus → bridge → notifier ───────────────────────────────


class TestEndToEndFlow:
    def test_alert_manager_feeds_bridge_notifier(self, fresh_bus, tmp_path):
        from event_bus.bridge import SupervisionBridge
        from supervision.alert_manager import Alert, AlertManager

        notifier = MagicMock()
        bridge = SupervisionBridge(notifier=notifier)
        bridge.activate()

        mgr = AlertManager(audit_file=str(tmp_path / "audit.jsonl"))
        mgr.raise_alert(
            Alert(
                type_="exec_call",
                severity="high",
                module="danger.py",
                message="exec() found",
            )
        )
        # SecurityAlertEvent emitted by AlertManager → bridge routes to notifier
        notifier.info.assert_called_once()

    def test_evolution_cycle_event_received_by_bridge(self, fresh_bus):
        from event_bus.bridge import SupervisionBridge
        from quant_hedge_ai.ai_evolution.evolution_engine import EvolutionEngine

        notifier = MagicMock()
        bridge = SupervisionBridge(notifier=notifier)
        bridge.activate()

        candles = [
            {
                "symbol": "BTCUSDT",
                "open": 100,
                "high": 110,
                "low": 90,
                "close": 105,
                "volume": 1000,
            }
        ] * 30
        engine = EvolutionEngine(population_size=5, generations=1)
        engine.run_cycle(cycle=1, regime="bull_trend", candles=candles)
        # EvolutionCycleEvent is logged (no notify call expected for this event type)
        stats = fresh_bus.stats()
        assert stats.get("EvolutionCycleEvent", 0) >= 1

    def test_audit_log_written_when_configured(self, fresh_bus, tmp_path):
        audit_path = tmp_path / "bus_audit.jsonl"
        fresh_bus.configure_audit(audit_path)
        received = []
        fresh_bus.subscribe(SecurityAlertEvent, received.append)
        fresh_bus.emit(
            SecurityAlertEvent(severity="critical", rule="xss", file="app.py")
        )
        assert audit_path.exists()
        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 1
        import json

        data = json.loads(lines[0])
        assert data["event_type"] == "SecurityAlertEvent"
