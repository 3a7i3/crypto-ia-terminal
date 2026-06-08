import pytest

from src.agent.codex_agent import CodexAgent
from src.agent.rsi_strategy import RSIStrategy
from src.backtest.data_feed import HistoricalDataFeed
from src.backtest.engine import BacktestEngine
from src.backtest.market_generator import range_bound, trend_up
from src.domain.order import Order
from src.engine.execution_router import ExecutionRouter
from src.engine.virtual_exchange import VirtualExchange
from src.execution.enl import ENLConfig, NoisyExchange
from src.portfolio.portfolio_state import PortfolioState
from src.risk.kill_switch import KillSwitch
from src.runtime.run_context import RunContext


def _make_noisy(config=None, balance=10_000.0):
    portfolio = PortfolioState(balance=balance)
    exchange = VirtualExchange(portfolio)
    noisy = NoisyExchange(exchange, config or ENLConfig.realistic())
    return noisy, portfolio


# -- ENLConfig presets --


def test_clean_preset_zero_friction():
    cfg = ENLConfig.clean()
    assert cfg.spread_bps == 0.0
    assert cfg.slippage_sigma == 0.0
    assert cfg.fill_rate == 1.0


def test_heavy_preset_has_friction():
    cfg = ENLConfig.heavy()
    assert cfg.spread_bps > 10.0
    assert cfg.slippage_sigma > 0.002


# -- Price adjustment --


def test_buy_price_above_market():
    noisy, _ = _make_noisy(ENLConfig.realistic())
    adj = noisy._fill_price("buy", 100.0)
    assert adj > 100.0


def test_sell_price_below_market():
    noisy, _ = _make_noisy(ENLConfig.realistic())
    adj = noisy._fill_price("sell", 100.0)
    assert adj < 100.0


def test_clean_config_no_price_change():
    noisy, _ = _make_noisy(ENLConfig.clean())
    assert noisy._fill_price("buy", 100.0) == 100.0
    assert noisy._fill_price("sell", 100.0) == 100.0


def test_slippage_proportional_to_price():
    noisy_low = NoisyExchange(
        VirtualExchange(PortfolioState(10000)), ENLConfig(slippage_sigma=0.01, seed=1)
    )
    noisy_high = NoisyExchange(
        VirtualExchange(PortfolioState(10000)), ENLConfig(slippage_sigma=0.01, seed=1)
    )
    low_cost = abs(noisy_low._fill_price("buy", 100.0) - 100.0)
    high_cost = abs(noisy_high._fill_price("buy", 1000.0) - 1000.0)
    assert high_cost > low_cost


# -- Fill rate --


def test_partial_fill_reduces_size():
    portfolio = PortfolioState(balance=10_000.0)
    exchange = VirtualExchange(portfolio)
    noisy = NoisyExchange(
        exchange, ENLConfig(fill_rate=0.5, spread_bps=0, slippage_sigma=0)
    )
    order = Order(symbol="BTC", side="buy", size=1.0)
    pos = noisy.place_order(order, 100.0)
    assert pos is not None
    assert abs(pos.size - 0.5) < 1e-6


def test_zero_fill_rate_rejects():
    portfolio = PortfolioState(balance=10_000.0)
    exchange = VirtualExchange(portfolio)
    noisy = NoisyExchange(exchange, ENLConfig(fill_rate=0.0))
    order = Order(symbol="BTC", side="buy", size=1.0)
    pos = noisy.place_order(order, 100.0)
    assert pos is None
    assert noisy.rejected_fills == 1


# -- Close position with friction --


def test_close_long_sells_below_price():
    noisy, portfolio = _make_noisy(
        ENLConfig(spread_bps=10, slippage_sigma=0.001, seed=42)
    )
    order = Order(symbol="ETH", side="buy", size=1.0)
    noisy.place_order(order, 200.0)
    trade = noisy.close_position("ETH", 210.0)
    # Long close = sell, should execute below 210
    assert trade is not None
    assert trade.exit_price < 210.0


# -- Friction report --


def test_friction_report_accumulates():
    noisy, _ = _make_noisy(ENLConfig.realistic())
    for _ in range(5):
        noisy._fill_price("buy", 100.0)
    report = noisy.friction_report()
    assert report["total_spread_cost"] > 0
    assert report["total_slippage_cost"] >= 0


# -- Reproducibility by seed --


def test_reproducible_with_seed():
    def _prices(seed):
        noisy = NoisyExchange(
            VirtualExchange(PortfolioState(10000)),
            ENLConfig(spread_bps=10, slippage_sigma=0.002, seed=seed),
        )
        return [noisy._fill_price("buy", 100.0) for _ in range(10)]

    assert _prices(42) == _prices(42)
    assert _prices(1) != _prices(2)


# -- Integration: BacktestEngine with ENL --


def _run_with_config(candles, config) -> dict:
    portfolio = PortfolioState(balance=10_000.0)
    exchange = VirtualExchange(portfolio)
    noisy = NoisyExchange(exchange, config)
    router = ExecutionRouter(noisy)
    feed = HistoricalDataFeed(candles)
    agent = CodexAgent(RSIStrategy(14, 30, 70), KillSwitch())
    ctx = RunContext(strategy_id="RSI_ENL_TEST")
    return BacktestEngine(agent, router, feed, portfolio, ctx).run()


def test_enl_reduces_pnl_vs_clean():
    candles = range_bound(n=120, seed=0)
    clean = _run_with_config(candles, ENLConfig.clean())
    noisy = _run_with_config(candles, ENLConfig.heavy())
    # Heavy friction should produce worse PnL than no friction
    assert noisy["total_pnl"] <= clean["total_pnl"]


def test_enl_integration_does_not_crash():
    candles = trend_up(n=120, seed=0)
    report = _run_with_config(candles, ENLConfig.realistic())
    assert "total_pnl" in report
    assert "total_trades" in report
