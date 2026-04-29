"""Feature engineering — builds market features from OHLCV candles."""

from __future__ import annotations

from statistics import mean, stdev


class FeatureEngineer:
    """Extracts and validates market features from OHLCV candle data."""

    def extract_features(self, candles: list[dict]) -> dict:
        if not candles:
            return self._empty_features()

        closes = [float(c.get("close", 0)) for c in candles]
        volumes = [float(c.get("volume", 0)) for c in candles]

        if len(closes) < 2:
            return {
                "momentum": 0.0,
                "realized_volatility": 0.0,
                "trend_strength": 0.5,
                "avg_volume": volumes[0] if volumes else 0.0,
                "volume_ratio": 1.0,
            }

        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
            if closes[i - 1] != 0
        ]

        momentum = (closes[-1] - closes[0]) / closes[0] if closes[0] else 0.0
        realized_vol = (
            stdev(returns) if len(returns) > 1 else abs(returns[0]) if returns else 0.0
        )
        avg_volume = mean(volumes) if volumes else 0.0
        volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1.0

        # Trend strength: fraction of returns in same direction as momentum
        if returns:
            direction = 1 if momentum >= 0 else -1
            aligned = sum(1 for r in returns if r * direction > 0)
            trend_strength = aligned / len(returns)
        else:
            trend_strength = 0.5

        return {
            "momentum": round(momentum, 6),
            "realized_volatility": round(realized_vol, 6),
            "trend_strength": round(trend_strength, 4),
            "avg_volume": round(avg_volume, 2),
            "volume_ratio": round(volume_ratio, 4),
        }

    def detect_anomalies(self, features: dict) -> list[str]:
        anomalies: list[str] = []
        vol = features.get("realized_volatility", 0.0)
        volume_ratio = features.get("volume_ratio", 1.0)
        momentum = features.get("momentum", 0.0)

        if vol > 0.05:
            anomalies.append(f"high_volatility:{vol:.4f}")
        if volume_ratio > 3.0:
            anomalies.append(f"volume_spike:{volume_ratio:.1f}x")
        if abs(momentum) > 0.10:
            direction = "up" if momentum > 0 else "down"
            anomalies.append(f"extreme_momentum_{direction}:{momentum:.4f}")

        return anomalies

    def _empty_features(self) -> dict:
        return {
            "momentum": 0.0,
            "realized_volatility": 0.0,
            "trend_strength": 0.5,
            "avg_volume": 0.0,
            "volume_ratio": 1.0,
        }
