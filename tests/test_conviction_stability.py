"""
Tests de l'intégration stabilité OHLCV dans le ConvictionEngine.

Vérifie que :
  - noisy/flat → pénalité significative (pousse vers MINIMAL)
  - trending + momentum personality → bonus fort
  - ranging + mean_reversion personality → bonus
  - ranging + momentum personality → pénalité
  - directional + BUY/SELL → léger bonus
  - unknown → neutre
  - evaluate() inclut 'stability' dans dims quand non-neutre
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from quant_hedge_ai.agents.intelligence.conviction_engine import (
    ConvictionEngine,
    ConvictionLevel,
    ConvictionResult,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _fake_signal(
    score: float = 70.0, action: str = "BUY", strength: float = 0.6
) -> object:
    return SimpleNamespace(
        score=score,
        signal=action,
        strength=strength,
        components={"mtf": 20.0},
        confirmed=False,
    )


def _base_features(
    stability_regime: str = "unknown", stability_score: float = 55.0
) -> dict:
    return {
        "momentum": 0.5,
        "realized_volatility": 0.02,
        "trend_strength": 0.6,
        "atr": 0.015,
        "stability_regime": stability_regime,
        "stability_score": stability_score,
    }


def _fake_candles(n: int = 100) -> list:
    return [{"open": 100, "close": 101, "high": 102, "low": 99, "volume": 50_000}] * n


def _evaluate(
    stability_regime: str,
    stability_score: float = 60.0,
    action: str = "BUY",
    personality: str = "unknown",
    signal_score: float = 70.0,
) -> ConvictionResult:
    engine = ConvictionEngine()
    return engine.evaluate(
        _fake_signal(score=signal_score, action=action),
        _base_features(stability_regime, stability_score),
        _fake_candles(),
        regime="bull_trend",
        personality_name=personality,
    )


# ── Tests _stability_adjustment ───────────────────────────────────────────────


class TestStabilityAdjustment:

    def test_noisy_returns_minus_20(self):
        adj = ConvictionEngine._stability_adjustment("noisy", 30.0, "BUY")
        assert adj == -20.0

    def test_flat_returns_minus_15(self):
        adj = ConvictionEngine._stability_adjustment("flat", 20.0, "SELL")
        assert adj == -15.0

    def test_trending_momentum_personality_returns_plus_8(self):
        adj = ConvictionEngine._stability_adjustment(
            "trending", 80.0, "BUY", "momentum"
        )
        assert adj == 8.0

    def test_trending_breakout_personality_returns_plus_8(self):
        adj = ConvictionEngine._stability_adjustment(
            "trending", 80.0, "BUY", "breakout"
        )
        assert adj == 8.0

    def test_trending_unknown_personality_returns_plus_3(self):
        adj = ConvictionEngine._stability_adjustment("trending", 70.0, "BUY", "unknown")
        assert adj == 3.0

    def test_ranging_mean_reversion_personality_returns_plus_5(self):
        adj = ConvictionEngine._stability_adjustment(
            "ranging", 55.0, "BUY", "mean_reversion"
        )
        assert adj == 5.0

    def test_ranging_scalp_personality_returns_plus_5(self):
        adj = ConvictionEngine._stability_adjustment("ranging", 55.0, "SELL", "scalp")
        assert adj == 5.0

    def test_ranging_momentum_personality_returns_minus_8(self):
        adj = ConvictionEngine._stability_adjustment("ranging", 55.0, "BUY", "momentum")
        assert adj == -8.0

    def test_directional_buy_returns_plus_3(self):
        adj = ConvictionEngine._stability_adjustment("directional", 65.0, "BUY")
        assert adj == 3.0

    def test_directional_hold_returns_0(self):
        adj = ConvictionEngine._stability_adjustment("directional", 65.0, "HOLD")
        assert adj == 0.0

    def test_unknown_returns_0(self):
        adj = ConvictionEngine._stability_adjustment("unknown", 50.0, "BUY")
        assert adj == 0.0


# ── Tests evaluate() avec stabilité ──────────────────────────────────────────


class TestEvaluateWithStability:

    def test_noisy_pushes_score_down(self):
        noisy = _evaluate("noisy", signal_score=75.0)
        clean = _evaluate("unknown", signal_score=75.0)
        assert noisy.score < clean.score
        assert noisy.score == pytest.approx(clean.score - 20.0, abs=0.5)

    def test_noisy_can_push_to_minimal(self):
        # Signal faible (30/100) + pénalité noisy (-20) → composite ~36 → MINIMAL
        noisy = _evaluate("noisy", signal_score=30.0)
        assert noisy.level == ConvictionLevel.MINIMAL
        assert noisy.size_factor == 0.0

    def test_trending_momentum_boosts_score(self):
        trending = _evaluate("trending", personality="momentum", signal_score=70.0)
        unknown = _evaluate("unknown", personality="momentum", signal_score=70.0)
        assert trending.score > unknown.score

    def test_ranging_mean_reversion_gives_bonus(self):
        ranging_rev = _evaluate(
            "ranging", personality="mean_reversion", signal_score=68.0
        )
        ranging_mom = _evaluate("ranging", personality="momentum", signal_score=68.0)
        assert ranging_rev.score > ranging_mom.score

    def test_ranging_momentum_penalizes_score(self):
        ranging = _evaluate("ranging", personality="momentum", signal_score=70.0)
        clean = _evaluate("unknown", personality="momentum", signal_score=70.0)
        assert ranging.score < clean.score

    def test_stability_dim_present_in_dims_when_nonzero(self):
        result = _evaluate("noisy")
        assert "stability" in result.dimensions

    def test_stability_dim_absent_when_unknown(self):
        result = _evaluate("unknown")
        assert "stability" not in result.dimensions

    def test_stability_note_added_for_noisy(self):
        result = _evaluate("noisy")
        assert any("noisy" in n for n in result.notes)

    def test_stability_note_added_for_trending(self):
        result = _evaluate("trending", personality="momentum")
        assert any("trending" in n for n in result.notes)

    def test_score_never_exceeds_100(self):
        # Toutes les conditions favorables ne doivent pas dépasser 100
        result = _evaluate("trending", personality="momentum", signal_score=100.0)
        assert result.score <= 100.0

    def test_score_never_below_0(self):
        # Toutes les pénalités empilées ne doivent pas descendre sous 0
        result = _evaluate("noisy", signal_score=0.0)
        assert result.score >= 0.0

    def test_flat_blocks_high_confidence_trade(self):
        # Signal fort (95) sur marché flat → conviction réduite
        result = _evaluate("flat", signal_score=95.0, personality="momentum")
        # Avec -15 pts de pénalité, un score de ~55 doit rester tradable mais réduit
        unknown = _evaluate("unknown", signal_score=95.0, personality="momentum")
        assert result.score < unknown.score
