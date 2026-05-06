"""Tests ProactiveAlerts — 3 types d'alertes Telegram proactives."""

from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock, patch

from quant_hedge_ai.agents.intelligence.proactive_alerts import (
    ProactiveAlerts,
    AlertRecord,
    _COOLDOWN_SIGNAL,
    _COOLDOWN_REGIME,
    _COOLDOWN_RISK,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _signal(actionable: bool = True, score: int = 80, signal: str = "BUY",
            regime: str = "bull_trend", symbol: str = "BTCUSDT", strength: float = 0.75):
    s = MagicMock()
    s.actionable = actionable
    s.score = score
    s.signal = signal
    s.regime = regime
    s.symbol = symbol
    s.strength = strength
    return s


def _gate_result(allowed: bool = False, failed: list | None = None, warnings: list | None = None):
    g = MagicMock()
    g.allowed = allowed
    g.failed = failed or ["signal_score (60<70)"]
    g.warnings = warnings or []
    return g


def _advice(text: str = "Conseil de test."):
    a = MagicMock()
    a.text = text
    return a


@pytest.fixture
def alerts():
    """Alertes sans Telegram (notifier=None) — log uniquement."""
    return ProactiveAlerts(notifier=None)


@pytest.fixture
def alerts_with_notifier():
    """Alertes avec un notifier mocké."""
    notifier = MagicMock()
    notifier.enabled = True
    notifier.info = MagicMock(return_value=True)
    return ProactiveAlerts(notifier=notifier)


# ── Tests constructeur / from_env ─────────────────────────────────────────────

class TestInit:
    def test_no_notifier_not_enabled(self, alerts):
        assert alerts.enabled is False

    def test_with_notifier_enabled(self, alerts_with_notifier):
        assert alerts_with_notifier.enabled is True

    def test_from_env_no_telegram_not_enabled(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        a = ProactiveAlerts.from_env()
        assert a.enabled is False

    def test_history_empty_initially(self, alerts):
        assert alerts.history() == []

    def test_stats_initial(self, alerts):
        s = alerts.stats()
        assert s["total_sent"] == 0
        assert s["enabled"] is False


# ── Tests alerte 1 : signal_opportunity ──────────────────────────────────────

class TestSignalOpportunity:
    def test_actionable_signal_sends(self, alerts):
        result = alerts.on_signal_opportunity(_signal(actionable=True))
        assert result is True

    def test_non_actionable_signal_skipped(self, alerts):
        result = alerts.on_signal_opportunity(_signal(actionable=False))
        assert result is False

    def test_advice_text_included_when_provided(self, alerts_with_notifier):
        alerts_with_notifier.on_signal_opportunity(_signal(), _advice("Super conseil."))
        call_args = alerts_with_notifier._notifier.info.call_args[0][0]
        assert "Super conseil." in call_args

    def test_rate_limit_prevents_second_send(self, alerts):
        alerts.on_signal_opportunity(_signal(symbol="BTC", signal="BUY"))
        result = alerts.on_signal_opportunity(_signal(symbol="BTC", signal="BUY"))
        assert result is False

    def test_different_symbol_not_rate_limited(self, alerts):
        alerts.on_signal_opportunity(_signal(symbol="BTC"))
        result = alerts.on_signal_opportunity(_signal(symbol="ETH"))
        assert result is True

    def test_different_side_not_rate_limited(self, alerts):
        alerts.on_signal_opportunity(_signal(symbol="BTC", signal="BUY"))
        result = alerts.on_signal_opportunity(_signal(symbol="BTC", signal="SELL"))
        assert result is True

    def test_history_recorded_after_send(self, alerts):
        alerts.on_signal_opportunity(_signal())
        assert len(alerts.history()) == 1
        assert alerts.history()[0].alert_type == "opportunity"

    def test_notifier_info_called(self, alerts_with_notifier):
        alerts_with_notifier.on_signal_opportunity(_signal())
        alerts_with_notifier._notifier.info.assert_called_once()

    def test_message_contains_symbol(self, alerts_with_notifier):
        alerts_with_notifier.on_signal_opportunity(_signal(symbol="SOLUSDT"))
        msg = alerts_with_notifier._notifier.info.call_args[0][0]
        assert "SOLUSDT" in msg

    def test_message_contains_score(self, alerts_with_notifier):
        alerts_with_notifier.on_signal_opportunity(_signal(score=85))
        msg = alerts_with_notifier._notifier.info.call_args[0][0]
        assert "85" in msg

    def test_notifier_exception_does_not_crash(self):
        notifier = MagicMock()
        notifier.enabled = True
        notifier.info.side_effect = RuntimeError("Telegram down")
        alerts = ProactiveAlerts(notifier=notifier)
        result = alerts.on_signal_opportunity(_signal())
        assert isinstance(result, bool)


# ── Tests alerte 2 : regime_change ───────────────────────────────────────────

class TestRegimeChange:
    def test_regime_change_sends(self, alerts):
        result = alerts.on_regime_change("BTCUSDT", "sideways", "bull_trend")
        assert result is True

    def test_same_regime_skipped(self, alerts):
        result = alerts.on_regime_change("BTCUSDT", "bull_trend", "bull_trend")
        assert result is False

    def test_risky_regime_has_warning_in_message(self, alerts_with_notifier):
        alerts_with_notifier.on_regime_change("BTC", "sideways", "flash_crash")
        msg = alerts_with_notifier._notifier.info.call_args[0][0]
        assert "RISQUE" in msg or "flash_crash" in msg

    def test_rate_limit_same_regime(self, alerts):
        alerts.on_regime_change("BTC", "sideways", "bull_trend")
        result = alerts.on_regime_change("BTC", "sideways", "bull_trend")
        assert result is False

    def test_different_new_regime_not_limited(self, alerts):
        alerts.on_regime_change("BTC", "sideways", "bull_trend")
        result = alerts.on_regime_change("BTC", "bull_trend", "bear_trend")
        assert result is True

    def test_message_contains_old_regime(self, alerts_with_notifier):
        alerts_with_notifier.on_regime_change("ETH", "sideways", "bull_trend")
        msg = alerts_with_notifier._notifier.info.call_args[0][0]
        assert "sideways" in msg

    def test_history_type_regime(self, alerts):
        alerts.on_regime_change("BTC", "sideways", "bull_trend")
        assert alerts.history()[-1].alert_type == "regime"


# ── Tests alerte 3 : risk_gate_blocked ───────────────────────────────────────

class TestRiskGateBlocked:
    def test_blocked_gate_sends(self, alerts):
        result = alerts.on_risk_gate_blocked(_gate_result(allowed=False))
        assert result is True

    def test_allowed_gate_skipped(self, alerts):
        result = alerts.on_risk_gate_blocked(_gate_result(allowed=True))
        assert result is False

    def test_message_contains_failed_conditions(self, alerts_with_notifier):
        gate = _gate_result(allowed=False, failed=["signal_score", "drawdown_ok"])
        alerts_with_notifier.on_risk_gate_blocked(gate, _signal())
        msg = alerts_with_notifier._notifier.info.call_args[0][0]
        assert "signal_score" in msg

    def test_message_contains_warnings(self, alerts_with_notifier):
        gate = _gate_result(allowed=False, warnings=["Drawdown proche du seuil"])
        alerts_with_notifier.on_risk_gate_blocked(gate)
        msg = alerts_with_notifier._notifier.info.call_args[0][0]
        assert "Drawdown proche du seuil" in msg

    def test_signal_symbol_in_message(self, alerts_with_notifier):
        gate = _gate_result(allowed=False)
        alerts_with_notifier.on_risk_gate_blocked(gate, _signal(symbol="XRPUSDT"))
        msg = alerts_with_notifier._notifier.info.call_args[0][0]
        assert "XRPUSDT" in msg

    def test_rate_limit_risk_block(self, alerts):
        gate = _gate_result(allowed=False)
        alerts.on_risk_gate_blocked(gate, _signal(symbol="BTC"))
        result = alerts.on_risk_gate_blocked(gate, _signal(symbol="BTC"))
        assert result is False

    def test_history_type_risk_block(self, alerts):
        alerts.on_risk_gate_blocked(_gate_result(allowed=False))
        assert alerts.history()[-1].alert_type == "risk_block"


# ── Tests rapport hebdomadaire ────────────────────────────────────────────────

class TestWeeklyReport:
    def test_weekly_report_sends(self, alerts):
        report = MagicMock()
        report.text_summary = "RAPPORT\n---\nGood week."
        result = alerts.on_weekly_report(report)
        assert result is True

    def test_weekly_cooldown_24h(self, alerts):
        report = MagicMock()
        report.text_summary = "Rapport."
        alerts.on_weekly_report(report)
        result = alerts.on_weekly_report(report)
        assert result is False

    def test_long_report_truncated(self, alerts_with_notifier):
        report = MagicMock()
        report.text_summary = "A" * 5000
        alerts_with_notifier.on_weekly_report(report)
        msg = alerts_with_notifier._notifier.info.call_args[0][0]
        assert len(msg) <= 4100   # troncature à 4000 + "[...]"


# ── Tests stats et utilitaires ────────────────────────────────────────────────

class TestStatsAndUtils:
    def test_stats_by_type(self, alerts):
        alerts.on_signal_opportunity(_signal(symbol="A"))
        alerts.on_signal_opportunity(_signal(symbol="B"))
        alerts.on_regime_change("C", "x", "y")
        s = alerts.stats()
        assert s["total_sent"] == 3
        assert s["by_type"]["opportunity"] == 2
        assert s["by_type"]["regime"] == 1

    def test_history_limit(self, alerts):
        for i in range(5):
            alerts.on_regime_change(f"S{i}", "x", "y")
        assert len(alerts.history(limit=3)) == 3

    def test_reset_cooldowns(self, alerts):
        alerts.on_signal_opportunity(_signal(symbol="BTC", signal="BUY"))
        alerts.reset_cooldowns()
        result = alerts.on_signal_opportunity(_signal(symbol="BTC", signal="BUY"))
        assert result is True


# ── Tests EventBus ────────────────────────────────────────────────────────────

class TestEventBus:
    def test_risk_block_emits_security_event(self, alerts):
        with patch("event_bus.bus.EventBus.get") as mock_bus:
            mock_inst = MagicMock()
            mock_bus.return_value = mock_inst
            alerts.on_risk_gate_blocked(_gate_result(allowed=False))
            assert mock_inst.emit.called

    def test_eventbus_exception_does_not_crash(self, alerts):
        with patch("event_bus.bus.EventBus.get", side_effect=RuntimeError("bus error")):
            result = alerts.on_risk_gate_blocked(_gate_result(allowed=False))
            assert isinstance(result, bool)
