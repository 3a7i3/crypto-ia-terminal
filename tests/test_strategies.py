from src.agent.breakout_strategy import BreakoutStrategy
from src.agent.codex_agent import CodexAgent
from src.agent.rsi_strategy import RSIStrategy
from src.risk.kill_switch import KillSwitch


def _market(close, symbol="BTC", high=None, low=None):
    return {
        "close": close,
        "symbol": symbol,
        "high": high or close + 0.5,
        "low": low or close - 0.5,
    }


# ------------------------------------------------------------------ #
# RSI Strategy                                                          #
# ------------------------------------------------------------------ #


def test_rsi_no_signal_before_warmup():
    s = RSIStrategy(period=14)
    for i in range(14):
        assert s.generate_signal(_market(100.0 + i)) is None


def test_rsi_buy_on_oversold():
    s = RSIStrategy(period=5, oversold=30)
    prices = [100, 99, 98, 97, 96, 95]  # forte baisse → RSI bas
    signals = [s.generate_signal(_market(p)) for p in prices]
    buys = [sig for sig in signals if sig and sig.direction == "buy"]
    assert len(buys) > 0


def test_rsi_sell_on_overbought():
    s = RSIStrategy(period=5, overbought=70)
    prices = [100, 101, 102, 103, 104, 105]  # forte hausse → RSI haut
    signals = [s.generate_signal(_market(p)) for p in prices]
    sells = [sig for sig in signals if sig and sig.direction == "sell"]
    assert len(sells) > 0


def test_rsi_signal_confidence_valid():
    s = RSIStrategy(period=5, oversold=30)
    prices = [100, 99, 98, 97, 96, 95]
    for p in prices:
        sig = s.generate_signal(_market(p))
        if sig:
            assert 0.6 <= sig.confidence <= 1.0


def test_rsi_no_signal_in_neutral_zone():
    s = RSIStrategy(period=5, oversold=30, overbought=70)
    # Prix stables → RSI neutre
    signals = [s.generate_signal(_market(100.0)) for _ in range(20)]
    assert all(sig is None for sig in signals)


# ------------------------------------------------------------------ #
# Breakout Strategy                                                     #
# ------------------------------------------------------------------ #


def test_breakout_no_signal_before_warmup():
    s = BreakoutStrategy(period=20)
    for i in range(20):
        assert s.generate_signal(_market(100.0)) is None


def test_breakout_buy_on_high_break():
    s = BreakoutStrategy(period=5)
    base = [_market(100.0) for _ in range(5)]
    for c in base:
        s.generate_signal(c)
    sig = s.generate_signal(_market(105.0, high=105.5))  # dépasse le plus haut de 100
    assert sig is not None
    assert sig.direction == "buy"


def test_breakout_sell_on_low_break():
    s = BreakoutStrategy(period=5)
    base = [_market(100.0) for _ in range(5)]
    for c in base:
        s.generate_signal(c)
    sig = s.generate_signal(_market(94.0, low=93.5))  # passe sous le plus bas de 100
    assert sig is not None
    assert sig.direction == "sell"


def test_breakout_no_signal_inside_range():
    s = BreakoutStrategy(period=5)
    prices = [98, 99, 100, 101, 102]
    for p in prices:
        s.generate_signal(_market(p))
    # Prix dans le range → pas de signal
    sig = s.generate_signal(_market(100.0))
    assert sig is None


def test_breakout_confidence_valid():
    s = BreakoutStrategy(period=5)
    for p in [100.0] * 5:
        s.generate_signal(_market(p))
    sig = s.generate_signal(_market(110.0, high=110.5))
    if sig:
        assert sig.confidence >= 0.6


# ------------------------------------------------------------------ #
# Via CodexAgent (filtre confidence < 0.6)                             #
# ------------------------------------------------------------------ #


def test_rsi_through_codex_agent():
    agent = CodexAgent(RSIStrategy(period=5, oversold=30), KillSwitch())
    prices = [100, 99, 98, 97, 96, 95]
    signals = [agent.on_market(_market(p)) for p in prices]
    assert any(s is not None for s in signals)


def test_breakout_through_codex_agent():
    agent = CodexAgent(BreakoutStrategy(period=5), KillSwitch())
    for p in [100.0] * 5:
        agent.on_market(_market(p))
    sig = agent.on_market(_market(110.0, high=110.5))
    assert sig is not None


# ------------------------------------------------------------------ #
# Compatibilité StrategyInterface                                       #
# ------------------------------------------------------------------ #


def test_rsi_implements_interface():
    from src.agent.strategy_interface import StrategyInterface

    assert isinstance(RSIStrategy(), StrategyInterface)


def test_breakout_implements_interface():
    from src.agent.strategy_interface import StrategyInterface

    assert isinstance(BreakoutStrategy(), StrategyInterface)
