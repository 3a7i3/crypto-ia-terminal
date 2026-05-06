"""
P1 — AUTO REGIME DETECTION
Détecte automatiquement: bull_trend, bear_trend, range, scalp, protection
"""

from typing import List, Dict, Optional, Tuple
from statistics import mean, stdev
import math


class AutoRegimeDetector:
    """Détection automatique du régime de marché basée sur technicals"""

    def __init__(self, lookback_periods: int = 20):
        """
        Args:
            lookback_periods: Nombre de bougies à analyser
        """
        self.lookback = lookback_periods

    def detect(self, candles: List[Dict]) -> Tuple[str, float]:
        """
        Détecte le régime basé sur OHLCV

        Args:
            candles: Liste OHLCV [{open, high, low, close, volume}, ...]

        Returns:
            (regime: str, confidence: float 0-1)
        """
        if len(candles) < self.lookback:
            return "range", 0.5

        recent = candles[-self.lookback:]

        # Indicateurs
        sma_5 = self._sma(recent, 5)
        sma_20 = self._sma(recent, 20)
        volatility = self._volatility(recent)
        atr_val = self._atr(recent)
        rsi = self._rsi(recent)
        trend_strength = self._trend_strength(recent)

        # Logique de détection
        return self._classify(
            sma_5=sma_5[-1] if sma_5 else 0,
            sma_20=sma_20[-1] if sma_20 else 0,
            volatility=volatility,
            atr=atr_val,
            rsi=rsi,
            trend_strength=trend_strength,
            last_close=recent[-1]['close']
        )

    def _classify(self,
                  sma_5: float,
                  sma_20: float,
                  volatility: float,
                  atr: float,
                  rsi: float,
                  trend_strength: float,
                  last_close: float) -> Tuple[str, float]:
        """Classifie le régime basé sur indicateurs"""

        # Bull Trend: SMA5 > SMA20, RSI > 50, forte tendance
        if sma_5 > sma_20 and rsi > 50 and trend_strength > 0.65:
            confidence = min(0.95, 0.7 + trend_strength * 0.25)
            return "bull_trend", confidence

        # Bear Trend: SMA5 < SMA20, RSI < 50, forte tendance
        if sma_5 < sma_20 and rsi < 50 and trend_strength > 0.65:
            confidence = min(0.95, 0.7 + trend_strength * 0.25)
            return "bear_trend", confidence

        # Range: SMA proche, RSI 40-60, volatilité basse
        if abs(sma_5 - sma_20) / sma_20 < 0.01 and 40 < rsi < 60:
            if volatility < 0.015:
                return "range", 0.80
            else:
                return "range", 0.60

        # Scalp: Volatilité très basse, volume stable
        if volatility < 0.008 and trend_strength < 0.4:
            return "scalp", 0.75

        # Protection: Volatilité très haute, safe mode
        if volatility > 0.05 or atr > last_close * 0.02:
            return "protection", 0.85

        # Default
        if sma_5 > sma_20:
            return "bull_trend", 0.5
        else:
            return "bear_trend", 0.5

    def _sma(self, candles: List[Dict], period: int) -> List[float]:
        """Simple Moving Average"""
        closes = [c['close'] for c in candles]
        if len(closes) < period:
            return closes

        sma = []
        for i in range(len(closes) - period + 1):
            avg = sum(closes[i:i+period]) / period
            sma.append(avg)

        return sma

    def _volatility(self, candles: List[Dict]) -> float:
        """Volatilité des returns (stdev des log returns)"""
        closes = [c['close'] for c in candles]
        if len(closes) < 2:
            return 0.0

        returns = []
        for i in range(1, len(closes)):
            ret = math.log(closes[i] / closes[i-1])
            returns.append(ret)

        if not returns:
            return 0.0

        return stdev(returns) if len(returns) > 1 else 0.0

    def _atr(self, candles: List[Dict], period: int = 14) -> float:
        """Average True Range"""
        if len(candles) < period:
            return 0.0

        tr_values = []
        for i in range(1, len(candles)):
            high = candles[i]['high']
            low = candles[i]['low']
            close_prev = candles[i-1]['close']

            tr = max(
                high - low,
                abs(high - close_prev),
                abs(low - close_prev)
            )
            tr_values.append(tr)

        return mean(tr_values[-period:]) if tr_values else 0.0

    def _rsi(self, candles: List[Dict], period: int = 14) -> float:
        """Relative Strength Index"""
        closes = [c['close'] for c in candles]
        if len(closes) < period + 1:
            return 50.0

        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        seed = deltas[:period]

        up = sum(d for d in seed if d > 0) / period
        down = sum(-d for d in seed if d < 0) / period

        rs = up / down if down != 0 else 1.0
        rsi = 100 - (100 / (1 + rs))

        for delta in deltas[period:]:
            up = (up * (period - 1) + (delta if delta > 0 else 0)) / period
            down = (down * (period - 1) + (-delta if delta < 0 else 0)) / period

            rs = up / down if down != 0 else 1.0
            rsi = 100 - (100 / (1 + rs))

        return rsi

    def _trend_strength(self, candles: List[Dict]) -> float:
        """Force de la tendance (0-1)"""
        closes = [c['close'] for c in candles]
        if len(closes) < 5:
            return 0.5

        # Calculer pente linéaire
        n = len(closes)
        x_mean = n / 2
        y_mean = mean(closes)

        numerator = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0

        # Normalize slope en 0-1
        avg_price = y_mean
        slope_pct = (slope / avg_price * 100) if avg_price != 0 else 0

        # -5% to +5% slope = 0-1 strength
        trend_strength = min(1.0, max(0.0, abs(slope_pct) / 5.0))

        return trend_strength

    def get_regime_params(self, regime: str) -> Dict[str, float]:
        """Retourne les paramètres TP/SL recommandés pour un régime"""
        params = {
            "bull_trend": {"tp": 0.025, "sl": 0.010, "trailing_pct": 0.015},
            "bear_trend": {"tp": 0.025, "sl": 0.010, "trailing_pct": 0.015},
            "range": {"tp": 0.008, "sl": 0.008, "trailing_pct": 0.005},
            "scalp": {"tp": 0.003, "sl": 0.002, "trailing_pct": 0.002},
            "protection": {"tp": 0.015, "sl": 0.020, "trailing_pct": 0.010},
        }
        return params.get(regime, {"tp": 0.020, "sl": 0.010, "trailing_pct": 0.010})


