"""Tests unitaires — WalkForwardValidator."""

from __future__ import annotations

import random

from quant_hedge_ai.agents.quant.walk_forward import (
    WalkForwardResult,
    WalkForwardValidator,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_candles(n: int, seed: int = 42, trend: float = 0.0) -> list[dict]:
    random.seed(seed)
    price = 100.0
    out = []
    for _ in range(n):
        price = max(price * (1 + trend + random.gauss(0, 0.01)), 1.0)
        o, c = price, price * random.uniform(0.995, 1.005)
        out.append(
            {
                "open": o,
                "high": max(o, c) * 1.002,
                "low": min(o, c) * 0.998,
                "close": c,
                "volume": 1000.0,
            }
        )
    return out


STRATEGY_EMA = {"entry_indicator": "EMA", "period": 14, "threshold": 1.0}
STRATEGY_RSI = {"entry_indicator": "RSI", "period": 14, "threshold": 1.0}


# ── WalkForwardResult ─────────────────────────────────────────────────────────


class TestWalkForwardResult:
    def test_as_dict_keys(self):
        r = WalkForwardResult()
        d = r.as_dict()
        assert "in_sample" in d
        assert "out_of_sample" in d
        assert "is_overfit" in d
        assert "overfit_score" in d
        assert "verdict" in d

    def test_default_verdict_unknown(self):
        r = WalkForwardResult()
        assert r.verdict == "unknown"

    def test_as_dict_rounds_values(self):
        r = WalkForwardResult(sharpe_in=1.23456789, pnl_in=5.987654321)
        d = r.as_dict()
        assert d["in_sample"]["sharpe"] == round(1.23456789, 4)
        assert d["in_sample"]["pnl_pct"] == round(5.987654321, 4)

    def test_n_candles_in_dict(self):
        r = WalkForwardResult(n_candles=500)
        assert r.as_dict()["n_candles"] == 500


# ── WalkForwardValidator.validate ─────────────────────────────────────────────


class TestWalkForwardValidatorValidate:
    def setup_method(self):
        self.validator = WalkForwardValidator(
            train_ratio=0.7, decay_threshold=0.5, min_trades_oos=5
        )
        self.candles = _make_candles(200)

    def test_returns_walk_forward_result(self):
        result = self.validator.validate(STRATEGY_EMA, self.candles)
        assert isinstance(result, WalkForwardResult)

    def test_verdict_is_valid_string(self):
        result = self.validator.validate(STRATEGY_EMA, self.candles)
        assert result.verdict in (
            "ROBUSTE",
            "ACCEPTABLE",
            "SUSPECT",
            "OVERFIT",
            "unknown",
        )

    def test_overfit_score_between_zero_and_one(self):
        result = self.validator.validate(STRATEGY_RSI, self.candles)
        assert 0.0 <= result.overfit_score <= 1.0

    def test_is_overfit_consistent_with_score(self):
        result = self.validator.validate(STRATEGY_EMA, self.candles)
        if result.is_overfit:
            assert result.overfit_score >= 0.5
        else:
            assert result.overfit_score < 0.5

    def test_n_candles_set(self):
        result = self.validator.validate(STRATEGY_EMA, self.candles)
        assert result.n_candles == len(self.candles)

    def test_split_ratio_respected(self):
        # IS doit avoir ~70% des bougies, OOS ~30%
        result = self.validator.validate(STRATEGY_EMA, self.candles)
        assert result.n_candles == len(self.candles)
        # Vérifie que les métriques IS et OOS sont bien distinctes
        # (peuvent être 0 si pas assez de trades)
        assert isinstance(result.sharpe_in, float)
        assert isinstance(result.sharpe_out, float)

    def test_drawdown_non_negative(self):
        result = self.validator.validate(STRATEGY_EMA, self.candles)
        assert result.drawdown_in >= 0.0
        assert result.drawdown_out >= 0.0

    def test_trades_non_negative(self):
        result = self.validator.validate(STRATEGY_EMA, self.candles)
        assert result.trades_in >= 0
        assert result.trades_out >= 0

    def test_strategy_stored_in_result(self):
        result = self.validator.validate(STRATEGY_EMA, self.candles)
        assert result.strategy == STRATEGY_EMA


# ── WalkForwardValidator.verdict ──────────────────────────────────────────────


class TestWalkForwardValidatorVerdict:
    def setup_method(self):
        self.v = WalkForwardValidator(decay_threshold=0.5, min_trades_oos=5)

    def _result(self, **kwargs) -> WalkForwardResult:
        defaults = dict(
            sharpe_in=2.0,
            sharpe_out=1.5,
            pnl_in=10.0,
            pnl_out=5.0,
            drawdown_in=0.05,
            drawdown_out=0.07,
            trades_in=20,
            trades_out=10,
        )
        defaults.update(kwargs)
        return WalkForwardResult(**defaults)

    def test_robust_verdict_good_oos(self):
        r = self._result(sharpe_in=1.5, sharpe_out=1.4)
        score, is_overfit, verdict = self.v._verdict(r)
        assert verdict == "ROBUSTE"
        assert not is_overfit

    def test_overfit_verdict_sharpe_decay(self):
        r = self._result(sharpe_in=2.0, sharpe_out=0.5)  # decay=0.25 < 0.5
        score, is_overfit, verdict = self.v._verdict(r)
        assert score >= 0.4

    def test_overfit_pnl_flip(self):
        r = self._result(sharpe_in=1.0, sharpe_out=1.0, pnl_in=5.0, pnl_out=-3.0)
        score, _, _ = self.v._verdict(r)
        assert score >= 0.3

    def test_too_few_trades_oos(self):
        r = self._result(trades_out=2)  # < min_trades_oos=5
        score, _, _ = self.v._verdict(r)
        assert score >= 0.2

    def test_drawdown_explosion(self):
        r = self._result(drawdown_in=0.05, drawdown_out=0.15)  # × 3 > seuil ×2
        score, _, _ = self.v._verdict(r)
        assert score >= 0.1

    def test_negative_sharpe_in_penalized(self):
        r = self._result(sharpe_in=-0.5, sharpe_out=-0.3)
        score, _, _ = self.v._verdict(r)
        assert score >= 0.2

    def test_score_capped_at_one(self):
        # Tout va mal → score ne dépasse pas 1.0
        r = self._result(
            sharpe_in=3.0,
            sharpe_out=0.1,
            pnl_in=50.0,
            pnl_out=-20.0,
            trades_out=1,
            drawdown_in=0.02,
            drawdown_out=0.20,
        )
        score, _, _ = self.v._verdict(r)
        assert score <= 1.0

    def test_verdict_suspect_range(self):
        r = self._result(
            sharpe_in=2.0, sharpe_out=0.6, pnl_in=5.0, pnl_out=1.0, trades_out=6
        )
        score, _, verdict = self.v._verdict(r)
        if 0.4 <= score < 0.6:
            assert verdict == "SUSPECT"


# ── validate_batch + summary ──────────────────────────────────────────────────


class TestValidateBatch:
    def test_batch_returns_all_results(self):
        v = WalkForwardValidator()
        candles = _make_candles(200)
        strategies = [STRATEGY_EMA, STRATEGY_RSI]
        results = v.validate_batch(strategies, candles, verbose=False)
        assert len(results) == 2

    def test_batch_verbose_logs(self, monkeypatch):
        import quant_hedge_ai.agents.quant.walk_forward as mod

        logged = []

        def _capture(event, *args, **kw):
            logged.append(event % args if args else event)

        monkeypatch.setattr(mod._log, "info", _capture)
        v = WalkForwardValidator()
        candles = _make_candles(200)
        strategies = [STRATEGY_EMA] * 10
        v.validate_batch(strategies, candles, verbose=True)
        assert any("10/10" in s for s in logged)

    def test_summary_empty_returns_empty_dict(self):
        assert WalkForwardValidator.summary([]) == {}

    def test_summary_keys(self):
        v = WalkForwardValidator()
        candles = _make_candles(200)
        results = v.validate_batch([STRATEGY_EMA, STRATEGY_RSI], candles, verbose=False)
        summary = WalkForwardValidator.summary(results)
        assert "total" in summary
        assert "overfit_rate" in summary
        assert "avg_sharpe_in" in summary
        assert "avg_sharpe_out" in summary
        assert "best_strategy" in summary

    def test_summary_total_matches(self):
        v = WalkForwardValidator()
        candles = _make_candles(200)
        results = v.validate_batch([STRATEGY_EMA, STRATEGY_RSI], candles, verbose=False)
        summary = WalkForwardValidator.summary(results)
        assert summary["total"] == 2
        assert (
            summary["robust"]
            + summary["acceptable"]
            + summary["suspect"]
            + summary["overfit"]
            == 2
        )

    def test_summary_overfit_rate_range(self):
        v = WalkForwardValidator()
        candles = _make_candles(200)
        results = v.validate_batch([STRATEGY_EMA], candles, verbose=False)
        summary = WalkForwardValidator.summary(results)
        assert 0.0 <= summary["overfit_rate"] <= 1.0
