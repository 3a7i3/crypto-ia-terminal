from src.agent.codex_agent import CodexAgent
from src.agent.sma_strategy import SMAStrategy
from src.backtest.data_feed import HistoricalDataFeed
from src.backtest.engine import BacktestEngine
from src.domain.order import Order
from src.engine.execution_router import ExecutionRouter
from src.engine.virtual_exchange import VirtualExchange
from src.events.event_bus import EventBus
from src.journal.trade_logger import TradeLogger
from src.portfolio.portfolio_state import PortfolioState
from src.risk.kill_switch import KillSwitch
from src.runtime.run_context import RunContext


def make_observed_stack(balance=10000.0):
    bus = EventBus()
    logger = TradeLogger()
    bus.subscribe("TRADE_OPENED", logger.on_trade_opened)
    bus.subscribe("TRADE_CLOSED", logger.on_trade_closed)
    portfolio = PortfolioState(balance=balance)
    exchange = VirtualExchange(portfolio, event_bus=bus)
    router = ExecutionRouter(exchange)
    return router, portfolio, logger


def make_candles(n=60, trend=0.5):
    price = 100.0
    candles = []
    for i in range(n):
        price += trend
        candles.append(
            {
                "timestamp": i,
                "symbol": "BTC",
                "close": price,
                "volume": 1000.0,
                "open": price - 0.1,
                "high": price + 0.2,
                "low": price - 0.2,
            }
        )
    return candles


# -- RunContext unit tests --


def test_run_context_auto_run_id():
    ctx = RunContext(strategy_id="SMA_5_20")
    assert len(ctx.run_id) == 8
    assert ctx.strategy_id == "SMA_5_20"


def test_two_contexts_have_different_run_ids():
    a = RunContext(strategy_id="S1")
    b = RunContext(strategy_id="S1")
    assert a.run_id != b.run_id


def test_run_context_to_dict():
    ctx = RunContext(strategy_id="RSI", market_state={"close": 100.0})
    d = ctx.to_dict()
    assert d["strategy_id"] == "RSI"
    assert d["market_state"] == {"close": 100.0}
    assert "run_id" in d
    assert "timestamp" in d


# -- Context propagation through exchange → logger --


def test_order_metadata_propagated_to_event():
    router, _, logger = make_observed_stack()
    ctx = RunContext(strategy_id="MACD")
    order = Order(
        symbol="BTC",
        side="buy",
        size=1.0,
        metadata={
            "run_id": ctx.run_id,
            "strategy_id": ctx.strategy_id,
            "confidence": 0.82,
            "market_state": {"close": 100.0},
        },
    )
    router.execute(order, price=100.0)
    entry = logger.logs[0]
    assert entry["run_id"] == ctx.run_id
    assert entry["strategy_id"] == "MACD"
    assert entry["confidence"] == 0.82
    assert entry["market_state"] == {"close": 100.0}


def test_closed_trade_carries_run_id():
    router, _, logger = make_observed_stack()
    ctx = RunContext(strategy_id="SMA")
    order = Order(
        symbol="BTC",
        side="buy",
        size=1.0,
        metadata={"run_id": ctx.run_id, "strategy_id": ctx.strategy_id},
    )
    router.execute(order, 100.0)
    router.sim_engine.close_position(
        "BTC", 110.0, metadata={"run_id": ctx.run_id, "strategy_id": ctx.strategy_id}
    )
    closed = logger.closed_trades()
    assert closed[0].run_id == ctx.run_id  # TradeEvent attribute (B2)


# -- by_run and by_strategy filters --


def test_by_run_filters_correctly():
    router, _, logger = make_observed_stack()
    ctx_a = RunContext(strategy_id="A")
    ctx_b = RunContext(strategy_id="B")
    for ctx in [ctx_a, ctx_b]:
        order = Order(
            symbol="BTC",
            side="buy",
            size=1.0,
            metadata={"run_id": ctx.run_id, "strategy_id": ctx.strategy_id},
        )
        router.execute(order, 100.0)
        router.sim_engine.close_position(
            "BTC",
            110.0,
            metadata={"run_id": ctx.run_id, "strategy_id": ctx.strategy_id},
        )
    # B2: by_run returns list[TradeEvent] (closed trades only — economic SSoT)
    assert len(logger.by_run(ctx_a.run_id)) == 1
    assert len(logger.by_run(ctx_b.run_id)) == 1


def test_by_strategy_filters_correctly():
    router, _, logger = make_observed_stack()
    for strategy in ["SMA", "RSI"]:
        ctx = RunContext(strategy_id=strategy)
        order = Order(
            symbol="BTC",
            side="buy",
            size=1.0,
            metadata={"run_id": ctx.run_id, "strategy_id": strategy},
        )
        router.execute(order, 100.0)
        router.sim_engine.close_position(
            "BTC", 115.0, metadata={"strategy_id": strategy}
        )
    # B2: by_strategy returns list[TradeEvent] (closed trades only — economic SSoT)
    sma_logs = logger.by_strategy("SMA")
    rsi_logs = logger.by_strategy("RSI")
    assert len(sma_logs) == 1
    assert len(rsi_logs) == 1


# -- Full backtest run carries context end-to-end --


def test_backtest_report_includes_run_id_and_strategy():
    candles = make_candles(n=60)
    portfolio = PortfolioState(balance=10000.0)
    from src.engine.virtual_exchange import VirtualExchange

    exchange = VirtualExchange(portfolio)
    router = ExecutionRouter(exchange)
    feed = HistoricalDataFeed(candles)
    strategy = SMAStrategy(fast_period=3, slow_period=10)
    agent = CodexAgent(strategy, KillSwitch())
    ctx = RunContext(strategy_id="SMA_3_10")
    engine = BacktestEngine(agent, router, feed, portfolio, run_context=ctx)
    report = engine.run()
    assert report["run_id"] == ctx.run_id
    assert report["strategy_id"] == "SMA_3_10"


def test_two_backtest_runs_have_distinct_run_ids():
    def run_once():
        candles = make_candles(n=40)
        portfolio = PortfolioState(balance=10000.0)
        exchange = VirtualExchange(portfolio)
        router = ExecutionRouter(exchange)
        feed = HistoricalDataFeed(candles)
        agent = CodexAgent(SMAStrategy(3, 10), KillSwitch())
        ctx = RunContext(strategy_id="SMA")
        return BacktestEngine(agent, router, feed, portfolio, ctx).run()

    r1 = run_once()
    r2 = run_once()
    assert r1["run_id"] != r2["run_id"]


def test_backtest_without_context_still_works():
    candles = make_candles(n=40)
    portfolio = PortfolioState(balance=10000.0)
    exchange = VirtualExchange(portfolio)
    router = ExecutionRouter(exchange)
    feed = HistoricalDataFeed(candles)
    agent = CodexAgent(SMAStrategy(3, 10), KillSwitch())
    engine = BacktestEngine(agent, router, feed, portfolio)  # no run_context
    report = engine.run()
    assert "run_id" in report
    assert report["strategy_id"] == "unknown"
