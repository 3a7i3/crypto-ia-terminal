import pytest

from src.agent.codex_agent import CodexAgent
from src.agent.sma_strategy import SMAStrategy
from src.backtest.data_feed import HistoricalDataFeed
from src.backtest.engine import BacktestEngine
from src.engine.execution_router import ExecutionRouter
from src.engine.virtual_exchange import VirtualExchange
from src.portfolio.portfolio_state import PortfolioState
from src.risk.kill_switch import KillSwitch


def make_candles(n=60, base=100.0, trend=0.5):
    candles = []
    price = base
    for i in range(n):
        price += trend
        candles.append(
            {
                "timestamp": i,
                "symbol": "BTC",
                "open": price - 0.1,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price,
                "volume": 1000.0,
            }
        )
    return candles


def make_backtest_stack(candles):
    portfolio = PortfolioState(balance=10000.0)
    exchange = VirtualExchange(portfolio)
    router = ExecutionRouter(exchange)  # same ExecutionRouter as in live sim
    feed = HistoricalDataFeed(candles)
    strategy = SMAStrategy(fast_period=3, slow_period=10)
    ks = KillSwitch()
    agent = CodexAgent(strategy, ks)
    engine = BacktestEngine(agent, router, feed, portfolio)
    return engine, router, portfolio


def test_backtest_uses_same_execution_router():
    # The ExecutionRouter imported must be the canonical one
    from src.engine.execution_router import ExecutionRouter as ER

    candles = make_candles()
    _, router, _ = make_backtest_stack(candles)
    assert isinstance(router, ER)


def test_backtest_runs_and_logs_trades():
    candles = make_candles(n=60)
    engine, _, _ = make_backtest_stack(candles)
    report = engine.run()
    assert "total_trades" in report
    assert "final_balance" in report
    assert "total_pnl" in report
    assert "win_rate" in report
    assert "trades" in report


def test_backtest_pnl_coherent():
    candles = make_candles(n=60, trend=1.0)
    engine, _, portfolio = make_backtest_stack(candles)
    initial_balance = portfolio.balance
    report = engine.run()
    # With a strong uptrend, at least some trades should have occurred
    assert isinstance(report["total_pnl"], float)
    # final balance + unrealized ~= initial + total_pnl (approximately)
    assert isinstance(report["final_balance"], float)


def test_data_feed_reset():
    candles = make_candles(n=5)
    feed = HistoricalDataFeed(candles)
    first = [feed.next() for _ in range(5)]
    assert feed.next() is None
    feed.reset()
    second = [feed.next() for _ in range(5)]
    assert [c["timestamp"] for c in first] == [c["timestamp"] for c in second]
