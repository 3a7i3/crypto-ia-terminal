import pytest

from src.domain.order import Order
from src.domain.position import Position
from src.domain.signal import Signal
from src.engine.execution_router import ExecutionRouter
from src.engine.virtual_exchange import VirtualExchange
from src.portfolio.portfolio_state import PortfolioState
from src.runtime.simulator import Simulator


def make_stack(balance=10000.0):
    portfolio = PortfolioState(balance=balance)
    exchange = VirtualExchange(portfolio)
    router = ExecutionRouter(exchange)
    sim = Simulator(router, portfolio)
    return sim, portfolio


def test_full_chain_long():
    sim, portfolio = make_stack()
    signal = Signal(symbol="BTC", direction="buy", confidence=0.8)
    position = sim.step(signal, price=100.0)
    assert position is not None
    assert position.side == "long"
    assert position.entry_price == 100.0
    equity = portfolio.mark_to_market({"BTC": 110.0})
    assert equity > 10000.0


def test_weak_signal_ignored():
    sim, portfolio = make_stack()
    signal = Signal(symbol="BTC", direction="buy", confidence=0.5)
    result = sim.step(signal, price=100.0)
    assert result is None
    assert "BTC" not in portfolio.positions


def test_short_pnl():
    sim, portfolio = make_stack()
    signal = Signal(symbol="ETH", direction="sell", confidence=0.9)
    position = sim.step(signal, price=200.0)
    assert position is not None
    assert position.side == "short"
    equity = portfolio.mark_to_market({"ETH": 180.0})
    assert equity > 10000.0
