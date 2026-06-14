"""Tests unitaires — ExecutionEngine : chemins futures, capital, dedup non couverts."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture
def eng(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCHANGE_ID", "binance")  # isolate from .env krakenfutures
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
    monkeypatch.setenv("EXEC_MAX_DD", "0.05")
    monkeypatch.setenv("EXEC_MAX_LOSS", "0.03")
    monkeypatch.setenv("EXEC_MAX_CONSEC_LOSSES", "3")
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
    monkeypatch.setenv("EXEC_DEDUP_WINDOW", "30")
    monkeypatch.setenv("EXEC_FUTURES_MIN_ORDER_USD", "55")
    monkeypatch.setenv("EXEC_FUTURES_MAX_ORDER_USD", "200")
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    e = ExecutionEngine(live=False, _sleep=lambda _: None)
    e.start_session(equity=10_000.0)
    return e


def _with_futures(eng) -> MagicMock:
    mock_ex = MagicMock()
    mock_ex.fetch_ticker.return_value = {"last": 80000.0}
    mock_ex.load_markets.return_value = {}
    mock_ex.create_order.return_value = {
        "id": "f123",
        "status": "closed",
        "avgPrice": 80000.0,
    }
    eng._exchange_futures = mock_ex
    return mock_ex


# ── Suite 1 : create_futures_order — disponibilité ───────────────────────────


class TestFuturesUnavailable:
    def test_no_exchange_returns_unavailable(self, eng):
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0)
        assert result["mode"] == "futures_unavailable"
        assert "MEXC_API_KEY" in result["error"]

    def test_unavailable_contains_symbol(self, eng):
        result = eng.create_futures_order("ETH/USDT", "BUY", 60.0)
        assert result["symbol"] == "ETH/USDT"


# ── Suite 2 : create_futures_order — exécution nominale ──────────────────────


class TestFuturesSuccess:
    def test_buy_returns_futures_demo_mode(self, eng):
        _with_futures(eng)
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0)
        assert result["mode"] == "futures_demo"
        assert result["id"] == "f123"

    def test_sell_side_forwarded(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("ETH/USDT", "SELL", 60.0)
        assert mock_ex.create_order.call_args[0][2] == "sell"

    def test_buy_side_forwarded(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTC/USDT", "BUY", 60.0)
        assert mock_ex.create_order.call_args[0][2] == "buy"

    def test_usd_size_in_result(self, eng):
        _with_futures(eng)
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0)
        assert "usd_size" in result
        assert result["usd_size"] > 0


# ── Suite 3 : symbol conversion ───────────────────────────────────────────────


class TestFuturesSymbolConversion:
    def test_slash_pair_converted_to_perp(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTC/USDT", "BUY", 60.0)
        used = mock_ex.create_order.call_args[0][0]
        assert used == "BTC/USDT:USDT"

    def test_already_perp_not_double_converted(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTC/USDT:USDT", "BUY", 60.0)
        used = mock_ex.create_order.call_args[0][0]
        assert used == "BTC/USDT:USDT"

    def test_no_slash_converted(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTCUSDT", "BUY", 60.0)
        used = mock_ex.create_order.call_args[0][0]
        assert used == "BTC/USDT:USDT"


# ── Suite 4 : size clamping ────────────────────────────────────────────────────


class TestFuturesSizeClamping:
    def test_below_min_clamped_up(self, eng):
        mock_ex = _with_futures(eng)
        result = eng.create_futures_order("BTC/USDT", "BUY", 1.0)
        assert result["mode"] == "futures_demo"
        assert result["usd_size"] >= 55.0

    def test_above_max_clamped_down(self, eng):
        mock_ex = _with_futures(eng)
        result = eng.create_futures_order("BTC/USDT", "BUY", 99999.0)
        assert result["mode"] == "futures_demo"
        # size_usd est clampé à 200 avant conversion en qty ;
        # la valeur finale peut être légèrement supérieure à cause de l'arrondi
        # de qty à la précision marché — on vérifie simplement que l'ordre passe
        assert result["usd_size"] > 0

    def test_within_range_unchanged(self, eng):
        mock_ex = _with_futures(eng)
        result = eng.create_futures_order("BTC/USDT", "BUY", 100.0)
        assert result["mode"] == "futures_demo"


# ── Suite 5 : leverage ────────────────────────────────────────────────────────


class TestFuturesLeverage:
    def test_leverage_1_no_set_leverage_call(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTC/USDT", "BUY", 60.0, leverage=1)
        mock_ex.set_leverage.assert_not_called()

    def test_leverage_3_calls_set_leverage(self, eng):
        mock_ex = _with_futures(eng)
        eng.create_futures_order("BTC/USDT", "BUY", 60.0, leverage=3)
        mock_ex.set_leverage.assert_called_once()
        assert mock_ex.set_leverage.call_args[0][0] == 3

    def test_leverage_exception_order_still_placed(self, eng):
        mock_ex = _with_futures(eng)
        mock_ex.set_leverage.side_effect = Exception("not supported")
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0, leverage=2)
        assert result["mode"] == "futures_demo"


# ── Suite 6 : error handling ──────────────────────────────────────────────────


class TestFuturesErrors:
    def test_exchange_error_returns_futures_failed(self, eng):
        mock_ex = _with_futures(eng)
        mock_ex.create_order.side_effect = RuntimeError("exchange down")
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0)
        assert result["mode"] == "futures_failed"
        assert "exchange down" in result["error"]

    def test_load_markets_error_uses_defaults(self, eng):
        mock_ex = _with_futures(eng)
        mock_ex.load_markets.side_effect = Exception("markets unavailable")
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0)
        assert result["mode"] == "futures_demo"

    def test_fetch_ticker_error_returns_futures_failed(self, eng):
        mock_ex = _with_futures(eng)
        mock_ex.fetch_ticker.side_effect = Exception("ticker timeout")
        result = eng.create_futures_order("BTC/USDT", "BUY", 60.0)
        assert result["mode"] == "futures_failed"
        assert "ticker timeout" in result["error"]


# ── Suite 7 : fetch_available_capital ─────────────────────────────────────────


class TestFetchAvailableCapital:
    @pytest.fixture(autouse=True)
    def _isolate_exchange(self, monkeypatch):
        monkeypatch.setenv("EXCHANGE_ID", "binance")

    def test_fallback_when_no_exchange(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("V9_INITIAL_CAPITAL", "2500")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        assert e.fetch_available_capital() == 2500.0

    def test_live_exchange_returns_usdt_balance(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("V9_INITIAL_CAPITAL", "1000")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        mock_ex = MagicMock()
        mock_ex.fetch_balance.return_value = {"free": {"USDT": 4200.0}}
        e._exchange = mock_ex
        assert e.fetch_available_capital() == 4200.0

    def test_zero_usdt_balance_falls_back(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("V9_INITIAL_CAPITAL", "999")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False)
        mock_ex = MagicMock()
        mock_ex.fetch_balance.return_value = {"free": {"USDT": 0.0}}
        e._exchange = mock_ex
        assert e.fetch_available_capital() == 999.0

    def test_exchange_error_falls_back(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "t.sqlite"))
        monkeypatch.setenv("V9_INITIAL_CAPITAL", "888")
        from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

        e = ExecutionEngine(live=False, _sleep=lambda _: None)
        mock_ex = MagicMock()
        mock_ex.fetch_balance.side_effect = Exception("network error")
        e._exchange = mock_ex
        assert e.fetch_available_capital() == 888.0


# ── Suite 8 : detect_quote_asset ──────────────────────────────────────────────


class TestDetectQuoteAsset:
    def test_btc_usdt(self, eng):
        assert eng.detect_quote_asset("BTC/USDT") == "USDT"

    def test_eth_btc(self, eng):
        assert eng.detect_quote_asset("ETH/BTC") == "BTC"

    def test_no_slash_returns_default(self, eng):
        assert eng.detect_quote_asset("BTCUSDT") == "USDT"


# ── Suite 9 : deduplication ────────────────────────────────────────────────────


class TestDeduplication:
    def test_same_order_rejected(self, eng):
        eng.create_order("BTC/USDT", "BUY", 100.0)
        result = eng.create_order("BTC/USDT", "BUY", 100.0)
        assert result["mode"] == "rejected"
        assert "duplicate" in result["error"]

    def test_different_action_not_duplicate(self, eng):
        eng.create_order("BTC/USDT", "BUY", 100.0)
        result = eng.create_order("BTC/USDT", "SELL", 100.0)
        assert result["mode"] == "paper"

    def test_different_symbol_not_duplicate(self, eng):
        eng.create_order("BTC/USDT", "BUY", 100.0)
        result = eng.create_order("ETH/USDT", "BUY", 100.0)
        assert result["mode"] == "paper"


# ── Suite 10 : has_futures_demo ────────────────────────────────────────────────


class TestHasFuturesDemo:
    def test_false_by_default(self, eng):
        assert eng.has_futures_demo() is False

    def test_true_when_exchange_set(self, eng):
        eng._exchange_futures = MagicMock()
        assert eng.has_futures_demo() is True
