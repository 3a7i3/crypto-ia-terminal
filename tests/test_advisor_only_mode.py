"""Tests AdvisorOnlyMode — mode V9_ADVISOR_ONLY=true."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from quant_hedge_ai.advisor_only_mode import AdvisorOnlyMode, AdvisorResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _signal(score: int = 80, signal: str = "BUY", regime: str = "bull_trend",
            actionable: bool = True):
    s = MagicMock()
    s.score = score
    s.signal = signal
    s.regime = regime
    s.actionable = actionable
    s.components = {"mtf": 30.0, "regime": 20.0}
    return s


def _advisor(text: str = "Conseil de test.", risk: str = "medium", conf: str = "moderate"):
    a = MagicMock()
    a.explain = MagicMock(return_value=MagicMock(
        text=text, risk_level=risk, confidence=conf
    ))
    return a


@pytest.fixture
def mode_active():
    return AdvisorOnlyMode(active=True, advisor=_advisor(), alerts=None)


@pytest.fixture
def mode_inactive():
    return AdvisorOnlyMode(active=False, advisor=_advisor(), alerts=None)


# ── Tests AdvisorResult ───────────────────────────────────────────────────────

class TestAdvisorResult:
    def test_would_trade_true_when_actionable(self, mode_active):
        r = mode_active.process_signal(_signal(score=80, signal="BUY", actionable=True))
        assert r.would_trade is True

    def test_would_trade_false_hold(self, mode_active):
        r = mode_active.process_signal(_signal(score=80, signal="HOLD", actionable=False))
        assert r.would_trade is False

    def test_would_trade_false_low_score(self, mode_active):
        r = mode_active.process_signal(_signal(score=50, signal="BUY", actionable=False))
        assert r.would_trade is False

    def test_as_dict_keys(self, mode_active):
        r = mode_active.process_signal(_signal())
        d = r.as_dict()
        for k in ("signal", "score", "regime", "advice_text", "risk_level",
                  "confidence", "alerted", "blocked_reason", "would_trade"):
            assert k in d


# ── Tests from_env ────────────────────────────────────────────────────────────

class TestFromEnv:
    def test_env_true_activates_mode(self, monkeypatch):
        monkeypatch.setenv("V9_ADVISOR_ONLY", "true")
        m = AdvisorOnlyMode.from_env()
        assert m.active is True

    def test_env_false_deactivates_mode(self, monkeypatch):
        monkeypatch.setenv("V9_ADVISOR_ONLY", "false")
        m = AdvisorOnlyMode.from_env()
        assert m.active is False

    def test_env_1_activates(self, monkeypatch):
        monkeypatch.setenv("V9_ADVISOR_ONLY", "1")
        m = AdvisorOnlyMode.from_env()
        assert m.active is True

    def test_env_yes_activates(self, monkeypatch):
        monkeypatch.setenv("V9_ADVISOR_ONLY", "yes")
        m = AdvisorOnlyMode.from_env()
        assert m.active is True

    def test_env_missing_defaults_false(self, monkeypatch):
        monkeypatch.delenv("V9_ADVISOR_ONLY", raising=False)
        m = AdvisorOnlyMode.from_env()
        assert m.active is False


# ── Tests process_signal — mode actif ────────────────────────────────────────

class TestProcessSignalActive:
    def test_returns_advisor_result(self, mode_active):
        r = mode_active.process_signal(_signal())
        assert isinstance(r, AdvisorResult)

    def test_blocked_reason_set(self, mode_active):
        r = mode_active.process_signal(_signal())
        assert r.blocked_reason == "advisor_only"

    def test_signal_field_preserved(self, mode_active):
        r = mode_active.process_signal(_signal(signal="SELL"))
        assert r.signal == "SELL"

    def test_score_field_preserved(self, mode_active):
        r = mode_active.process_signal(_signal(score=85))
        assert r.score == 85

    def test_regime_field_preserved(self, mode_active):
        r = mode_active.process_signal(_signal(regime="bear_trend"))
        assert r.regime == "bear_trend"

    def test_advice_text_filled(self, mode_active):
        r = mode_active.process_signal(_signal())
        assert len(r.advice_text) > 0

    def test_no_advisor_no_crash(self):
        mode = AdvisorOnlyMode(active=True, advisor=None)
        r = mode.process_signal(_signal())
        assert isinstance(r, AdvisorResult)
        assert r.advice_text == ""

    def test_advisor_exception_no_crash(self):
        bad_advisor = MagicMock()
        bad_advisor.explain.side_effect = RuntimeError("LLM error")
        mode = AdvisorOnlyMode(active=True, advisor=bad_advisor)
        r = mode.process_signal(_signal())
        assert isinstance(r, AdvisorResult)


# ── Tests process_signal — mode inactif ──────────────────────────────────────

class TestProcessSignalInactive:
    def test_blocked_reason_empty_when_inactive(self, mode_inactive):
        r = mode_inactive.process_signal(_signal())
        assert r.blocked_reason == ""

    def test_returns_result_even_inactive(self, mode_inactive):
        r = mode_inactive.process_signal(_signal())
        assert isinstance(r, AdvisorResult)


# ── Tests alertes intégrées ───────────────────────────────────────────────────

class TestAlerts:
    def test_alert_sent_when_actionable(self):
        mock_alerts = MagicMock()
        mock_alerts.on_signal_opportunity = MagicMock(return_value=True)
        mode = AdvisorOnlyMode(active=True, alerts=mock_alerts)
        mode.process_signal(_signal(actionable=True))
        mock_alerts.on_signal_opportunity.assert_called_once()

    def test_alert_not_sent_when_not_actionable(self):
        mock_alerts = MagicMock()
        mode = AdvisorOnlyMode(active=True, alerts=mock_alerts)
        mode.process_signal(_signal(actionable=False))
        mock_alerts.on_signal_opportunity.assert_not_called()

    def test_alerted_true_when_alert_sent(self):
        mock_alerts = MagicMock()
        mock_alerts.on_signal_opportunity = MagicMock(return_value=True)
        mode = AdvisorOnlyMode(active=True, alerts=mock_alerts)
        r = mode.process_signal(_signal(actionable=True))
        assert r.alerted is True

    def test_alerted_false_when_no_alerts(self, mode_active):
        r = mode_active.process_signal(_signal(actionable=True))
        assert r.alerted is False   # alerts=None dans la fixture


# ── Tests compteurs ───────────────────────────────────────────────────────────

class TestCounters:
    def test_cycle_count_increments(self, mode_active):
        mode_active.process_signal(_signal())
        mode_active.process_signal(_signal())
        assert mode_active._cycle_count == 2

    def test_would_trade_count_increments(self, mode_active):
        mode_active.process_signal(_signal(score=80, signal="BUY", actionable=True))
        assert mode_active._would_trade_count == 1

    def test_hold_signal_not_counted(self, mode_active):
        mode_active.process_signal(_signal(score=80, signal="HOLD", actionable=False))
        assert mode_active._would_trade_count == 0

    def test_summary_zero_initially(self):
        mode = AdvisorOnlyMode(active=True)
        s = mode.summary()
        assert s["cycles_processed"] == 0
        assert s["would_trade_rate"] == 0.0

    def test_summary_rate_computed(self, mode_active):
        mode_active.process_signal(_signal(score=80, signal="BUY", actionable=True))
        mode_active.process_signal(_signal(score=80, signal="HOLD", actionable=False))
        s = mode_active.summary()
        assert s["would_trade_rate"] == pytest.approx(0.5)

    def test_summary_active_field(self, mode_active):
        s = mode_active.summary()
        assert s["active"] is True

    def test_summary_inactive_field(self, mode_inactive):
        s = mode_inactive.summary()
        assert s["active"] is False
