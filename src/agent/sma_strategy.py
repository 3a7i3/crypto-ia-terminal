from src.agent.strategy_interface import StrategyInterface
from src.domain.signal import Signal


class SMAStrategy(StrategyInterface):
    def __init__(self, fast_period: int = 5, slow_period: int = 20):
        self.fast = fast_period
        self.slow = slow_period
        self.prices: list[float] = []
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def _sma(self, period: int) -> float | None:
        if len(self.prices) < period:
            return None
        return sum(self.prices[-period:]) / period

    def generate_signal(self, market_data: dict) -> Signal | None:
        price = market_data.get("close") or market_data.get("price")
        symbol = market_data.get("symbol", "BTC")
        if price is None:
            return None

        self.prices.append(price)

        fast = self._sma(self.fast)
        slow = self._sma(self.slow)

        if (
            fast is None
            or slow is None
            or self._prev_fast is None
            or self._prev_slow is None
        ):
            self._prev_fast = fast
            self._prev_slow = slow
            return None

        signal = None
        # Golden cross: fast crosses above slow
        if self._prev_fast <= self._prev_slow and fast > slow:
            signal = Signal(symbol=symbol, direction="buy", confidence=0.75)
        # Death cross: fast crosses below slow
        elif self._prev_fast >= self._prev_slow and fast < slow:
            signal = Signal(symbol=symbol, direction="sell", confidence=0.75)

        self._prev_fast = fast
        self._prev_slow = slow
        return signal
