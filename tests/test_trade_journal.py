from src.domain.order import Order
from src.domain.trade_event import TradeEvent
from src.engine.execution_router import ExecutionRouter
from src.engine.virtual_exchange import VirtualExchange
from src.events.event_bus import SimEventBus
from src.journal.trade_logger import TradeLogger
from src.portfolio.portfolio_state import PortfolioState


def make_observed_stack(balance=10000.0):
    bus = SimEventBus()
    logger = TradeLogger()
    bus.subscribe("TRADE_OPENED", logger.on_trade_opened)
    bus.subscribe("TRADE_CLOSED", logger.on_trade_closed)
    portfolio = PortfolioState(balance=balance)
    exchange = VirtualExchange(portfolio, event_bus=bus)
    router = ExecutionRouter(exchange)
    return router, portfolio, logger, bus


def test_trade_opened_logged():
    router, portfolio, logger, _ = make_observed_stack()
    order = Order(symbol="BTC", side="buy", size=1.0)
    router.execute(order, price=100.0)
    assert len(logger.logs) == 1
    assert logger.logs[0]["type"] == "OPENED"
    assert logger.logs[0]["entry"] == 100.0


def test_trade_closed_logged_with_pnl():
    router, portfolio, logger, _ = make_observed_stack()
    order = Order(symbol="BTC", side="buy", size=1.0)
    router.execute(order, price=100.0)
    router.sim_engine.close_position("BTC", 120.0)
    closed = logger.closed_trades()
    assert len(closed) == 1
    assert isinstance(closed[0], TradeEvent)
    assert closed[0].net_pnl_usd == 20.0
    assert closed[0].exit_price == 120.0


def test_total_pnl_aggregated():
    router, portfolio, logger, _ = make_observed_stack()
    for price in [100.0, 200.0]:
        sym = f"SYM{int(price)}"
        router.execute(Order(symbol=sym, side="buy", size=1.0), price=price)
        router.sim_engine.close_position(sym, price + 10.0)
    assert logger.total_pnl() == 20.0


def test_win_rate_computed():
    router, portfolio, logger, _ = make_observed_stack()
    router.execute(Order(symbol="BTC", side="buy", size=1.0), 100.0)
    router.sim_engine.close_position("BTC", 110.0)  # win
    router.execute(Order(symbol="ETH", side="buy", size=1.0), 200.0)
    router.sim_engine.close_position("ETH", 190.0)  # loss
    assert logger.win_rate() == 0.5


def test_replay_returns_full_ordered_log():
    router, portfolio, logger, _ = make_observed_stack()
    router.execute(Order(symbol="BTC", side="buy", size=1.0), 100.0)
    router.sim_engine.close_position("BTC", 110.0)
    replay = logger.replay()
    assert len(replay) == 2
    assert replay[0]["type"] == "OPENED"  # open = dict opérationnel
    assert isinstance(replay[1], TradeEvent)  # close = TradeEvent SSoT


def test_no_bus_does_not_crash():
    portfolio = PortfolioState(balance=10000.0)
    exchange = VirtualExchange(portfolio)  # no event_bus
    router = ExecutionRouter(exchange)
    router.execute(Order(symbol="BTC", side="buy", size=1.0), 100.0)
    router.sim_engine.close_position("BTC", 110.0)


def test_portfolio_snapshot():
    portfolio = PortfolioState(balance=5000.0)
    exchange = VirtualExchange(portfolio)
    router = ExecutionRouter(exchange)
    router.execute(Order(symbol="BTC", side="buy", size=2.0), 100.0)
    snap = portfolio.snapshot()
    assert snap["balance"] == 5000.0
    assert "BTC" in snap["positions"]
    assert snap["positions"]["BTC"]["size"] == 2.0
    assert snap["positions"]["BTC"]["entry_price"] == 100.0


def test_short_trade_logged_correctly():
    router, portfolio, logger, _ = make_observed_stack()
    router.execute(Order(symbol="ETH", side="sell", size=1.0), 300.0)
    router.sim_engine.close_position("ETH", 270.0)
    closed = logger.closed_trades()
    assert isinstance(closed[0], TradeEvent)
    assert closed[0].net_pnl_usd == 30.0


def test_logger_reset():
    router, portfolio, logger, _ = make_observed_stack()
    router.execute(Order(symbol="BTC", side="buy", size=1.0), 100.0)
    logger.reset()
    assert logger.logs == []
    assert logger.total_pnl() == 0.0
