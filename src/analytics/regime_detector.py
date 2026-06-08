"""
Classifie un ensemble de candles en 3 régimes :
  trend    — mouvement directionnel net
  volatile — amplitude ATR élevée, pas de direction stable
  range    — faible amplitude, oscillation autour de la moyenne

Aucune dépendance externe. Maths de base uniquement.
"""


class RegimeDetector:

    def __init__(
        self,
        atr_volatile_threshold: float = 0.018,
        trend_slope_threshold: float = 0.04,
        sma_period: int = 20,
    ):
        self.atr_volatile_threshold = atr_volatile_threshold
        self.trend_slope_threshold = trend_slope_threshold
        self.sma_period = sma_period

    def classify(self, candles: list[dict]) -> str:
        """
        Retourne "trending", "volatile" ou "sideways".
        Requiert au moins sma_period candles.
        """
        if len(candles) < self.sma_period:
            return "sideways"

        closes = [float(c["close"]) for c in candles]
        highs = [float(c.get("high", c["close"])) for c in candles]
        lows = [float(c.get("low", c["close"])) for c in candles]

        # -- Volatilité ATR normalisée --
        atr_values = [
            (highs[i] - lows[i]) / closes[i]
            for i in range(len(candles))
            if closes[i] > 0
        ]
        atr_pct = sum(atr_values) / len(atr_values) if atr_values else 0.0

        if atr_pct > self.atr_volatile_threshold:
            return "volatile"

        # -- Pente SMA (trend) --
        sma_early = sum(closes[: self.sma_period]) / self.sma_period
        sma_late = sum(closes[-self.sma_period :]) / self.sma_period
        slope = abs(sma_late - sma_early) / sma_early if sma_early > 0 else 0.0

        if slope > self.trend_slope_threshold:
            return "trending"

        return "sideways"

    def metrics(self, candles: list[dict]) -> dict:
        """Retourne les métriques brutes utilisées pour la classification."""
        if len(candles) < self.sma_period:
            return {
                "regime": "sideways",
                "atr_pct": 0.0,
                "slope": 0.0,
                "n": len(candles),
            }

        closes = [float(c["close"]) for c in candles]
        highs = [float(c.get("high", c["close"])) for c in candles]
        lows = [float(c.get("low", c["close"])) for c in candles]

        atr_values = [
            (highs[i] - lows[i]) / closes[i]
            for i in range(len(candles))
            if closes[i] > 0
        ]
        atr_pct = sum(atr_values) / len(atr_values) if atr_values else 0.0

        sma_early = sum(closes[: self.sma_period]) / self.sma_period
        sma_late = sum(closes[-self.sma_period :]) / self.sma_period
        slope = (sma_late - sma_early) / sma_early if sma_early > 0 else 0.0

        return {
            "regime": self.classify(candles),
            "atr_pct": round(atr_pct, 5),
            "slope": round(slope, 5),
            "n": len(candles),
        }
