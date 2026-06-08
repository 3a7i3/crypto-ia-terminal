from src.agent.codex_agent import CodexAgent
from src.agent.sma_strategy import SMAStrategy
from src.analytics.performance_breakdown import breakdown
from src.analytics.regime_detector import RegimeDetector
from src.backtest.data_feed import HistoricalDataFeed
from src.backtest.engine import BacktestEngine
from src.engine.execution_router import ExecutionRouter
from src.engine.virtual_exchange import VirtualExchange
from src.portfolio.portfolio_state import PortfolioState
from src.risk.kill_switch import KillSwitch
from src.runtime.run_context import RunContext


def _candles_trend(n=60, slope=2.0):
    price = 100.0
    candles = []
    for i in range(n):
        price += slope
        candles.append(
            {"close": price, "high": price + 1, "low": price - 1, "symbol": "BTC"}
        )
    return candles


def _candles_range(n=60, noise=0.5):
    import math

    candles = []
    price = 100.0
    for i in range(n):
        price = 100.0 + math.sin(i * 0.4) * noise
        candles.append(
            {"close": price, "high": price + 0.2, "low": price - 0.2, "symbol": "BTC"}
        )
    return candles


def _candles_volatile(n=60):
    import math

    candles = []
    price = 100.0
    for i in range(n):
        spike = 5.0 * math.sin(i * 1.5)
        price = max(1.0, 100.0 + spike)
        candles.append(
            {"close": price, "high": price + 4, "low": price - 4, "symbol": "BTC"}
        )
    return candles


detector = RegimeDetector()


# -- RegimeDetector --


def test_trend_detected():
    assert detector.classify(_candles_trend(slope=3.0)) == "trending"


def test_range_detected():
    assert detector.classify(_candles_range(noise=0.1)) == "sideways"


def test_volatile_detected():
    assert detector.classify(_candles_volatile()) == "volatile"


def test_too_few_candles_returns_range():
    assert detector.classify([{"close": 100, "high": 101, "low": 99}]) == "sideways"


def test_metrics_returns_all_keys():
    m = detector.metrics(_candles_trend())
    assert "regime" in m
    assert "atr_pct" in m
    assert "slope" in m
    assert "n" in m


def test_slope_positive_in_uptrend():
    m = detector.metrics(_candles_trend(slope=2.0))
    assert m["slope"] > 0


# -- BacktestEngine includes regime in report --


def _make_report(candles):
    portfolio = PortfolioState(balance=10000.0)
    exchange = VirtualExchange(portfolio)
    router = ExecutionRouter(exchange)
    feed = HistoricalDataFeed(candles)
    agent = CodexAgent(SMAStrategy(3, 10), KillSwitch())
    ctx = RunContext(strategy_id="TEST")
    return BacktestEngine(agent, router, feed, portfolio, ctx).run()


def test_report_has_regime():
    report = _make_report(_candles_trend())
    assert "regime" in report
    assert report["regime"] in ("trending", "sideways", "volatile")


def test_trend_candles_produce_trend_regime():
    report = _make_report(_candles_trend(n=80, slope=3.0))
    assert report["regime"] == "trending"


def test_report_has_regime_metrics():
    report = _make_report(_candles_trend())
    assert "regime_atr" in report
    assert "regime_slope" in report


# -- Performance breakdown --


def test_breakdown_empty():
    bd = breakdown([])
    assert bd["all"]["n_runs"] == 0


def test_breakdown_aggregates_by_regime():
    reports = [
        {
            "regime": "trending",
            "total_trades": 5,
            "total_pnl": 100.0,
            "win_rate": 0.6,
            "max_drawdown": 0.05,
        },
        {
            "regime": "trending",
            "total_trades": 4,
            "total_pnl": -20.0,
            "win_rate": 0.4,
            "max_drawdown": 0.08,
        },
        {
            "regime": "sideways",
            "total_trades": 3,
            "total_pnl": 10.0,
            "win_rate": 0.5,
            "max_drawdown": 0.02,
        },
        {
            "regime": "volatile",
            "total_trades": 8,
            "total_pnl": -50.0,
            "win_rate": 0.3,
            "max_drawdown": 0.15,
        },
    ]
    bd = breakdown(reports)
    assert bd["trending"]["n_runs"] == 2
    assert bd["sideways"]["n_runs"] == 1
    assert bd["volatile"]["n_runs"] == 1
    assert bd["all"]["n_runs"] == 4


def test_breakdown_profit_factor():
    reports = [
        {
            "regime": "trending",
            "total_trades": 5,
            "total_pnl": 200.0,
            "win_rate": 0.6,
            "max_drawdown": 0.05,
        },
        {
            "regime": "trending",
            "total_trades": 5,
            "total_pnl": -100.0,
            "win_rate": 0.4,
            "max_drawdown": 0.08,
        },
    ]
    bd = breakdown(reports)
    assert bd["trending"]["profit_factor"] == 2.0


def test_breakdown_no_losses_infinite_pf():
    reports = [
        {
            "regime": "trending",
            "total_trades": 3,
            "total_pnl": 50.0,
            "win_rate": 1.0,
            "max_drawdown": 0.0,
        }
    ]
    bd = breakdown(reports)
    assert bd["trending"]["profit_factor"] == float("inf")
