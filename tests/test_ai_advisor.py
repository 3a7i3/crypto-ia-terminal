"""Tests AIAdvisor — conseil IA par signal de trading."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from quant_hedge_ai.agents.execution.live_signal_engine import SignalResult
from quant_hedge_ai.agents.intelligence.ai_advisor import (
    AIAdvisor,
    Advice,
    _LM_STUDIO_MAX_TOKENS,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _result(
    symbol: str = "BTCUSDT",
    score: int = 78,
    signal: str = "BUY",
    regime: str = "bull_trend",
    confirmed: bool = True,
    strength: float = 0.75,
    components: dict | None = None,
) -> SignalResult:
    return SignalResult(
        symbol=symbol,
        score=score,
        signal=signal,
        regime=regime,
        confirmed=confirmed,
        strength=strength,
        components=components or {
            "mtf": 30.0, "regime": 25.0, "data_quality": 14.0, "memory": 18.0
        },
    )


@pytest.fixture
def advisor():
    return AIAdvisor(use_lm_studio=False)  # mode déterministe pour les tests


# ── Tests Advice ──────────────────────────────────────────────────────────────

class TestAdvice:
    def test_as_dict_keys(self, advisor):
        r = _result()
        a = advisor.explain(r)
        d = a.as_dict()
        for k in ("symbol", "signal", "score", "regime", "text", "risk_level",
                  "confidence", "source"):
            assert k in d

    def test_short_contains_symbol(self, advisor):
        r = _result(symbol="ETHUSDT")
        a = advisor.explain(r)
        assert "ETHUSDT" in a.short()

    def test_short_contains_signal(self, advisor):
        r = _result(signal="SELL")
        a = advisor.explain(r)
        assert "SELL" in a.short()

    def test_source_deterministic_when_lm_studio_off(self, advisor):
        r = _result()
        a = advisor.explain(r)
        assert a.source == "deterministic"


# ── Tests explain — mode déterministe ────────────────────────────────────────

class TestExplainDeterministic:
    def test_returns_advice_object(self, advisor):
        assert isinstance(advisor.explain(_result()), Advice)

    def test_text_not_empty(self, advisor):
        a = advisor.explain(_result())
        assert len(a.text) > 20

    def test_symbol_in_text(self, advisor):
        a = advisor.explain(_result(symbol="SOLUSDT"))
        assert "SOLUSDT" in a.text

    def test_signal_word_in_text_buy(self, advisor):
        a = advisor.explain(_result(signal="BUY"))
        assert "achat" in a.text.lower()

    def test_signal_word_in_text_sell(self, advisor):
        a = advisor.explain(_result(signal="SELL"))
        assert "vente" in a.text.lower()

    def test_signal_word_in_text_hold(self, advisor):
        a = advisor.explain(_result(signal="HOLD", score=50, confirmed=False))
        assert "neutre" in a.text.lower()

    def test_regime_desc_in_text(self, advisor):
        a = advisor.explain(_result(regime="bear_trend"))
        assert "baissière" in a.text

    def test_regime_unknown_fallback(self, advisor):
        a = advisor.explain(_result(regime="unknown"))
        assert a.regime == "unknown"

    def test_confirmed_mention_in_text(self, advisor):
        a = advisor.explain(_result(confirmed=True, strength=0.8))
        assert "confirmé" in a.text

    def test_unconfirmed_mention_in_text(self, advisor):
        a = advisor.explain(_result(confirmed=False, strength=0.4))
        assert "non confirmé" in a.text

    def test_strengths_appear_on_high_score(self, advisor):
        comps = {"mtf": 38.0, "regime": 24.0, "data_quality": 14.0, "memory": 18.0}
        a = advisor.explain(_result(score=90, confirmed=True, components=comps))
        assert "Points forts" in a.text

    def test_risk_mention_on_volatile_regime(self, advisor):
        a = advisor.explain(_result(regime="flash_crash", score=30, confirmed=False))
        assert "krach" in a.text or "risque" in a.text.lower()


# ── Tests évaluation du risque ────────────────────────────────────────────────

class TestRiskAssessment:
    def test_flash_crash_extreme_risk(self, advisor):
        a = advisor.explain(_result(regime="flash_crash"))
        assert a.risk_level == "extreme"

    def test_high_vol_high_risk(self, advisor):
        a = advisor.explain(_result(regime="high_volatility_regime"))
        assert a.risk_level == "high"

    def test_unconfirmed_signal_high_risk(self, advisor):
        a = advisor.explain(_result(confirmed=False, score=40))
        assert a.risk_level == "high"

    def test_high_score_confirmed_low_risk(self, advisor):
        a = advisor.explain(_result(score=90, confirmed=True, strength=0.85))
        assert a.risk_level == "low"

    def test_moderate_score_medium_risk(self, advisor):
        a = advisor.explain(_result(score=72, confirmed=True))
        assert a.risk_level == "medium"

    def test_low_score_high_risk(self, advisor):
        a = advisor.explain(_result(score=45, confirmed=False))
        assert a.risk_level == "high"


# ── Tests évaluation de la confiance ─────────────────────────────────────────

class TestConfidenceAssessment:
    def test_high_confidence_on_strong_signal(self, advisor):
        a = advisor.explain(_result(score=88, confirmed=True, strength=0.8))
        assert a.confidence == "high"

    def test_moderate_confidence_on_good_signal(self, advisor):
        a = advisor.explain(_result(score=73, confirmed=True, strength=0.6))
        assert a.confidence == "moderate"

    def test_low_confidence_on_weak_signal(self, advisor):
        a = advisor.explain(_result(score=50, confirmed=False, strength=0.3))
        assert a.confidence == "low"


# ── Tests explain_batch ───────────────────────────────────────────────────────

class TestExplainBatch:
    def test_returns_list(self, advisor):
        results = [_result("BTC"), _result("ETH", signal="SELL")]
        advices = advisor.explain_batch(results)
        assert len(advices) == 2

    def test_empty_batch(self, advisor):
        assert advisor.explain_batch([]) == []

    def test_exception_per_item_does_not_crash(self, advisor):
        bad_result = MagicMock(spec=SignalResult)
        bad_result.symbol = "BAD"
        bad_result.signal = None  # va lever une AttributeError
        bad_result.components = {}
        bad_result.score = 0
        bad_result.regime = "unknown"
        bad_result.confirmed = False
        bad_result.strength = 0.0

        good = _result("GOOD")
        advices = advisor.explain_batch([good, bad_result])
        assert len(advices) >= 1


# ── Tests mode LM Studio ──────────────────────────────────────────────────────

class TestLMStudioMode:
    def test_lm_studio_called_when_available(self):
        advisor = AIAdvisor(use_lm_studio=True, mode="auto")
        r = _result()
        with patch(
            "quant_hedge_ai.agents.intelligence.ai_advisor.AIAdvisor._ask_lm_studio",
            return_value="Conseil IA généré.",
        ) as mock_ask:
            a = advisor.explain(r)
            mock_ask.assert_called_once()
            assert a.source == "lm_studio"
            assert "Conseil IA généré." in a.text

    def test_fallback_to_deterministic_on_lm_studio_error(self):
        advisor = AIAdvisor(use_lm_studio=True, mode="auto")
        r = _result()
        with patch(
            "quant_hedge_ai.agents.intelligence.ai_advisor.AIAdvisor._ask_lm_studio",
            side_effect=RuntimeError("LM Studio indisponible"),
        ):
            a = advisor.explain(r)
            assert a.source == "deterministic"

    def test_mode_deterministic_skips_lm_studio(self):
        advisor = AIAdvisor(use_lm_studio=True, mode="deterministic")
        r = _result()
        with patch(
            "quant_hedge_ai.agents.intelligence.ai_advisor.AIAdvisor._ask_lm_studio",
        ) as mock_ask:
            advisor.explain(r)
            mock_ask.assert_not_called()

    def test_build_prompt_contains_symbol(self):
        advisor = AIAdvisor(use_lm_studio=False)
        r = _result(symbol="XRPUSDT")
        prompt = advisor._build_prompt(r, "medium", "moderate")
        assert "XRPUSDT" in prompt
        assert "BUY" in prompt

    def test_build_prompt_contains_regime(self):
        advisor = AIAdvisor(use_lm_studio=False)
        r = _result(regime="bear_trend")
        prompt = advisor._build_prompt(r, "high", "low")
        assert "baissière" in prompt

    def test_ask_lm_studio_uses_configured_token_budget(self):
        advisor = AIAdvisor(use_lm_studio=True, mode="auto")
        r = _result()

        with patch("lm_studio.ai_router.AIRouter.ask", return_value="ok") as mock_ask:
            assert advisor._ask_lm_studio(r, "medium", "moderate") == "ok"

        assert mock_ask.call_args.kwargs["max_tokens"] == _LM_STUDIO_MAX_TOKENS

    def test_non_actionable_hold_skips_lm_studio(self):
        advisor = AIAdvisor(use_lm_studio=True, mode="auto")
        r = _result(score=52, signal="HOLD", confirmed=False, strength=0.2)

        with patch(
            "quant_hedge_ai.agents.intelligence.ai_advisor.AIAdvisor._ask_lm_studio"
        ) as mock_ask:
            advice = advisor.explain(r)

        mock_ask.assert_not_called()
        assert advice.source == "deterministic"


# ── Tests EventBus emission ───────────────────────────────────────────────────

class TestEventBusEmission:
    def test_high_score_emits_event(self):
        advisor = AIAdvisor(use_lm_studio=False)
        r = _result(score=85, signal="BUY")
        with patch("event_bus.bus.EventBus.get") as mock_bus:
            mock_instance = MagicMock()
            mock_bus.return_value = mock_instance
            advisor.explain(r)
            assert mock_instance.emit.called

    def test_low_score_does_not_emit(self):
        advisor = AIAdvisor(use_lm_studio=False)
        r = _result(score=60, signal="HOLD")
        with patch("event_bus.bus.EventBus.get") as mock_bus:
            mock_instance = MagicMock()
            mock_bus.return_value = mock_instance
            advisor.explain(r)
            mock_instance.emit.assert_not_called()
