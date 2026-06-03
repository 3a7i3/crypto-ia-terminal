"""Tests OrderSizer — dimensionnement Kelly + volatilité."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.decision_packet import (
    ConvictionLevel,
    DecisionPacket,
    DecisionSide,
    DecisionState,
    MarketRegime,
)
from quant_hedge_ai.agents.risk.order_sizer import OrderSizer, SizeResult

# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture
def sizer():
    return OrderSizer(
        kelly_fraction=0.25,
        min_size_usd=10.0,
        max_size_usd=5_000.0,
        vol_target=0.02,
    )


def _signal(score: int = 75):
    s = MagicMock()
    s.score = score
    return s


# ── Tests SizeResult ──────────────────────────────────────────────────────────


class TestSizeResult:
    def test_as_dict_keys(self, sizer):
        r = sizer.compute(
            capital=10_000.0, win_rate=0.6, avg_win_pct=3.0, avg_loss_pct=2.0
        )
        d = r.as_dict()
        for k in (
            "size_usd",
            "size_base",
            "kelly_fraction",
            "volatility_factor",
            "drawdown_factor",
            "final_fraction",
            "capped",
            "notes",
        ):
            assert k in d

    def test_notes_not_empty(self, sizer):
        r = sizer.compute(10_000.0, 0.6, 3.0, 2.0)
        assert len(r.notes) >= 3


# ── Tests calcul Kelly ────────────────────────────────────────────────────────


class TestKelly:
    def test_positive_kelly_when_win_rate_high(self, sizer):
        k = sizer._kelly(win_rate=0.6, avg_win_pct=3.0, avg_loss_pct=2.0)
        assert k > 0

    def test_zero_kelly_when_negative_expectancy(self, sizer):
        k = sizer._kelly(win_rate=0.3, avg_win_pct=1.0, avg_loss_pct=5.0)
        assert k == 0.0

    def test_kelly_clamped_below_zero(self, sizer):
        k = sizer._kelly(win_rate=0.1, avg_win_pct=1.0, avg_loss_pct=10.0)
        assert k >= 0.0

    def test_kelly_win_rate_one(self, sizer):
        k = sizer._kelly(win_rate=1.0, avg_win_pct=2.0, avg_loss_pct=1.0)
        assert k == pytest.approx(1.0)

    def test_kelly_symmetric_50pct(self, sizer):
        k = sizer._kelly(win_rate=0.5, avg_win_pct=2.0, avg_loss_pct=2.0)
        assert k == 0.0


# ── Tests facteur volatilité ──────────────────────────────────────────────────


class TestVolatilityFactor:
    def test_equal_vol_gives_one(self, sizer):
        assert sizer._volatility_factor(0.02) == pytest.approx(1.0)

    def test_low_vol_gives_one(self, sizer):
        assert sizer._volatility_factor(0.01) == pytest.approx(1.0)

    def test_high_vol_reduces_factor(self, sizer):
        assert sizer._volatility_factor(0.08) < 1.0

    def test_zero_vol_gives_one(self, sizer):
        assert sizer._volatility_factor(0.0) == pytest.approx(1.0)

    def test_factor_never_above_one(self, sizer):
        assert sizer._volatility_factor(0.001) <= 1.0


# ── Tests facteur drawdown ────────────────────────────────────────────────────


class TestDrawdownFactor:
    def test_zero_drawdown_gives_one(self, sizer):
        assert sizer._drawdown_factor(0.0) == pytest.approx(1.0)

    def test_negative_drawdown_gives_one(self, sizer):
        assert sizer._drawdown_factor(-0.05) == pytest.approx(1.0)

    def test_large_drawdown_reduces_factor(self, sizer):
        assert sizer._drawdown_factor(0.3) < 0.5

    def test_extreme_drawdown_gives_minimum(self, sizer):
        assert sizer._drawdown_factor(1.0) == pytest.approx(0.1)

    def test_drawdown_guard_integrated(self):
        from quant_hedge_ai.agents.risk.drawdown_guard import DrawdownGuard

        dg = DrawdownGuard()
        sizer = OrderSizer(drawdown_guard=dg)
        factor = sizer._drawdown_factor(0.2)
        assert 0.0 < factor <= 1.0


# ── Tests compute ─────────────────────────────────────────────────────────────


class TestCompute:
    def test_returns_size_result(self, sizer):
        r = sizer.compute(10_000.0, 0.6, 3.0, 2.0)
        assert isinstance(r, SizeResult)

    def test_size_usd_positive(self, sizer):
        r = sizer.compute(10_000.0, 0.6, 3.0, 2.0)
        assert r.size_usd > 0

    def test_size_respects_minimum(self, sizer):
        # Très petit capital → doit être >= min_size_usd
        r = sizer.compute(100.0, 0.51, 0.1, 0.09)
        assert r.size_usd >= 10.0 or r.size_usd == 0.0  # Kelly nul possible

    def test_size_respects_maximum(self, sizer):
        r = sizer.compute(1_000_000.0, 0.9, 10.0, 1.0)
        assert r.size_usd <= 5_000.0

    def test_capped_true_when_at_max(self, sizer):
        r = sizer.compute(1_000_000.0, 0.9, 10.0, 1.0)
        assert r.capped is True

    def test_capped_false_normal_size(self, sizer):
        r = sizer.compute(10_000.0, 0.55, 2.0, 1.5)
        # La taille normale ne devrait pas être cappée
        if r.size_usd < 5_000.0 and r.size_usd >= 10.0:
            assert r.capped is False

    def test_size_base_computed_from_price(self, sizer):
        r = sizer.compute(10_000.0, 0.6, 3.0, 2.0, price=50_000.0)
        assert r.size_base == pytest.approx(r.size_usd / 50_000.0, rel=0.01)

    def test_high_drawdown_reduces_size(self, sizer):
        r_low = sizer.compute(10_000.0, 0.6, 3.0, 2.0, current_drawdown=0.0)
        r_high = sizer.compute(10_000.0, 0.6, 3.0, 2.0, current_drawdown=0.3)
        assert r_high.size_usd <= r_low.size_usd

    def test_high_vol_reduces_size(self, sizer):
        r_low_vol = sizer.compute(10_000.0, 0.6, 3.0, 2.0, realized_volatility=0.02)
        r_high_vol = sizer.compute(10_000.0, 0.6, 3.0, 2.0, realized_volatility=0.10)
        assert r_high_vol.size_usd <= r_low_vol.size_usd

    def test_negative_kelly_gives_zero_or_min(self, sizer):
        r = sizer.compute(10_000.0, 0.2, 1.0, 5.0)
        assert r.size_usd == 0.0 or r.size_usd == sizer.min_size_usd

    def test_strong_signal_score_increases_size(self, sizer):
        r70 = sizer.compute(10_000.0, 0.6, 3.0, 2.0, signal_score=70)
        r90 = sizer.compute(10_000.0, 0.6, 3.0, 2.0, signal_score=90)
        assert r90.size_usd >= r70.size_usd

    def test_zero_price_gives_zero_base(self, sizer):
        r = sizer.compute(10_000.0, 0.6, 3.0, 2.0, price=0.0)
        assert r.size_base == 0.0


# ── Tests compute_from_signal ─────────────────────────────────────────────────


class TestComputeFromSignal:
    def test_returns_size_result(self, sizer):
        s = _signal(score=75)
        r = sizer.compute_from_signal(
            signal_result=s,
            capital=10_000.0,
            win_rate=0.6,
            avg_win_pct=3.0,
            avg_loss_pct=2.0,
        )
        assert isinstance(r, SizeResult)

    def test_features_volatility_used(self, sizer):
        s = _signal(score=75)
        features_low = {"realized_volatility": 0.01}
        features_high = {"realized_volatility": 0.10}
        r_low = sizer.compute_from_signal(
            s, 10_000.0, 0.6, 3.0, 2.0, features=features_low
        )
        r_high = sizer.compute_from_signal(
            s, 10_000.0, 0.6, 3.0, 2.0, features=features_high
        )
        assert r_high.size_usd <= r_low.size_usd

    def test_no_features_uses_default_vol(self, sizer):
        s = _signal(score=75)
        r = sizer.compute_from_signal(s, 10_000.0, 0.6, 3.0, 2.0)
        assert r.size_usd >= 0.0


# ── Tests paramètres de construction ─────────────────────────────────────────


class TestConstructor:
    def test_kelly_fraction_clamped_max(self):
        sizer = OrderSizer(kelly_fraction=5.0)
        assert sizer.kelly_fraction == 1.0

    def test_kelly_fraction_clamped_min(self):
        sizer = OrderSizer(kelly_fraction=-1.0)
        assert sizer.kelly_fraction == pytest.approx(0.01)

    def test_min_size_non_negative(self):
        sizer = OrderSizer(min_size_usd=-100.0)
        assert sizer.min_size_usd == 0.0

    def test_max_size_at_least_min(self):
        sizer = OrderSizer(min_size_usd=500.0, max_size_usd=100.0)
        assert sizer.max_size_usd >= sizer.min_size_usd


class TestDecisionPacketSizing:
    def test_size_packet_prefers_features_over_metadata(self, sizer):
        packet = DecisionPacket(
            symbol="BTC/USDT",
            side=DecisionSide.LONG,
            confidence=60.0,
            adjusted_confidence=90.0,
            regime=MarketRegime.TREND_BULL,
            conviction=ConvictionLevel.HIGH,
            lifecycle_state=DecisionState.APPROVED,
            features={
                "realized_volatility": 0.02,
                "conviction_size_factor": 0.5,
                "pb_size_factor": 0.5,
            },
            metadata={
                "conviction_size_factor": 0.1,
                "pb_size_factor": 0.1,
            },
        )

        sizer.size_packet(packet, capital=10_000.0, price=50_000.0)

        size_usd = float(packet.features["os_size_usd"])
        assert size_usd >= sizer.min_size_usd
        assert packet.lifecycle_state == DecisionState.EXECUTION_PENDING
