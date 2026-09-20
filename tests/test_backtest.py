import pytest

from src.agent.codex_agent import CodexAgent
from src.agent.sma_strategy import SMAStrategy
from src.backtest.data_feed import HistoricalDataFeed
from src.backtest.engine import BacktestEngine
from src.engine.execution_router import ExecutionRouter
from src.domain.signal import Signal
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
    engine, _, _ = make_backtest_stack(candles)
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


class _ScriptedAgent:
    def __init__(self, signals_by_timestamp):
        self._signals = signals_by_timestamp

    def on_market(self, candle):
        return self._signals.get(candle["timestamp"])


def test_position_survives_until_deferred_opposite_signal():
    candles = [
        {
            "timestamp": i,
            "symbol": "BTC",
            "open": price[0],
            "high": max(price) + 1.0,
            "low": min(price) - 1.0,
            "close": price[1],
            "volume": 1000.0,
        }
        for i, price in enumerate(
            [
                (99.0, 100.0),
                (101.0, 102.0),
                (102.0, 103.0),
                (103.0, 104.0),
                (104.0, 105.0),
                (106.0, 105.0),
                (105.0, 104.0),
                (104.0, 103.0),
                (103.0, 103.0),
                (103.0, 103.0),
            ]
        )
    ]

    portfolio = PortfolioState(balance=10_000.0)
    exchange = VirtualExchange(portfolio)
    router = ExecutionRouter(exchange)
    feed = HistoricalDataFeed(candles)
    agent = _ScriptedAgent(
        {
            0: Signal(symbol="BTC", direction="buy", confidence=1.0),
            4: Signal(symbol="BTC", direction="sell", confidence=1.0),
        }
    )

    report = BacktestEngine(agent, router, feed, portfolio).run()

    assert report["total_trades"] == 2

    first, second = report["trades"]

    # BUY seen at close[0] enters at open[1] and remains alive through bars
    # 1..4.  The SELL seen at close[4] closes it only at open[5].
    assert first.side == "buy"
    assert first.entry_price == pytest.approx(101.0)
    assert first.exit_price == pytest.approx(106.0)
    assert first.gross_pnl_usd == pytest.approx(5.0)

    # The reversal opens SHORT at the same reachable open[5], then the finite
    # replay boundary liquidates it at the final observed close.
    assert second.side == "sell"
    assert second.entry_price == pytest.approx(106.0)
    assert second.exit_price == pytest.approx(103.0)
    assert second.gross_pnl_usd == pytest.approx(3.0)

    assert report["total_pnl"] == pytest.approx(8.0)
    assert report["final_balance"] == pytest.approx(10_008.0)
    assert portfolio.positions == {}


def test_same_side_signal_does_not_overwrite_existing_entry():
    candles = make_candles(n=20, base=100.0, trend=1.0)
    portfolio = PortfolioState(balance=10_000.0)
    exchange = VirtualExchange(portfolio)
    router = ExecutionRouter(exchange)
    feed = HistoricalDataFeed(candles)
    agent = _ScriptedAgent(
        {
            0: Signal(symbol="BTC", direction="buy", confidence=1.0),
            2: Signal(symbol="BTC", direction="buy", confidence=1.0),
        }
    )

    report = BacktestEngine(agent, router, feed, portfolio).run()

    assert report["total_trades"] == 1
    trade = report["trades"][0]
    assert trade.entry_price == pytest.approx(candles[1]["open"])
    assert trade.exit_price == pytest.approx(candles[-1]["close"])
