"""
P2 — ML EXIT PREDICTION
Prédire le meilleur moment pour sortir une position
Basé sur: features technicals + ML (simple neural network)
"""

import math
from statistics import mean, stdev
from typing import Dict, List, Tuple


class ExitFeatureEngineer:
    """Ingénierie de features pour ML exit prediction"""

    @staticmethod
    def extract_features(
        candles: List[Dict], entry_price: float, entry_idx: int, lookback: int = 20
    ) -> Dict[str, float]:
        """
        Extrait features technicals pour prédire exit

        Returns:
            {
                "rsi": float,
                "macd": float,
                "trend_strength": float,
                "volatility": float,
                "distance_to_entry": float,
                "mfe_pct": float,
                "mae_pct": float,
                ...
            }
        """
        if entry_idx >= len(candles):
            return {}

        current_candle = candles[-1]
        current_price = current_candle["close"]

        features = {}

        # 1. RSI (Relative Strength Index)
        features["rsi"] = ExitFeatureEngineer._calculate_rsi(
            [c["close"] for c in candles[-20:]]
        )

        # 2. MACD (Moving Average Convergence Divergence)
        features["macd"] = ExitFeatureEngineer._calculate_macd(
            [c["close"] for c in candles[-26:]]
        )

        # 3. Trend strength
        features["trend_strength"] = ExitFeatureEngineer._calculate_trend_strength(
            [c["close"] for c in candles[-lookback:]]
        )

        # 4. Volatility
        features["volatility"] = ExitFeatureEngineer._calculate_volatility(
            [c["close"] for c in candles[-lookback:]]
        )

        # 5. Distance from entry
        features["distance_to_entry"] = (current_price - entry_price) / entry_price

        # 6. MFE (Maximum Favorable Excursion)
        candles_since_entry = candles[entry_idx:]
        if candles_since_entry:
            max_price = max(c["high"] for c in candles_since_entry)
            features["mfe_pct"] = (max_price - entry_price) / entry_price

        # 7. MAE (Maximum Adverse Excursion)
        if candles_since_entry:
            min_price = min(c["low"] for c in candles_since_entry)
            features["mae_pct"] = (min_price - entry_price) / entry_price

        # 8. Bollinger Bands position
        features["bb_position"] = ExitFeatureEngineer._calculate_bb_position(
            [c["close"] for c in candles[-20:]], current_price
        )

        # 9. Momentum
        closes = [c["close"] for c in candles[-10:]]
        features["momentum"] = (
            (closes[-1] - closes[0]) / closes[0] if closes[0] > 0 else 0
        )

        # 10. Time in trade (relative)
        features["time_in_trade"] = min(1.0, (len(candles) - entry_idx) / lookback)

        return features

    @staticmethod
    def _calculate_rsi(prices: List[float], period: int = 14) -> float:
        """RSI calculation"""
        if len(prices) < period + 1:
            return 50.0

        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        seed = deltas[:period]

        up = sum(d for d in seed if d > 0) / period
        down = sum(-d for d in seed if d < 0) / period or 0.0001

        rs = up / down if down != 0 else 1.0
        rsi = 100 - (100 / (1 + rs))

        for delta in deltas[period:]:
            up = (up * (period - 1) + (delta if delta > 0 else 0)) / period
            down = (down * (period - 1) + (-delta if delta < 0 else 0)) / period
            rs = up / down if down != 0 else 1.0
            rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def _calculate_macd(prices: List[float]) -> float:
        """MACD calculation (simplified)"""
        if len(prices) < 26:
            return 0.0

        ema_12 = ExitFeatureEngineer._ema(prices, 12)
        ema_26 = ExitFeatureEngineer._ema(prices, 26)

        macd = ema_12 - ema_26
        return macd

    @staticmethod
    def _ema(prices: List[float], period: int) -> float:
        """Exponential Moving Average"""
        if len(prices) < period:
            return mean(prices) if prices else 0.0

        multiplier = 2 / (period + 1)
        ema = mean(prices[:period])

        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    @staticmethod
    def _calculate_trend_strength(prices: List[float]) -> float:
        """Trend strength (0-1)"""
        if len(prices) < 5:
            return 0.5

        n = len(prices)
        x_mean = n / 2
        y_mean = mean(prices)

        numerator = sum((i - x_mean) * (prices[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0
        avg_price = y_mean
        slope_pct = (slope / avg_price * 100) if avg_price != 0 else 0

        trend = min(1.0, max(0.0, abs(slope_pct) / 5.0))
        return trend

    @staticmethod
    def _calculate_volatility(prices: List[float]) -> float:
        """Volatility (std dev of returns)"""
        if len(prices) < 2:
            return 0.0

        returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]
        return stdev(returns) if len(returns) > 1 else 0.0

    @staticmethod
    def _calculate_bb_position(prices: List[float], current_price: float) -> float:
        """Bollinger Bands position (0-1 scale)"""
        if len(prices) < 20:
            return 0.5

        sma = mean(prices[-20:])
        std = stdev(prices[-20:]) if len(prices[-20:]) > 1 else 1.0

        upper_band = sma + (2 * std)
        lower_band = sma - (2 * std)

        if upper_band - lower_band == 0:
            return 0.5

        position = (current_price - lower_band) / (upper_band - lower_band)
        return min(1.0, max(0.0, position))


class SimpleNeuralNetwork:
    """Simple neural network pour exit prediction"""

    def __init__(self, input_size: int = 10, hidden_size: int = 16):
        """
        Architecture simple:
        Input (10) -> Hidden (16) -> Output (1)
        """
        self.input_size = input_size
        self.hidden_size = hidden_size

        # Poids (initialisés aléatoirement petit)
        import random

        random.seed(42)

        self.w1 = [
            [random.gauss(0, 0.1) for _ in range(hidden_size)]
            for _ in range(input_size)
        ]
        self.b1 = [0.0] * hidden_size

        self.w2 = [random.gauss(0, 0.1) for _ in range(hidden_size)]
        self.b2 = 0.0

    def relu(self, x: float) -> float:
        """ReLU activation"""
        return max(0.0, x)

    def sigmoid(self, x: float) -> float:
        """Sigmoid activation (pour probabilité)"""
        try:
            return 1.0 / (1.0 + math.exp(-x))
        except OverflowError:
            # math.exp déborde pour |x| très grand : sigmoid → 0 ou 1 selon le signe
            return 0.0 if x < 0 else 1.0

    def forward(self, inputs: List[float]) -> float:
        """Forward pass"""
        if len(inputs) != self.input_size:
            return 0.5

        # Hidden layer
        hidden = []
        for j in range(self.hidden_size):
            z = self.b1[j]
            for i in range(self.input_size):
                z += inputs[i] * self.w1[i][j]
            hidden.append(self.relu(z))

        # Output layer
        z_out = self.b2
        for j in range(self.hidden_size):
            z_out += hidden[j] * self.w2[j]

        # Probabilité de good exit (0-1)
        probability = self.sigmoid(z_out)
        return probability

    def predict_exit_quality(self, inputs: List[float]) -> Tuple[str, float]:
        """
        Prédit la qualité du exit

        Returns:
            ("good_exit" / "bad_exit" / "hold", confidence 0-1)
        """
        prob = self.forward(inputs)

        if prob > 0.7:
            return "good_exit", prob
        elif prob < 0.3:
            return "bad_exit", 1 - prob
        else:
            return "hold", 0.5


class MLExitPredictor:
    """Système complet de prédiction ML pour exits"""

    def __init__(self):
        self.feature_engineer = ExitFeatureEngineer()
        self.model = SimpleNeuralNetwork(input_size=10, hidden_size=16)

    def predict_exit(
        self, candles: List[Dict], entry_price: float, entry_idx: int
    ) -> Dict:
        """
        Prédit le meilleur exit pour une position

        Returns:
            {
                "should_exit": bool,
                "quality": str ("good_exit" / "bad_exit" / "hold"),
                "confidence": float,
                "features": dict,
                "reason": str
            }
        """
        # Extraire features
        features = self.feature_engineer.extract_features(
            candles, entry_price, entry_idx
        )

        if not features:
            return {
                "should_exit": False,
                "quality": "hold",
                "confidence": 0.5,
                "features": {},
                "reason": "Not enough data",
            }

        # Normaliser features (simple z-score)
        feature_vector = self._normalize_features(features)

        # Prédiction ML
        quality, confidence = self.model.predict_exit_quality(feature_vector)

        # Logique décision
        should_exit = quality != "hold"

        reason = self._generate_reason(features, quality, confidence)

        return {
            "should_exit": should_exit,
            "quality": quality,
            "confidence": confidence,
            "features": features,
            "reason": reason,
        }

    def _normalize_features(self, features: Dict[str, float]) -> List[float]:
        """Normalise features pour le réseau"""
        # Order: rsi, macd, trend_strength, volatility, distance_to_entry,
        #        mfe_pct, mae_pct, bb_position, momentum, time_in_trade

        feature_order = [
            "rsi",
            "macd",
            "trend_strength",
            "volatility",
            "distance_to_entry",
            "mfe_pct",
            "mae_pct",
            "bb_position",
            "momentum",
            "time_in_trade",
        ]

        vector = []
        for key in feature_order:
            value = features.get(key, 0.0)

            # Normaliser à [-1, 1]
            if key == "rsi":
                value = (value - 50) / 50
            elif key == "bb_position":
                value = (value - 0.5) * 2
            elif key in ["trend_strength", "volatility", "time_in_trade"]:
                value = (value - 0.5) * 2
            elif key in ["distance_to_entry", "mfe_pct", "mae_pct", "momentum"]:
                value = min(1.0, max(-1.0, value))

            vector.append(value)

        return vector

    def _generate_reason(self, features: Dict, quality: str, confidence: float) -> str:
        """Génère une explication pour la prédiction"""
        rsi = features.get("rsi", 50)
        trend = features.get("trend_strength", 0.5)
        distance = features.get("distance_to_entry", 0)

        if quality == "good_exit":
            if rsi > 70:
                return "RSI overbought, good exit zone"
            elif distance > 0.02:
                return "Good profit (>2%), exit suggested"
            else:
                return "Optimal exit point detected"

        elif quality == "bad_exit":
            if rsi < 30:
                return "RSI oversold, hold or buy more"
            elif distance < -0.01:
                return "Loss zone, wait for recovery"
            else:
                return "Exit conditions not met"

        else:  # hold
            if trend > 0.7:
                return "Strong trend, hold position"
            else:
                return "Neutral - monitor for better exit"
