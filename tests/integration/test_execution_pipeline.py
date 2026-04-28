"""Tests d'intégration — ExecutionEngine (paper + testnet Binance)."""

from __future__ import annotations

import pytest

from .conftest import SKIP_TESTNET

pytestmark = pytest.mark.integration


# ── Mode paper ────────────────────────────────────────────────────────────────


class TestExecutionPaperMode:
    def test_safety_status_returns_expected_keys(self, engine_paper):
        status = engine_paper.safety_status()
        assert "session" in status
        assert "trade_log" in status
        assert "live_mode" in status

    def test_live_mode_is_false_in_paper(self, engine_paper):
        assert engine_paper.safety_status()["live_mode"] is False

    def test_session_initialized_not_halted(self, engine_paper):
        status = engine_paper.safety_status()
        assert status["session"]["halted"] is False

    def test_paper_order_returns_paper_mode(self, engine_paper):
        result = engine_paper.create_order("BTCUSDT", "BUY", 100.0)
        assert result["mode"] == "paper"
        assert result["symbol"] == "BTCUSDT"
        assert result["action"].upper() == "BUY"

    def test_paper_order_is_logged(self, engine_paper):
        engine_paper.create_order("ETHUSDT", "BUY", 50.0)
        trades = engine_paper._logger.recent_trades(10)
        assert any(t["symbol"] == "ETHUSDT" for t in trades)

    def test_duplicate_order_rejected_in_window(self, engine_paper):
        engine_paper.create_order("BTCUSDT", "BUY", 200.0)
        result2 = engine_paper.create_order("BTCUSDT", "BUY", 200.0)
        assert result2["mode"] == "rejected"
        assert "duplicate" in result2["error"].lower()

    def test_oversized_order_rejected(self, engine_paper):
        result = engine_paper.create_order("BTCUSDT", "BUY", 999_999.0)
        assert result["mode"] == "rejected"

    def test_trade_count_increments(self, engine_paper):
        before = engine_paper.safety_status()["trade_log"]["total_trades"]
        engine_paper.create_order("SOLUSDT", "BUY", 75.0)
        after = engine_paper.safety_status()["trade_log"]["total_trades"]
        assert after > before

    def test_session_pnl_tracked_after_trade(self, engine_paper):
        pnl = engine_paper._logger.session_pnl()
        assert isinstance(pnl, float)

    def test_multiple_symbols_independent_dedup(self, engine_paper):
        r_btc = engine_paper.create_order("BTCUSDT", "SELL", 100.0)
        r_eth = engine_paper.create_order("ETHUSDT", "SELL", 100.0)
        assert r_btc["mode"] == "paper"
        assert r_eth["mode"] == "paper"

    def test_order_size_in_result(self, engine_paper):
        result = engine_paper.create_order("BNBUSDT", "BUY", 123.45)
        assert abs(result["size"] - 123.45) < 0.01


# ── Safety layer (halt conditions) ────────────────────────────────────────────


class TestExecutionSafetyLayer:
    def test_halt_blocks_subsequent_orders(self, engine_paper):
        engine_paper._guard._state.halted = True
        engine_paper._guard._state.halt_reason = "test halt"
        result = engine_paper.create_order("BTCUSDT", "BUY", 100.0)
        assert result["mode"] == "rejected"
        engine_paper._guard.reset()

    def test_reset_restores_order_flow(self, engine_paper):
        engine_paper._guard._state.halted = True
        engine_paper._guard._state.halt_reason = "test"
        engine_paper._guard.reset()
        result = engine_paper.create_order("BTCUSDT", "BUY", 50.0)
        assert result["mode"] == "paper"

    def test_consecutive_losses_trigger_halt(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_CONSEC_LOSSES", "2")
        monkeypatch.setenv("EXEC_MAX_DD", "0.99")
        monkeypatch.setenv("EXEC_MAX_LOSS", "0.99")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        eng = ExecutionEngine(live=False)
        eng.start_session(equity=1000.0)
        eng._guard.record_trade(-10.0, 990.0)
        eng._guard.record_trade(-10.0, 980.0)
        assert eng._guard.is_halted


# ── Mode testnet Binance ───────────────────────────────────────────────────────


class TestExecutionTestnet:
    @SKIP_TESTNET
    def test_engine_initializes_in_live_mode(self, engine_testnet):
        assert engine_testnet.safety_status()["live_mode"] is True

    @SKIP_TESTNET
    def test_testnet_order_returns_live_or_failed(self, engine_testnet):
        result = engine_testnet.create_order("BTCUSDT", "BUY", 0.001)
        assert result["mode"] in ("live", "live_failed")

    @SKIP_TESTNET
    def test_testnet_order_logged_in_db(self, engine_testnet):
        engine_testnet.create_order("ETHUSDT", "BUY", 0.01)
        trades = engine_testnet._logger.recent_trades(5)
        assert len(trades) >= 1

    @SKIP_TESTNET
    def test_testnet_safety_status_after_order(self, engine_testnet):
        engine_testnet.create_order("BTCUSDT", "BUY", 0.001)
        status = engine_testnet.safety_status()
        assert status["trade_log"]["total_trades"] >= 1
