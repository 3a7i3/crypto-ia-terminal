"""Tests for DrawdownGuard — position sizing under drawdown."""

from __future__ import annotations

import pytest

from quant_hedge_ai.agents.risk.drawdown_guard import DrawdownGuard


@pytest.fixture
def guard():
    return DrawdownGuard()


class TestNoDrawdown:
    def test_zero_drawdown_returns_base_size(self, guard):
        assert guard.adjust_position_size(0.0, 1.0) == 1.0

    def test_negative_drawdown_returns_base_size(self, guard):
        assert guard.adjust_position_size(-0.05, 1.0) == 1.0

    def test_negative_drawdown_custom_base(self, guard):
        assert guard.adjust_position_size(-0.10, 0.5) == 0.5


class TestReduction:
    def test_small_drawdown_reduces_size(self, guard):
        result = guard.adjust_position_size(0.10, 1.0)
        # factor = max(0.1, 1 - 0.10*2.5) = max(0.1, 0.75) = 0.75
        assert result == pytest.approx(0.75, abs=1e-4)

    def test_medium_drawdown(self, guard):
        result = guard.adjust_position_size(0.20, 1.0)
        # factor = max(0.1, 1 - 0.20*2.5) = max(0.1, 0.5) = 0.5
        assert result == pytest.approx(0.5, abs=1e-4)

    def test_large_drawdown_floors_at_min(self, guard):
        result = guard.adjust_position_size(0.50, 1.0)
        # factor = max(0.1, 1 - 0.50*2.5) = max(0.1, -0.25) = 0.1
        assert result == pytest.approx(0.1, abs=1e-4)

    def test_extreme_drawdown_still_floors(self, guard):
        result = guard.adjust_position_size(1.0, 1.0)
        assert result == pytest.approx(0.1, abs=1e-4)

    def test_drawdown_scales_with_base_size(self, guard):
        result = guard.adjust_position_size(0.10, 2.0)
        # factor = 0.75, base = 2.0 → 1.5
        assert result == pytest.approx(1.5, abs=1e-4)

    def test_result_is_rounded_to_4_decimals(self, guard):
        result = guard.adjust_position_size(0.13, 1.0)
        assert result == round(result, 4)

    def test_threshold_where_floor_kicks_in(self, guard):
        # factor = 1 - dd*2.5 = 0.1 → dd = 0.36
        result_just_before = guard.adjust_position_size(0.35, 1.0)
        result_at_floor = guard.adjust_position_size(0.40, 1.0)
        assert result_just_before > 0.1
        assert result_at_floor == pytest.approx(0.1, abs=1e-4)


class TestReturnType:
    def test_returns_float(self, guard):
        assert isinstance(guard.adjust_position_size(0.1, 1.0), float)

    def test_result_always_positive(self, guard):
        for dd in [0.0, 0.1, 0.3, 0.5, 0.9, 1.5]:
            assert guard.adjust_position_size(dd, 1.0) > 0
