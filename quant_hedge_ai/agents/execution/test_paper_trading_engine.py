"""Tests PaperTradingEngine — simulation complète sans persistance disque."""

from __future__ import annotations
import pytest
from quant_hedge_ai.agents.execution.paper_trading_engine import PaperTradingEngine


@pytest.fixture
def eng():
    return PaperTradingEngine(initial_balance=10_000.0, persist=False)


class TestInit:
    def test_initial_balance(self, eng):
        assert eng.balance == 10_000.0

    def test_no_positions_initially(self, eng):
        assert eng.positions == {}

    def test_no_trades_initially(self, eng):
        assert eng.trade_history == []

    def test_size_factor_default_one(self, eng):
        assert eng._size_factor == 1.0


class TestSetSizeFactor:
    def test_clamps_below_zero(self, eng):
        eng.set_size_factor(-1.0)
        assert eng._size_factor == 0.0

    def test_clamps_above_one(self, eng):
        eng.set_size_factor(5.0)
        assert eng._size_factor == 1.0

    def test_mid_value(self, eng):
        eng.set_size_factor(0.3)
        assert eng._size_factor == pytest.approx(0.3)


class TestExecuteBuy:
    def test_buy_reduces_balance(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 1.0}, mark_price=1000.0)
        assert eng.balance == pytest.approx(9_000.0)

    def test_buy_adds_position(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 2.0}, mark_price=500.0)
        assert eng.positions.get("BTCUSDT", 0.0) == pytest.approx(2.0)

    def test_buy_returns_balance_positions(self, eng):
        result = eng.execute({"symbol": "ETHUSDT", "action": "BUY", "size": 1.0}, mark_price=200.0)
        assert "balance" in result
        assert "positions" in result
        assert "last_trade" in result

    def test_buy_insufficient_balance_no_position(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 100.0}, mark_price=200.0)
        # notional=20000 > balance=10000 → trade not executed
        assert eng.positions.get("BTCUSDT", 0.0) == 0.0

    def test_buy_records_trade(self, eng):
        eng.execute({"symbol": "SOLUSDT", "action": "BUY", "size": 5.0}, mark_price=50.0)
        assert len(eng.trade_history) == 1
        assert eng.trade_history[0]["action"] == "BUY"


class TestExecuteSell:
    def test_sell_increases_balance(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 1.0}, mark_price=1000.0)
        eng.execute({"symbol": "BTCUSDT", "action": "SELL", "size": 1.0}, mark_price=1000.0)
        assert eng.balance > 9_000.0  # got proceeds back

    def test_sell_reduces_position(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 2.0}, mark_price=500.0)
        eng.execute({"symbol": "BTCUSDT", "action": "SELL", "size": 1.0}, mark_price=500.0)
        assert eng.positions.get("BTCUSDT", 0.0) == pytest.approx(1.0)

    def test_sell_more_than_held_caps_at_position(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 1.0}, mark_price=500.0)
        eng.execute({"symbol": "BTCUSDT", "action": "SELL", "size": 99.0}, mark_price=500.0)
        assert eng.positions.get("BTCUSDT", 0.0) == pytest.approx(0.0)

    def test_sell_no_position_no_crash(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "SELL", "size": 1.0}, mark_price=500.0)


class TestMetrics:
    def test_portfolio_value_no_positions(self, eng):
        assert eng.portfolio_value({}) == pytest.approx(10_000.0)

    def test_portfolio_value_with_position(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 1.0}, mark_price=1000.0)
        val = eng.portfolio_value({"BTCUSDT": 1_200.0})
        assert val == pytest.approx(9_000.0 + 1_200.0)

    def test_total_pnl_zero_initially(self, eng):
        assert eng.total_pnl() == 0.0

    def test_win_rate_zero_no_trades(self, eng):
        assert eng.win_rate() == 0.0

    def test_snapshot_keys(self, eng):
        snap = eng.snapshot()
        for key in ("balance", "portfolio_value", "pnl_total", "pnl_pct",
                    "positions", "n_trades", "win_rate"):
            assert key in snap

    def test_equity_curve_updated_after_trade(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 1.0}, mark_price=1000.0)
        assert len(eng.equity_curve) == 1


class TestReset:
    def test_reset_restores_balance(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 1.0}, mark_price=500.0)
        eng.reset()
        assert eng.balance == pytest.approx(10_000.0)

    def test_reset_clears_positions(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 1.0}, mark_price=500.0)
        eng.reset()
        assert eng.positions == {}

    def test_reset_clears_history(self, eng):
        eng.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 1.0}, mark_price=500.0)
        eng.reset()
        assert eng.trade_history == []


class TestPersistence:
    def test_save_and_load(self, tmp_path, monkeypatch):
        import quant_hedge_ai.agents.execution.paper_trading_engine as mod
        state_path = tmp_path / "state.json"
        monkeypatch.setattr(mod, "_STATE_FILE", state_path)

        eng1 = PaperTradingEngine(initial_balance=5_000.0, persist=True)
        eng1.execute({"symbol": "BTCUSDT", "action": "BUY", "size": 1.0}, mark_price=500.0)
        eng1._save()

        eng2 = PaperTradingEngine(initial_balance=5_000.0, persist=True)
        assert eng2.balance == pytest.approx(4_500.0)
        assert len(eng2.trade_history) == 1

    def test_load_missing_file_no_crash(self, tmp_path, monkeypatch):
        import quant_hedge_ai.agents.execution.paper_trading_engine as mod
        monkeypatch.setattr(mod, "_STATE_FILE", tmp_path / "missing.json")
        eng = PaperTradingEngine(initial_balance=1_000.0, persist=True)
        assert eng.balance == pytest.approx(1_000.0)

    def test_load_corrupt_json_no_crash(self, tmp_path, monkeypatch):
        import quant_hedge_ai.agents.execution.paper_trading_engine as mod
        state_path = tmp_path / "state.json"
        state_path.write_text("not valid json", encoding="utf-8")
        monkeypatch.setattr(mod, "_STATE_FILE", state_path)
        eng = PaperTradingEngine(initial_balance=2_000.0, persist=True)
        assert eng.balance == pytest.approx(2_000.0)
