"""
Famille C — Breakout.
Cassure de range : achat si le prix dépasse le plus haut des N dernières candles,
vente si le prix passe sous le plus bas.
"""

from src.agent.strategy_interface import StrategyInterface
from src.domain.signal import Signal


class BreakoutStrategy(StrategyInterface):
    def __init__(self, period: int = 20):
        self.period = period
        self._candles: list[dict] = []

    def generate_signal(self, market_data: dict) -> Signal | None:
        symbol = market_data.get("symbol", "BTC")
        close = market_data.get("close") or market_data.get("price")
        if close is None:
            return None

        self._candles.append(market_data)

        # Attendre period + 1 candles (la fenêtre de référence exclut la candle courante)
        if len(self._candles) < self.period + 1:
            return None

        window = self._candles[-(self.period + 1) : -1]
        highest = max(float(c.get("high", c.get("close", 0))) for c in window)
        lowest = min(float(c.get("low", c.get("close", 0))) for c in window)

        if float(close) > highest:
            return Signal(symbol=symbol, direction="buy", confidence=0.75)
        if float(close) < lowest:
            return Signal(symbol=symbol, direction="sell", confidence=0.75)
        return None
