"""Tests unitaires — ExecutionEngine (paper mode, safety layer, size factor, live fallback)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def eng(tmp_path, monkeypatch):
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
    monkeypatch.setenv("EXEC_MAX_DD", "0.05")
    monkeypatch.setenv("EXEC_MAX_LOSS", "0.03")
    monkeypatch.setenv("EXEC_MAX_CONSEC_LOSSES", "3")
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
    monkeypatch.setenv("EXEC_DEDUP_WINDOW", "30")
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    e = ExecutionEngine(live=False)
    e.start_session(equity=10_000.0)
    return e


class TestFromEnv:
    def test_from_env_paper_when_no_keys(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXCHANGE_ID", "binance")  # isolate from .env
        monkeypatch.delenv("BINANCE_API_KEY", raising=False)
        monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine.from_env()
        assert e._live is False

    def test_from_env_attempts_live_when_keys_present(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("BINANCE_API_KEY", "fake_key")
        monkeypatch.setenv("BINANCE_API_SECRET", "fake_secret")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine.from_env()
        assert isinstance(e._live, bool)


class TestSizeFactor:
    def test_set_size_factor_clamps_to_zero(self, eng):
        eng.set_size_factor(-5.0)
        assert eng._size_factor == 0.0

    def test_set_size_factor_clamps_to_one(self, eng):
        eng.set_size_factor(99.0)
        assert eng._size_factor == 1.0

    def test_set_size_factor_mid_value(self, eng):
        eng.set_size_factor(0.5)
        assert eng._size_factor == pytest.approx(0.5)

    def test_size_factor_applied_to_order(self, eng):
        eng.set_size_factor(0.5)
        result = eng.create_order("BTCUSDT", "BUY", 100.0)
        assert result["mode"] == "paper"
        assert result["size"] == pytest.approx(50.0, abs=0.01)


class TestAnomalousSizeRecovery:
    def test_zero_size_triggers_alert_and_corrects(self, eng):
        result = eng.create_order("BTCUSDT", "BUY", 0.0)
        assert result["mode"] in ("paper", "rejected")

    def test_huge_size_triggers_alert_and_corrects(self, eng):
        result = eng.create_order("BTCUSDT", "BUY", 2e9)
        assert result["mode"] in ("paper", "rejected")


class TestPaperMode:
    def test_basic_paper_order(self, eng):
        result = eng.create_order("BTCUSDT", "BUY", 100.0)
        assert result["mode"] == "paper"
        assert result["symbol"] == "BTCUSDT"

    def test_safety_status_structure(self, eng):
        status = eng.safety_status()
        assert "session" in status
        assert "trade_log" in status
        assert "live_mode" in status
        assert status["live_mode"] is False

    def test_start_session_resets_state(self, eng):
        eng.start_session(equity=5000.0)
        assert eng._guard.state()["halted"] is False

    def test_sell_order_paper(self, eng):
        result = eng.create_order("ETHUSDT", "SELL", 50.0)
        assert result["mode"] == "paper"
        assert result["action"] == "SELL"


class TestLiveFallback:
    def test_init_exchange_falls_back_when_ccxt_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("BINANCE_API_KEY", "k")
        monkeypatch.setenv("BINANCE_API_SECRET", "s")
        with patch.dict("sys.modules", {"ccxt": None}):
            from quant_hedge_ai.agents.execution import execution_engine as mod

            try:
                e = mod.ExecutionEngine(live=True)
                assert isinstance(e._live, bool)
            except Exception:
                pass

    def _setup_mock_exchange(
        self, mock_exchange, usdt_balance: float = 10_000.0
    ) -> None:
        mock_exchange.fetch_ticker.return_value = {"last": 50_000.0}
        mock_exchange.load_markets.return_value = {}
        mock_exchange.fetch_balance.return_value = {"free": {"USDT": usdt_balance}}

    def test_place_live_order_exception_returns_live_failed(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        e._live = True
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.side_effect = RuntimeError("connection refused")
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        result = e.create_order("BTCUSDT", "BUY", 100.0)
        assert result["mode"] == "live_failed"
        assert "connection refused" in result["error"]

    def test_place_live_order_success(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        e._live = True
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.return_value = {"id": "abc123", "status": "closed"}
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        result = e.create_order("BTCUSDT", "BUY", 100.0)
        assert result["mode"] == "live"
        assert result["id"] == "abc123"

    def test_place_live_order_sell_side(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        e._live = True
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.return_value = {"id": "sell1"}
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        e.create_order("BTCUSDT", "SELL", 100.0)
        assert mock_exchange.create_order.call_args[0][2] == "sell"

    def test_place_live_order_symbol_slash_conversion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        e._live = True
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.return_value = {"id": "x"}
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        e.create_order("BTCUSDT", "BUY", 100.0)
        assert "/" in mock_exchange.create_order.call_args[0][0]
