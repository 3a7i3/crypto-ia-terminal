import pytest

from src.agent.codex_agent import CodexAgent
from src.agent.momentum_strategy import MomentumStrategy
from src.backtest.market_generator import range_bound, trend_up
from src.risk.kill_switch import KillSwitch


def _market(close, symbol="BTC"):
    return {"close": close, "symbol": symbol, "high": close + 1, "low": close - 1}


def test_no_signal_before_warmup():
    m = MomentumStrategy(period=10, threshold=0.03)
    for i in range(10):
        assert m.generate_signal(_market(100.0 + i)) is None


def test_buy_on_strong_upward_momentum():
    m = MomentumStrategy(period=5, threshold=0.03)
    prices = [100, 101, 102, 103, 104, 104]
    sigs = [m.generate_signal(_market(p)) for p in prices]
    # après warmup, si la hausse > 3% → buy
    buys = [s for s in sigs if s and s.direction == "buy"]
    assert len(buys) > 0


def test_sell_on_strong_downward_momentum():
    m = MomentumStrategy(period=5, threshold=0.03)
    prices = [100, 99, 98, 97, 96, 95]
    sigs = [m.generate_signal(_market(p)) for p in prices]
    sells = [s for s in sigs if s and s.direction == "sell"]
    assert len(sells) > 0


def test_no_signal_in_flat_market():
    m = MomentumStrategy(period=5, threshold=0.03)
    prices = [100.0] * 15
    sigs = [m.generate_signal(_market(p)) for p in prices]
    assert all(s is None for s in sigs)


def test_confidence_above_threshold():
    m = MomentumStrategy(period=5, threshold=0.02)
    prices = [100, 101, 102, 103, 104]
    for p in prices:
        sig = m.generate_signal(_market(p))
        if sig:
            assert sig.confidence >= 0.6


def test_fewer_trades_than_rsi():
    from src.agent.rsi_strategy import RSIStrategy

    candles = trend_up(n=120, seed=0)

    def _count_signals(strategy):
        count = 0
        for c in candles:
            sig = strategy.generate_signal(c)
            if sig:
                count += 1
        return count

    rsi_count = _count_signals(RSIStrategy(14, 30, 70))
    mom_count = _count_signals(MomentumStrategy(period=30, threshold=0.03))
    # Momentum doit générer moins de signaux que RSI
    assert mom_count <= rsi_count


def test_implements_strategy_interface():
    from src.agent.strategy_interface import StrategyInterface

    assert isinstance(MomentumStrategy(), StrategyInterface)


def test_through_codex_agent():
    agent = CodexAgent(MomentumStrategy(period=5, threshold=0.02), KillSwitch())
    prices = [100, 101, 102, 103, 104, 105]
    sigs = [agent.on_market(_market(p)) for p in prices]
    assert any(s is not None for s in sigs)


def test_larger_period_fewer_signals():
    candles = trend_up(n=200, seed=0)
    m_fast = MomentumStrategy(period=10, threshold=0.02)
    m_slow = MomentumStrategy(period=50, threshold=0.02)
    fast_count = sum(1 for c in candles if m_fast.generate_signal(c))
    slow_count = sum(1 for c in candles if m_slow.generate_signal(c))
    assert slow_count <= fast_count
