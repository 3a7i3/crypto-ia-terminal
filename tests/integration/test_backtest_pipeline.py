"""Tests d'intégration — BacktestLab + WalkForwardValidator sur données du scanner."""

from __future__ import annotations

import math

import pytest

from quant_hedge_ai.agents.quant.walk_forward import WalkForwardResult

from .conftest import SKIP_TESTNET, STRATEGIES, STRATEGY_EMA, STRATEGY_RSI

pytestmark = pytest.mark.integration


# ── BacktestLab sur données synthétiques ──────────────────────────────────────


class TestBacktestPipeline:
    def _get_candles(self, scanner_synthetic):
        result = scanner_synthetic.scan()
        return result["history"]["BTCUSDT"]

    def test_backtest_returns_expected_keys(self, scanner_synthetic, lab):
        candles = self._get_candles(scanner_synthetic)
        result = lab.run_backtest(STRATEGY_EMA, candles)
        for key in ("pnl", "sharpe", "drawdown", "win_rate", "trades", "bars"):
            assert key in result, f"Clé manquante : {key}"

    def test_backtest_bars_matches_candle_count(self, scanner_synthetic, lab):
        candles = self._get_candles(scanner_synthetic)
        result = lab.run_backtest(STRATEGY_EMA, candles)
        assert result["bars"] == len(candles)

    def test_backtest_pnl_is_finite_float(self, scanner_synthetic, lab):
        candles = self._get_candles(scanner_synthetic)
        result = lab.run_backtest(STRATEGY_EMA, candles)
        assert isinstance(result["pnl"], float)
        assert math.isfinite(result["pnl"])

    def test_backtest_sharpe_is_finite_float(self, scanner_synthetic, lab):
        candles = self._get_candles(scanner_synthetic)
        result = lab.run_backtest(STRATEGY_RSI, candles)
        assert isinstance(result["sharpe"], float)
        assert not math.isnan(result["sharpe"])

    def test_backtest_drawdown_between_zero_and_one(self, scanner_synthetic, lab):
        candles = self._get_candles(scanner_synthetic)
        result = lab.run_backtest(STRATEGY_EMA, candles)
        assert 0.0 <= result["drawdown"] <= 1.0

    def test_backtest_win_rate_between_zero_and_one(self, scanner_synthetic, lab):
        candles = self._get_candles(scanner_synthetic)
        result = lab.run_backtest(STRATEGY_RSI, candles)
        assert 0.0 <= result["win_rate"] <= 1.0

    def test_backtest_on_both_symbols(self, scanner_synthetic, lab):
        result_scan = scanner_synthetic.scan()
        for sym in ("BTCUSDT", "ETHUSDT"):
            candles = result_scan["history"][sym]
            result = lab.run_backtest(STRATEGY_EMA, candles)
            assert result["bars"] == len(candles)

    def test_backtest_strategy_stored_in_result(self, scanner_synthetic, lab):
        candles = self._get_candles(scanner_synthetic)
        result = lab.run_backtest(STRATEGY_EMA, candles)
        assert result.get("strategy") == STRATEGY_EMA


# ── WalkForwardValidator sur données synthétiques ────────────────────────────


class TestWalkForwardPipeline:
    def _get_candles(self, scanner_synthetic):
        result = scanner_synthetic.scan()
        return result["history"]["BTCUSDT"]

    def test_validate_returns_walk_forward_result(self, scanner_synthetic, validator):
        candles = self._get_candles(scanner_synthetic)
        result = validator.validate(STRATEGY_EMA, candles)
        assert isinstance(result, WalkForwardResult)

    def test_verdict_is_valid_string(self, scanner_synthetic, validator):
        candles = self._get_candles(scanner_synthetic)
        result = validator.validate(STRATEGY_EMA, candles)
        assert result.verdict in (
            "ROBUSTE",
            "ACCEPTABLE",
            "SUSPECT",
            "OVERFIT",
            "unknown",
        )

    def test_overfit_score_in_range(self, scanner_synthetic, validator):
        candles = self._get_candles(scanner_synthetic)
        result = validator.validate(STRATEGY_RSI, candles)
        assert 0.0 <= result.overfit_score <= 1.0

    def test_n_candles_matches_input(self, scanner_synthetic, validator):
        candles = self._get_candles(scanner_synthetic)
        result = validator.validate(STRATEGY_EMA, candles)
        assert result.n_candles == len(candles)

    def test_validate_batch_returns_all_results(self, scanner_synthetic, validator):
        candles = self._get_candles(scanner_synthetic)
        results = validator.validate_batch(STRATEGIES, candles, verbose=False)
        assert len(results) == len(STRATEGIES)

    def test_summary_has_required_keys(self, scanner_synthetic, validator):
        candles = self._get_candles(scanner_synthetic)
        results = validator.validate_batch(STRATEGIES, candles, verbose=False)
        summary = validator.summary(results)
        for key in (
            "total",
            "overfit_rate",
            "avg_sharpe_in",
            "avg_sharpe_out",
            "best_strategy",
        ):
            assert key in summary, f"Clé manquante dans summary : {key}"

    def test_summary_total_matches_strategy_count(self, scanner_synthetic, validator):
        candles = self._get_candles(scanner_synthetic)
        results = validator.validate_batch(STRATEGIES, candles, verbose=False)
        summary = validator.summary(results)
        assert summary["total"] == len(STRATEGIES)

    def test_summary_counts_sum_to_total(self, scanner_synthetic, validator):
        candles = self._get_candles(scanner_synthetic)
        results = validator.validate_batch(STRATEGIES, candles, verbose=False)
        s = validator.summary(results)
        count_sum = s["robust"] + s["acceptable"] + s["suspect"] + s["overfit"]
        assert count_sum == s["total"]


# ── Testnet (données réelles pour le backtest) ────────────────────────────────


class TestBacktestOnTestnetData:
    @SKIP_TESTNET
    def test_backtest_on_real_btc_data(self, scanner_testnet, lab):
        result_scan = scanner_testnet.scan()
        candles = result_scan["history"]["BTCUSDT"]
        result = lab.run_backtest(STRATEGY_EMA, candles)
        assert result["bars"] == len(candles)
        assert isinstance(result["sharpe"], float)

    @SKIP_TESTNET
    def test_walk_forward_on_real_btc_data(self, scanner_testnet, validator):
        result_scan = scanner_testnet.scan()
        candles = result_scan["history"]["BTCUSDT"]
        result = validator.validate(STRATEGY_EMA, candles)
        assert isinstance(result, WalkForwardResult)
        assert 0.0 <= result.overfit_score <= 1.0
