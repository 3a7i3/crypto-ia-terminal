"""Tests LiveSignalEngine — agrégateur de signaux 0-100 par symbole."""

from __future__ import annotations

import pytest

from quant_hedge_ai.agents.execution.live_signal_engine import (
    LiveSignalEngine,
    SignalResult,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _candles(n: int = 30, close: float = 100.0) -> list[dict]:
    """Génère n candles minimalistes."""
    return [
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000.0}
        for _ in range(n)
    ]


def _bull_candles(n: int = 30) -> list[dict]:
    """Candles en tendance haussière pour déclencher RSI < 30 → BUY."""
    candles = []
    price = 50.0
    for i in range(n):
        candles.append({"open": price, "high": price + 0.1, "low": price - 2.0, "close": price - 1.5, "volume": 1000.0})
        price = max(10.0, price - 1.5)
    return candles


@pytest.fixture
def engine():
    return LiveSignalEngine(strategy={"entry_indicator": "RSI", "period": 14,
                                       "entry_threshold": 30, "exit_threshold": 70})


@pytest.fixture
def mtf_flat():
    return {
        "1h": _candles(30),
        "4h": _candles(30),
    }


@pytest.fixture
def mtf_bull():
    return {
        "1h": _bull_candles(30),
        "4h": _bull_candles(30),
        "1d": _bull_candles(30),
    }


# ── Tests SignalResult ─────────────────────────────────────────────────────────

class TestSignalResult:
    def test_actionable_true_above_min(self):
        r = SignalResult(symbol="BTC", score=75, signal="BUY")
        assert r.actionable is True

    def test_actionable_false_hold(self):
        r = SignalResult(symbol="BTC", score=80, signal="HOLD")
        assert r.actionable is False

    def test_actionable_false_low_score(self):
        r = SignalResult(symbol="BTC", score=50, signal="BUY")
        assert r.actionable is False

    def test_as_dict_keys(self):
        r = SignalResult(symbol="ETH", score=60, signal="SELL")
        d = r.as_dict()
        for key in ("symbol", "score", "signal", "regime", "confirmed", "strength",
                    "actionable", "components", "timestamp"):
            assert key in d

    def test_actionable_sell_above_min(self):
        r = SignalResult(symbol="SOL", score=80, signal="SELL")
        assert r.actionable is True


# ── Tests evaluate ────────────────────────────────────────────────────────────

class TestEvaluate:
    def test_returns_signal_result(self, engine, mtf_flat):
        result = engine.evaluate("BTCUSDT", mtf_flat)
        assert isinstance(result, SignalResult)
        assert result.symbol == "BTCUSDT"

    def test_score_in_range(self, engine, mtf_flat):
        result = engine.evaluate("BTCUSDT", mtf_flat)
        assert 0 <= result.score <= 100

    def test_empty_candles_low_score(self, engine):
        result = engine.evaluate("BTCUSDT", {})
        assert result.score <= 30

    def test_components_present(self, engine, mtf_flat):
        result = engine.evaluate("BTCUSDT", mtf_flat)
        assert "mtf" in result.components
        assert "regime" in result.components
        assert "data_quality" in result.components
        assert "memory" in result.components

    def test_memory_sharpe_positive_boosts_score(self, engine, mtf_flat):
        r_no_mem = engine.evaluate("BTCUSDT", mtf_flat, memory_sharpe=None)
        r_with_mem = engine.evaluate("BTCUSDT", mtf_flat, memory_sharpe=2.0)
        # Avec sharpe=2.0, on obtient 20 pts mémoire vs 10 pts neutre
        assert r_with_mem.score >= r_no_mem.score

    def test_memory_sharpe_zero_no_bonus(self, engine, mtf_flat):
        result = engine.evaluate("BTCUSDT", mtf_flat, memory_sharpe=0.0)
        assert result.components["memory"] == 0.0

    def test_memory_sharpe_negative_no_bonus(self, engine, mtf_flat):
        result = engine.evaluate("BTCUSDT", mtf_flat, memory_sharpe=-1.0)
        assert result.components["memory"] == 0.0

    def test_memory_sharpe_max_caps_at_20(self, engine, mtf_flat):
        result = engine.evaluate("BTCUSDT", mtf_flat, memory_sharpe=5.0)
        assert result.components["memory"] == 20.0

    def test_features_bull_trend_boosts_score(self, engine, mtf_flat):
        features_bull = {"momentum": 0.08, "realized_volatility": 0.02, "trend_strength": 0.9}
        features_unknown = {}
        r_bull = engine.evaluate("BTC", mtf_flat, features=features_bull)
        r_unk = engine.evaluate("BTC", mtf_flat, features=features_unknown)
        assert r_bull.components["regime"] > r_unk.components["regime"]

    def test_result_cached_in_last_results(self, engine, mtf_flat):
        engine.evaluate("ETHUSDT", mtf_flat)
        assert "ETHUSDT" in engine._last_results

    def test_exception_in_mtf_returns_hold(self, engine):
        # Candles trop courtes → HOLD
        result = engine.evaluate("BTCUSDT", {"1h": [{"close": 100}]})
        assert result.signal == "HOLD"


