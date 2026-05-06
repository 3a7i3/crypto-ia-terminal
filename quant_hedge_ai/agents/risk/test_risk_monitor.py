"""Tests RiskMonitor — filtre de résultats par drawdown max."""

from __future__ import annotations
import pytest
from quant_hedge_ai.agents.risk.risk_monitor import RiskMonitor


@pytest.fixture
def rm():
    return RiskMonitor(max_drawdown=0.2)


class TestCheck:
    def test_low_drawdown_passes(self, rm):
        assert rm.check({"drawdown": 0.10}) is True

    def test_exactly_at_limit_passes(self, rm):
        assert rm.check({"drawdown": 0.20}) is True

    def test_above_limit_rejected(self, rm):
        assert rm.check({"drawdown": 0.21}) is False

    def test_zero_drawdown_passes(self, rm):
        assert rm.check({"drawdown": 0.0}) is True

    def test_missing_drawdown_key_defaults_to_1(self, rm):
        # default drawdown=1.0 > 0.2 → False
        assert rm.check({}) is False

    def test_string_drawdown_coerced(self, rm):
        assert rm.check({"drawdown": "0.05"}) is True

    def test_custom_max_drawdown(self):
        rm = RiskMonitor(max_drawdown=0.5)
        assert rm.check({"drawdown": 0.49}) is True
        assert rm.check({"drawdown": 0.51}) is False
