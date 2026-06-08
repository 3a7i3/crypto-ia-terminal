"""
Famille D — Momentum lent (Rate of Change).

Signal : achète quand le prix a progressé de X% sur N candles.
         vend quand le prix a baissé de X% sur N candles.

Propriétés voulues :
  - trades rares (seuil élevé + longue période)
  - amplitude par trade >> spread
  - compatible ENL realistic/heavy
"""

from src.agent.strategy_interface import StrategyInterface
from src.domain.signal import Signal


class MomentumStrategy(StrategyInterface):
    def __init__(
        self,
        period: int = 30,
        threshold: float = 0.03,  # 3% de mouvement minimum
        confidence: float = 0.80,
    ):
        self.period = period
        self.threshold = threshold
        self.confidence = confidence
        self._prices: list[float] = []

    def generate_signal(self, market_data: dict) -> Signal | None:
        price = float(market_data.get("close") or market_data.get("price", 0))
        symbol = market_data.get("symbol", "BTC")
        if price <= 0:
            return None

        self._prices.append(price)

        if len(self._prices) < self.period + 1:
            return None

        base = self._prices[-(self.period + 1)]
        roc = (price - base) / base  # Rate of Change

        if roc > self.threshold:
            return Signal(symbol=symbol, direction="buy", confidence=self.confidence)
        if roc < -self.threshold:
            return Signal(symbol=symbol, direction="sell", confidence=self.confidence)
        return None