class MultiTimeframeAnalysis:
    """Analyse multi-timeframe pour décisions plus robustes"""

    def __init__(self):
        self.detector = AutoRegimeDetector()

    def analyze_timeframes(self,
                          candles_5m: List[Dict],
                          candles_15m: List[Dict],
                          candles_1h: List[Dict]) -> Dict:
        """
        Analyse sur 3 timeframes pour robustesse

        Returns:
            {
                "5m": (regime, conf),
                "15m": (regime, conf),
                "1h": (regime, conf),
                "consensus": regime,
                "agreement": pct
            }
        """
        regime_5m, conf_5m = self.detector.detect(candles_5m)
        regime_15m, conf_15m = self.detector.detect(candles_15m)
        regime_1h, conf_1h = self.detector.detect(candles_1h)

        regimes = [regime_5m, regime_15m, regime_1h]

        # Consensus: le régime le plus fréquent
        regime_counts = {}
        for r in regimes:
            regime_counts[r] = regime_counts.get(r, 0) + 1

        consensus = max(regime_counts, key=regime_counts.get)
        agreement = regime_counts[consensus] / 3

        return {
            "5m": (regime_5m, conf_5m),
            "15m": (regime_15m, conf_15m),
            "1h": (regime_1h, conf_1h),
            "consensus": consensus,
            "agreement": agreement,
            "regime_counts": regime_counts,
        }


def create_regime_aware_position(regime: str,
                                 symbol: str,
                                 side: str,
                                 entry_price: float,
                                 size: float) -> Dict:
    """Factory pour créer une position avec paramètres adaptés au régime"""
    detector = AutoRegimeDetector()
    params = detector.get_regime_params(regime)

    return {
        "symbol": symbol,
        "side": side,
        "entry_price": entry_price,
        "size": size,
        "regime": regime,
        "tp": entry_price * (1 + params["tp"]) if side == "BUY" else entry_price * (1 - params["tp"]),
        "sl": entry_price * (1 - params["sl"]) if side == "BUY" else entry_price * (1 + params["sl"]),
        "trailing_pct": params["trailing_pct"],
    }
