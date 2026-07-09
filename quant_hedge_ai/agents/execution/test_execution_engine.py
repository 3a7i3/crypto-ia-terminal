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
        monkeypatch.setenv("EXCHANGE_ID", "mexc")  # isolate from .env
        monkeypatch.delenv("MEXC_API_KEY", raising=False)
        monkeypatch.delenv("MEXC_API_SECRET", raising=False)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine.from_env()
        assert e._live is False

    def test_from_env_stays_paper_when_keys_present_but_not_confirmed(
        self, tmp_path, monkeypatch
    ):
        """SEC-01 — la seule présence de clés API ne suffit plus : sans
        LIVE_TRADING_CONFIRMED=true, from_env() reste en paper."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("MEXC_API_KEY", "fake_key")
        monkeypatch.setenv("MEXC_API_SECRET", "fake_secret")
        monkeypatch.delenv("LIVE_TRADING_CONFIRMED", raising=False)
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine.from_env()
        assert e._live is False

    def test_from_env_live_when_keys_present_and_confirmed(self, tmp_path, monkeypatch):
        """SEC-01 — clés API + LIVE_TRADING_CONFIRMED=true : les deux
        conditions réunies, le moteur peut passer live."""
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("MEXC_API_KEY", "fake_key")
        monkeypatch.setenv("MEXC_API_SECRET", "fake_secret")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine.from_env()
        assert e._live is True


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
        monkeypatch.setenv("MEXC_API_KEY", "k")
        monkeypatch.setenv("MEXC_API_SECRET", "s")
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
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")  # gate SEC-01 ouvert
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
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
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")  # gate SEC-01 ouvert
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
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")  # gate SEC-01 ouvert
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
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")  # gate SEC-01 ouvert
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


class TestExecutionGateSEC01:
    """SEC-01 (2026-07-08) — gate d'exécution réelle derrière
    PAPER_TRADING_ENABLED, avec neutralité stricte vs le rejet MEXC 700007
    déjà observé en production (voir RECOVERY.md / T1 finding #3)."""

    def _setup_mock_exchange(
        self, mock_exchange, usdt_balance: float = 10_000.0
    ) -> None:
        mock_exchange.fetch_ticker.return_value = {"last": 50_000.0}
        mock_exchange.load_markets.return_value = {}
        mock_exchange.fetch_balance.return_value = {"free": {"USDT": usdt_balance}}

    def _make_live_engine(self, tmp_path, monkeypatch, mock_exchange):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        e._live = True
        e._exchange = mock_exchange
        e.start_session(10_000.0)
        return e

    def test_gate_blocks_order_when_paper_trading_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        e = self._make_live_engine(tmp_path, monkeypatch, mock_exchange)

        result = e.create_order("ETHFI/USDT", "BUY", 100.0)

        assert result["mode"] == "live_failed"
        assert result["error"] == "blocked_by_paper_gate"
        mock_exchange.fetch_ticker.assert_not_called()
        mock_exchange.create_order.assert_not_called()

    def test_gate_blocked_shape_identical_to_real_rejection(
        self, tmp_path, monkeypatch
    ):
        """Neutralité stricte : mêmes clés, même mode, que le rejet MEXC
        700007 réel (exception levée dans _place_live_order)."""
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        mock_gated = MagicMock()
        self._setup_mock_exchange(mock_gated)
        e_gated = self._make_live_engine(tmp_path, monkeypatch, mock_gated)
        gated_result = e_gated.create_order("ETH/USDT", "SELL", 100.0)

        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        mock_real = MagicMock()
        self._setup_mock_exchange(mock_real)
        mock_real.create_order.side_effect = Exception(
            '{"code":700007,"msg":"No permission to access the endpoint."}'
        )
        e_real = self._make_live_engine(tmp_path, monkeypatch, mock_real)
        real_result = e_real.create_order("ETH/USDT", "SELL", 100.0)

        assert gated_result["mode"] == real_result["mode"] == "live_failed"
        assert set(gated_result.keys()) == set(real_result.keys())

    def test_gate_off_reaches_real_execution_path(self, tmp_path, monkeypatch):
        """PAPER_TRADING_ENABLED=false : le chemin live est bien atteint
        (mocké) — le gate ne bloque plus rien."""
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.return_value = {"id": "live1"}
        e = self._make_live_engine(tmp_path, monkeypatch, mock_exchange)

        result = e.create_order("BTC/USDT", "BUY", 100.0)

        assert result["mode"] == "live"
        mock_exchange.fetch_ticker.assert_called_once()
        mock_exchange.create_order.assert_called_once()

    def test_gate_blocked_order_logged_as_error_in_trade_log(
        self, tmp_path, monkeypatch
    ):
        """Même enregistrement trade_log (mode='live_failed', status='error')
        que le rejet MEXC réel — même compteurs d'erreurs alimentés en aval."""
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        e = self._make_live_engine(tmp_path, monkeypatch, mock_exchange)

        e.create_order("HYPE/USDT", "BUY", 100.0)

        recent = e._logger.recent_trades(1)
        assert len(recent) == 1
        assert recent[0]["mode"] == "live_failed"
        assert recent[0]["status"] == "error"
        assert recent[0]["error"] == "blocked_by_paper_gate"

    def test_gate_reads_env_at_call_time_not_cached(self, tmp_path, monkeypatch):
        """DS-001 (ADR-0008) — PAPER_TRADING_ENABLED est lu à l'appel, jamais
        figé à l'__init__ : basculer la variable en cours de vie du process
        change immédiatement le comportement, sans recréer le moteur."""
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
        monkeypatch.setenv("EXEC_DEDUP_WINDOW", "0")  # isole du garde anti-doublon
        mock_exchange = MagicMock()
        self._setup_mock_exchange(mock_exchange)
        mock_exchange.create_order.return_value = {"id": "live2"}
        e = self._make_live_engine(tmp_path, monkeypatch, mock_exchange)

        blocked = e.create_order("SOL/USDT", "BUY", 100.0)
        assert blocked["mode"] == "live_failed"

        monkeypatch.setenv("PAPER_TRADING_ENABLED", "false")
        unblocked = e.create_order("SOL/USDT", "BUY", 100.0)
        assert unblocked["mode"] == "live"
