"""
Famille B — Mean Reversion.
RSI extrême : achat sous le seuil oversold, vente au-dessus de overbought.
"""

from src.agent.strategy_interface import StrategyInterface
from src.domain.signal import Signal


class RSIStrategy(StrategyInterface):
    def __init__(
        self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0
    ):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self._prices: list[float] = []

    def generate_signal(self, market_data: dict) -> Signal | None:
        price = market_data.get("close") or market_data.get("price")
        symbol = market_data.get("symbol", "BTC")
        if price is None:
            return None

        self._prices.append(float(price))

        rsi = self._rsi()
        if rsi is None:
            return None

        if rsi < self.oversold:
            return Signal(symbol=symbol, direction="buy", confidence=0.75)
        if rsi > self.overbought:
            return Signal(symbol=symbol, direction="sell", confidence=0.75)
        return None

    def _rsi(self) -> float | None:
        # Wilder smoothing sur `period` variations
        if len(self._prices) < self.period + 1:
            return None

        deltas = [
            self._prices[i] - self._prices[i - 1]
            for i in range(len(self._prices) - self.period, len(self._prices))
        ]

        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]

        avg_gain = sum(gains) / self.period if gains else 0.0
        avg_loss = sum(losses) / self.period if losses else 0.0

        if avg_gain == 0 and avg_loss == 0:
            return 50.0  # aucun mouvement = neutre
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
