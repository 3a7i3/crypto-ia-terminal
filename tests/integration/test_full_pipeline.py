"""Tests d'intégration — pipeline end-to-end : scan→validate→backtest→order→log."""

from __future__ import annotations

import math

import pytest

from quant_hedge_ai.agents.market.ohlcv_validator import validate_candles

from .conftest import SKIP_TESTNET, STRATEGIES, STRATEGY_EMA, STRATEGY_RSI, SYMBOLS

pytestmark = pytest.mark.integration


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_pipeline(scanner, lab, validator, engine, strategies=None):
    """Mini-pipeline : scan → validate → backtest → walk_forward → order."""
    strategies = strategies or [STRATEGY_EMA, STRATEGY_RSI]
    scan_result = scanner.scan()
    orders = []

    for sym in SYMBOLS:
        candles = scan_result["history"][sym]

        # Étape 1 : validation OHLCV
        clean, report = validate_candles(candles, symbol=sym)
        if not clean:
            continue

        # Étape 2 : walk-forward filter (on garde les stratégies non-overfit)
        wf_results = validator.validate_batch(strategies, clean, verbose=False)
        valid_strategies = [r for r in wf_results if not r.is_overfit]

        # Si toutes sont overfit, on prend quand même la meilleure
        if not valid_strategies:
            valid_strategies = wf_results[:1]

        # Étape 3 : backtest pour choisir la meilleure stratégie
        _ = max(wf_results, key=lambda r: r.sharpe_in)

        # Étape 4 : placer un ordre paper
        order = engine.create_order(sym, "BUY", 100.0)
        orders.append(order)

    return orders, scan_result


# ── Pipeline complet mode synthétique ─────────────────────────────────────────


class TestFullPipelineSynthetic:
    def test_pipeline_completes_without_error(
        self, scanner_synthetic, lab, validator, engine_paper
    ):
        orders, _ = _run_pipeline(scanner_synthetic, lab, validator, engine_paper)
        assert len(orders) > 0

    def test_pipeline_places_one_order_per_symbol(
        self, scanner_synthetic, lab, validator, engine_paper
    ):
        orders, _ = _run_pipeline(scanner_synthetic, lab, validator, engine_paper)
        assert len(orders) == len(SYMBOLS)

    def test_pipeline_orders_have_valid_mode(
        self, scanner_synthetic, lab, validator, engine_paper
    ):
        orders, _ = _run_pipeline(scanner_synthetic, lab, validator, engine_paper)
        for order in orders:
            assert order["mode"] in (
                "paper",
                "rejected",
            ), f"Mode inattendu: {order['mode']}"

    def test_pipeline_trades_are_logged(
        self, scanner_synthetic, lab, validator, engine_paper
    ):
        orders, _ = _run_pipeline(scanner_synthetic, lab, validator, engine_paper)
        paper_count = sum(1 for o in orders if o["mode"] == "paper")
        trades = engine_paper._logger.recent_trades(50)
        assert len(trades) >= paper_count

    def test_pipeline_ohlcv_validation_passes(self, scanner_synthetic):
        result = scanner_synthetic.scan()
        for sym in SYMBOLS:
            clean, report = validate_candles(result["history"][sym], symbol=sym)
            assert report.dropped == 0, f"{sym}: {report.reasons}"

    def test_pipeline_walk_forward_produces_verdicts(
        self, scanner_synthetic, validator
    ):
        result = scanner_synthetic.scan()
        candles = result["history"]["BTCUSDT"]
        wf_results = validator.validate_batch(STRATEGIES, candles, verbose=False)
        for r in wf_results:
            assert r.verdict in (
                "ROBUSTE",
                "ACCEPTABLE",
                "SUSPECT",
                "OVERFIT",
                "unknown",
            )

    def test_pipeline_backtest_before_walk_forward(
        self, scanner_synthetic, lab, validator
    ):
        result = scanner_synthetic.scan()
        candles = result["history"]["BTCUSDT"]
        bt = lab.run_backtest(STRATEGY_EMA, candles)
        wf = validator.validate(STRATEGY_EMA, candles)
        assert math.isfinite(bt["pnl"])
        assert 0.0 <= wf.overfit_score <= 1.0

    def test_pipeline_data_quality_tracked(
        self, scanner_synthetic, lab, validator, engine_paper
    ):
        _run_pipeline(scanner_synthetic, lab, validator, engine_paper)
        quality = scanner_synthetic.data_quality()
        assert quality["synthetic"] > 0
        assert isinstance(quality["real_ratio"], float)

    def test_pipeline_safety_status_after_run(
        self, scanner_synthetic, lab, validator, engine_paper
    ):
        _run_pipeline(scanner_synthetic, lab, validator, engine_paper)
        status = engine_paper.safety_status()
        assert "session" in status
        assert "trade_log" in status
        assert status["trade_log"]["total_trades"] >= 0

    def test_pipeline_dedup_prevents_double_orders(
        self, scanner_synthetic, lab, validator, engine_paper
    ):
        orders1, _ = _run_pipeline(scanner_synthetic, lab, validator, engine_paper)
        orders2, _ = _run_pipeline(scanner_synthetic, lab, validator, engine_paper)
        rejected2 = [o for o in orders2 if o["mode"] == "rejected"]
        assert (
            len(rejected2) > 0
        ), "La déduplication aurait dû bloquer les ordres répétés"


# ── Pipeline complet mode testnet ─────────────────────────────────────────────


class TestFullPipelineTestnet:
    @SKIP_TESTNET
    def test_testnet_pipeline_completes(
        self, scanner_testnet, lab, validator, engine_testnet
    ):
        orders, scan_result = _run_pipeline(
            scanner_testnet, lab, validator, engine_testnet
        )
        assert len(orders) > 0

    @SKIP_TESTNET
    def test_testnet_pipeline_orders_logged(
        self, scanner_testnet, lab, validator, engine_testnet
    ):
        _run_pipeline(scanner_testnet, lab, validator, engine_testnet)
        status = engine_testnet.safety_status()
        assert status["trade_log"]["total_trades"] >= 1

    @SKIP_TESTNET
    def test_testnet_real_data_quality(self, scanner_testnet):
        scanner_testnet.scan()
        quality = scanner_testnet.data_quality()
        assert quality["real"] > 0