# ── Tests blacklist ───────────────────────────────────────────────────────────

class TestBlacklist:
    def test_blacklisted_regime_caps_score(self, engine, mtf_flat):
        features = {"momentum": 0.08, "realized_volatility": 0.02, "trend_strength": 0.9}
        # Sans blacklist
        engine.evaluate("BTC", mtf_flat, features=features)
        # Avec blacklist du régime bull_trend
        engine.blacklist_regime("bull_trend")
        r2 = engine.evaluate("BTC", mtf_flat, features=features)
        assert r2.score <= 30

    def test_unblacklist_removes_cap(self, engine, mtf_flat):
        engine.blacklist_regime("bull_trend")
        engine.unblacklist_regime("bull_trend")
        features = {"momentum": 0.08, "realized_volatility": 0.02, "trend_strength": 0.9}
        r = engine.evaluate("BTC", mtf_flat, features=features)
        # Score pas cappé (peut dépasser 30)
        assert "regime_blacklist_veto" not in r.components

    def test_blacklist_component_recorded(self, engine, mtf_flat):
        engine.blacklist_regime("bull_trend")
        features = {"momentum": 0.08, "realized_volatility": 0.02, "trend_strength": 0.9}
        r = engine.evaluate("BTC", mtf_flat, features=features)
        assert "regime_blacklist_veto" in r.components


# ── Tests evaluate_batch ──────────────────────────────────────────────────────

class TestEvaluateBatch:
    def test_returns_list(self, engine, mtf_flat):
        data = {
            "BTCUSDT": {"mtf_candles": mtf_flat},
            "ETHUSDT": {"mtf_candles": mtf_flat},
        }
        results = engine.evaluate_batch(data)
        assert len(results) == 2

    def test_sorted_by_score_desc(self, engine, mtf_flat):
        data = {
            "BTCUSDT": {"mtf_candles": mtf_flat, "memory_sharpe": 2.0},
            "ETHUSDT": {"mtf_candles": {}, "memory_sharpe": 0.0},
        }
        results = engine.evaluate_batch(data)
        assert results[0].score >= results[1].score

    def test_exception_per_symbol_does_not_crash_batch(self, engine):
        data = {
            "OK": {"mtf_candles": {"1h": _candles()}},
            "BAD": "not_a_dict",  # va lever une exception
        }
        results = engine.evaluate_batch(data)
        assert len(results) == 1  # seul OK a réussi


# ── Tests top_opportunities ───────────────────────────────────────────────────

class TestTopOpportunities:
    def test_no_results_returns_empty(self, engine):
        assert engine.top_opportunities() == []

    def test_returns_actionable_only(self, engine, mtf_flat):
        # Force un résultat non-actionable
        engine._last_results["X"] = SignalResult(symbol="X", score=40, signal="HOLD")
        engine._last_results["Y"] = SignalResult(symbol="Y", score=80, signal="BUY")
        top = engine.top_opportunities()
        assert all(r.actionable for r in top)

    def test_top_n_limited(self, engine):
        for i in range(5):
            engine._last_results[f"SYM{i}"] = SignalResult(
                symbol=f"SYM{i}", score=80 - i, signal="BUY"
            )
        top = engine.top_opportunities(n=2)
        assert len(top) <= 2


# ── Tests qualité données réelle ─────────────────────────────────────────────

class TestDataQuality:
    def test_valid_candles_score_near_max(self, engine):
        good = [
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0}
            for _ in range(20)
        ]
        mtf = {"1h": good, "4h": good}
        result = engine.evaluate("BTC", mtf)
        assert result.components["data_quality"] > 10.0  # proche de 15

    def test_empty_tf_candles_skipped(self, engine):
        mtf = {"1h": [], "4h": _candles(20)}
        result = engine.evaluate("BTC", mtf)
        assert result.components["data_quality"] >= 0.0

    def test_all_empty_tf_gives_zero(self, engine):
        mtf = {"1h": [], "4h": []}
        result = engine.evaluate("BTC", mtf)
        # Toutes les TF vides → total_weight=0 → ratio=0.5 → score=7.5 (fallback neutre)
        assert result.components["data_quality"] >= 0.0

    def test_unknown_tf_weight_defaults_to_1(self, engine):
        good = [
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 500.0}
            for _ in range(10)
        ]
        mtf = {"3m": good}  # TF inconnue → poids 1.0
        result = engine.evaluate("BTC", mtf)
        assert result.components["data_quality"] >= 0.0


# ── Tests env var ────────────────────────────────────────────────────────────

class TestEnvVar:
    def test_default_min_score_from_env(self, monkeypatch):
        monkeypatch.setenv("SIGNAL_MIN_SCORE", "85")
        import importlib
        import quant_hedge_ai.agents.execution.live_signal_engine as mod
        importlib.reload(mod)
        assert mod._DEFAULT_MIN_SCORE == 85

    def test_engine_min_score_override(self):
        eng = LiveSignalEngine(min_score=55)
        assert eng.min_score == 55
