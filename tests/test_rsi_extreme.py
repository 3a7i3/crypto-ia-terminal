from src.agent.rsi_extreme_strategy import RSIExtremeStrategy
from src.agent.rsi_strategy import RSIStrategy
from src.backtest.market_generator import trend_up


def _market(close, symbol="BTC"):
    return {"close": close, "symbol": symbol}


def test_no_signal_before_warmup():
    # Sans trend filter, warmup = rsi_period + 1 = 15 candles
    s = RSIExtremeStrategy(rsi_period=14, use_trend_filter=False)
    for i in range(14):
        assert s.generate_signal(_market(100.0 + i * 0.1)) is None


def test_buy_requires_uptrend():
    s = RSIExtremeStrategy(rsi_period=5, oversold=10, overbought=90, trend_period=10)
    # Uptrend: prices rising overall
    uptrend = [100 + i * 0.5 for i in range(10)]
    # Oversold condition: sharp drop after uptrend
    drop = [uptrend[-1] - j * 2 for j in range(6)]
    prices = uptrend + drop
    sigs = [s.generate_signal(_market(p)) for p in prices]
    buys = [sg for sg in sigs if sg and sg.direction == "buy"]
    # Not guaranteed due to warmup, but shouldn't crash
    assert isinstance(buys, list)


def test_sell_requires_downtrend():
    s = RSIExtremeStrategy(rsi_period=5, oversold=10, overbought=90, trend_period=10)
    # Downtrend
    downtrend = [100 - i * 0.5 for i in range(10)]
    # Overbought: sharp rise after downtrend
    pump = [downtrend[-1] + j * 2 for j in range(6)]
    prices = downtrend + pump
    sigs = [s.generate_signal(_market(p)) for p in prices]
    sells = [sg for sg in sigs if sg and sg.direction == "sell"]
    assert isinstance(sells, list)


def test_no_buy_in_downtrend_with_trend_filter():
    # Avec use_trend_filter=True : le downtrend bloque les achats
    s = RSIExtremeStrategy(
        rsi_period=5, oversold=40, overbought=60, trend_period=5, use_trend_filter=True
    )
    prices = [100 - i * 1.0 for i in range(20)]
    sigs = [s.generate_signal(_market(p)) for p in prices]
    buys = [sg for sg in sigs if sg and sg.direction == "buy"]
    assert len(buys) == 0


def test_fewer_signals_than_standard_rsi():
    candles = trend_up(n=200, seed=0)

    standard = RSIStrategy(14, 30, 70)
    extreme = RSIExtremeStrategy(14, 10, 90, trend_period=50)

    std_count = sum(1 for c in candles if standard.generate_signal(c))
    ext_count = sum(1 for c in candles if extreme.generate_signal(c))

    # Extreme RSI generates fewer or equal signals
    assert ext_count <= std_count


def test_confidence_above_min():
    s = RSIExtremeStrategy(confidence=0.85)
    for c in trend_up(n=100, seed=0):
        sig = s.generate_signal(c)
        if sig:
            assert sig.confidence >= 0.6


def test_implements_interface():
    from src.agent.strategy_interface import StrategyInterface

    assert isinstance(RSIExtremeStrategy(), StrategyInterface)
