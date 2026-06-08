"""
RSI Extreme + Trend Filter.

Objectif : signaux rares à amplitude large.
  - RSI < 10 en uptrend → achat (oversold extrême, tendance haussière)
  - RSI > 90 en downtrend → vente (overbought extrême, tendance baissière)

Filtre de tendance : SMA(trend_period) - prix au-dessus = uptrend.
Signal quality > signal frequency.
"""

from src.agent.strategy_interface import StrategyInterface
from src.domain.signal import Signal


class RSIExtremeStrategy(StrategyInterface):
    """
    RSI extreme mean-reversion.

    use_trend_filter=False (défaut) : pure mean-reversion, pas de filtre de tendance.
        RSI < oversold → buy (oversold = rebond attendu)
        RSI > overbought → sell (overbought = correction attendue)

    use_trend_filter=True : entrée alignée avec la tendance longue.
        RSI < oversold ET uptrend → buy
        RSI > overbought ET downtrend → sell
        ⚠️ auto-contradictoire pour extrêmes < 20 / > 80 (RSI extrême = contre-tendance)
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 20.0,
        overbought: float = 80.0,
        trend_period: int = 50,
        use_trend_filter: bool = False,
        confidence: float = 0.85,
    ):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.trend_period = trend_period
        self.use_trend_filter = use_trend_filter
        self.confidence = confidence
        self._prices: list[float] = []

    def generate_signal(self, market_data: dict) -> Signal | None:
        price = float(market_data.get("close") or market_data.get("price", 0))
        symbol = market_data.get("symbol", "BTC")
        if price <= 0:
            return None

        self._prices.append(price)

        needed = (
            (self.rsi_period + 1)
            if not self.use_trend_filter
            else max(self.rsi_period + 1, self.trend_period)
        )
        if len(self._prices) < needed:
            return None

        rsi = self._rsi()
        if rsi is None:
            return None

        if self.use_trend_filter:
            trend = self._trend()
            if trend is None:
                return None
            if rsi < self.oversold and trend == "up":
                return Signal(
                    symbol=symbol, direction="buy", confidence=self.confidence
                )
            if rsi > self.overbought and trend == "down":
                return Signal(
                    symbol=symbol, direction="sell", confidence=self.confidence
                )
        else:
            if rsi < self.oversold:
                return Signal(
                    symbol=symbol, direction="buy", confidence=self.confidence
                )
            if rsi > self.overbought:
                return Signal(
                    symbol=symbol, direction="sell", confidence=self.confidence
                )

        return None

    def _rsi(self) -> float | None:
        if len(self._prices) < self.rsi_period + 1:
            return None
        deltas = [
            self._prices[i] - self._prices[i - 1]
            for i in range(len(self._prices) - self.rsi_period, len(self._prices))
        ]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]
        avg_g = sum(gains) / self.rsi_period if gains else 0.0
        avg_l = sum(losses) / self.rsi_period if losses else 0.0
        if avg_g == 0 and avg_l == 0:
            return 50.0
        if avg_l == 0:
            return 100.0
        return 100.0 - (100.0 / (1.0 + avg_g / avg_l))

    def _trend(self) -> str | None:
        if len(self._prices) < self.trend_period:
            return None
        sma = sum(self._prices[-self.trend_period :]) / self.trend_period
        price = self._prices[-1]
        return "up" if price > sma else "down"
