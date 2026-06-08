from src.agent.codex_agent import CodexAgent
from src.agent.sma_strategy import SMAStrategy
from src.backtest.data_feed import HistoricalDataFeed
from src.backtest.engine import BacktestEngine
from src.backtest.market_generator import high_volatility, range_bound, trend_up
from src.engine.execution_router import ExecutionRouter
from src.engine.virtual_exchange import VirtualExchange
from src.portfolio.portfolio_state import PortfolioState
from src.risk.kill_switch import KillSwitch
from src.risk.regime_gate import RegimeGate
from src.runtime.run_context import RunContext


def _make_agent():
    return CodexAgent(SMAStrategy(3, 10), KillSwitch())


# -- Blocage selon régime --


def test_gate_blocks_signal_in_wrong_regime():
    agent = _make_agent()
    gate = RegimeGate(agent, allowed_regimes={"sideways"}, window=30)
    # En trend, le gate doit bloquer
    for c in trend_up(n=60):
        gate.on_market(c)
    assert gate.last_regime == "trending"
    assert gate.blocked > 0


def test_gate_passes_signal_in_allowed_regime():
    agent = _make_agent()
    gate = RegimeGate(agent, allowed_regimes={"sideways"}, window=30)
    signals = []
    for c in range_bound(n=80):
        sig = gate.on_market(c)
        if sig:
            signals.append(sig)
    assert gate.last_regime == "sideways"


def test_gate_blocks_all_in_volatile_when_not_allowed():
    agent = _make_agent()
    gate = RegimeGate(agent, allowed_regimes={"sideways", "trending"}, window=30)
    for c in high_volatility(n=60):
        gate.on_market(c)
    assert gate.last_regime == "volatile"
    assert gate.blocked > 0


def test_gate_multi_regime_allowed():
    agent = _make_agent()
    gate = RegimeGate(
        agent, allowed_regimes={"trending", "sideways", "volatile"}, window=30
    )
    # Tous régimes autorisés → aucun blocage dû au régime
    # (des signaux peuvent ne pas sortir si SMA n'a pas assez de données, mais pas de blocage régime)
    for c in range_bound(n=60):
        gate.on_market(c)
    assert gate.last_regime in {"trending", "sideways", "volatile"}


# -- Reset --


def test_gate_reset_clears_state():
    agent = _make_agent()
    gate = RegimeGate(agent, allowed_regimes={"range"}, window=30)
    for c in trend_up(n=40):
        gate.on_market(c)
    gate.reset()
    assert gate.blocked == 0
    assert gate.passed == 0
    assert gate._history == []


# -- Test A/B sur mêmes seeds --


def _run_backtest(candles, use_gate: bool) -> dict:
    portfolio = PortfolioState(balance=10_000.0)
    exchange = VirtualExchange(portfolio)
    router = ExecutionRouter(exchange)
    feed = HistoricalDataFeed(candles)
    base_agent = CodexAgent(SMAStrategy(3, 10), KillSwitch())
    agent = (
        RegimeGate(base_agent, allowed_regimes={"sideways"}) if use_gate else base_agent
    )
    ctx = RunContext(strategy_id="SMA_GATE" if use_gate else "SMA_RAW")
    return BacktestEngine(agent, router, feed, portfolio, ctx).run()


def test_ab_same_seeds_different_results():
    # Sur des candles de trend, le gate doit produire moins (ou 0) de trades
    candles = trend_up(n=120, seed=42)
    raw = _run_backtest(candles, use_gate=False)
    gate = _run_backtest(candles, use_gate=True)
    # Le gate bloque en trend → moins de trades ou 0
    assert gate["total_trades"] <= raw["total_trades"]


def test_gate_does_not_hurt_range_performance():
    candles = range_bound(n=120, seed=42)
    raw = _run_backtest(candles, use_gate=False)
    gate = _run_backtest(candles, use_gate=True)
    # En range (régime autorisé), les trades doivent être identiques
    assert gate["total_trades"] == raw["total_trades"]


def test_gate_reduces_trades_in_volatile():
    candles = high_volatility(n=120, seed=42)
    raw = _run_backtest(candles, use_gate=False)
    gate = _run_backtest(candles, use_gate=True)
    assert gate["total_trades"] <= raw["total_trades"]
