"""Feature engineering — builds market features from OHLCV candles."""

from __future__ import annotations

import math
from statistics import stdev


class FeatureEngineer:
    """Extracts and validates market features from OHLCV candle data."""

    def extract_features(self, candles: list[dict]) -> dict:
        volumes = [float(c.get("volume", 0)) for c in candles] if candles else []
        avg_volume_pre = (sum(volumes) / len(volumes)) if volumes else 0.0
        volume_ratio_pre = (volumes[-1] / avg_volume_pre if avg_volume_pre > 0 else 1.0) if volumes else 1.0

        if not candles or len(candles) < 2:
            result = self._empty_features()
            result["avg_volume"] = round(avg_volume_pre, 2)
            result["volume_ratio"] = round(volume_ratio_pre, 4)
            return result

        closes  = [float(c.get("close",  0)) for c in candles]
        highs   = [float(c.get("high",   c.get("close", 0))) for c in candles]
        lows    = [float(c.get("low",    c.get("close", 0))) for c in candles]

        price = closes[-1]
        if price == 0:
            result = self._empty_features()
            result["avg_volume"] = round(avg_volume_pre, 2)
            result["volume_ratio"] = round(volume_ratio_pre, 4)
            return result

        # ── Retours ──────────────────────────────────────────────────────────
        returns = [
            (closes[i] - closes[i-1]) / closes[i-1]
            for i in range(1, len(closes)) if closes[i-1] != 0
        ]

        # ── Momentum & volatilité ─────────────────────────────────────────────
        momentum       = (closes[-1] - closes[0]) / closes[0] if closes[0] else 0.0
        realized_vol   = stdev(returns) if len(returns) > 1 else abs(returns[0]) if returns else 0.0
        avg_volume     = avg_volume_pre
        volume_ratio   = volume_ratio_pre

        if returns:
            direction    = 1 if momentum >= 0 else -1
            aligned      = sum(1 for r in returns if r * direction > 0)
            trend_strength = aligned / len(returns)
        else:
            trend_strength = 0.5

        # ── ATR (14 périodes) ────────────────────────────────────────────────
        atr = self._atr(closes, highs, lows, period=14)
        atr_ratio = atr / price if price else 0.0   # ATR normalisé / prix

        # ── RSI (14) ─────────────────────────────────────────────────────────
        rsi = self._rsi(closes, period=14)

        # ── EMA (20 / 50) ─────────────────────────────────────────────────────
        ema20 = self._ema(closes, 20)[-1] if len(closes) >= 20 else price
        ema50 = self._ema(closes, 50)[-1] if len(closes) >= 50 else price
        ema_cross = (price - ema20) / ema20 if ema20 else 0.0   # distance EMA20

        # ── MACD (12-26-9) ───────────────────────────────────────────────────
        macd_line, macd_signal, macd_hist = self._macd(closes)

        # ── Bandes de Bollinger (20, ±2σ) ───────────────────────────────────
        bb_upper, bb_mid, bb_lower, bb_pct = self._bollinger(closes, period=20)

        # ── VWAP approché ────────────────────────────────────────────────────
        vwap_window = min(50, len(closes))
        c_w = closes[-vwap_window:]
        v_w = volumes[-vwap_window:]
        total_vol = sum(v_w) + 1e-9
        vwap      = sum(c_w[i] * v_w[i] for i in range(vwap_window)) / total_vol
        vwap_dist = (price - vwap) / vwap if vwap else 0.0

        # ── Supports / Résistances simplifiés (plus haut/bas 20 bougies) ─────
        window = 20
        recent_high = max(highs[-window:]) if len(highs) >= window else max(highs)
        recent_low  = min(lows[-window:])  if len(lows)  >= window else min(lows)
        range_pos   = (price - recent_low) / (recent_high - recent_low) \
                      if recent_high != recent_low else 0.5   # 0=bas du range, 1=haut

        return {
            # Basiques
            "momentum":           round(momentum,       6),
            "realized_volatility": round(realized_vol,  6),
            "trend_strength":     round(trend_strength, 4),
            "avg_volume":         round(avg_volume,     2),
            "volume_ratio":       round(volume_ratio,   4),
            # ATR
            "atr":                round(atr,            4),
            "atr_ratio":          round(atr_ratio,      6),  # ← utilisé par CAE
            "volatility":         round(atr_ratio,      6),  # alias pour compatibilité
            # RSI
            "rsi":                round(rsi,            2),
            "rsi_oversold":       rsi < 30,
            "rsi_overbought":     rsi > 70,
            # EMA
            "ema20":              round(ema20,          4),
            "ema50":              round(ema50,          4),
            "ema_cross":          round(ema_cross,      6),   # >0 = prix au-dessus EMA20
            "ema_bullish":        ema20 > ema50,
            # MACD
            "macd_line":          round(macd_line,      4),
            "macd_signal":        round(macd_signal,    4),
            "macd_hist":          round(macd_hist,      4),
            "macd_bullish":       macd_hist > 0,
            # Bollinger
            "bb_upper":           round(bb_upper,       4),
            "bb_lower":           round(bb_lower,       4),
            "bb_pct":             round(bb_pct,         4),   # 0=bas bande, 1=haut bande
            "bb_squeeze":         (bb_upper - bb_lower) / bb_mid < 0.04 if bb_mid else False,
            # VWAP
            "vwap":               round(vwap,           4),
            "vwap_dist":          round(vwap_dist,      6),
            # Range
            "recent_high":        round(recent_high,    4),
            "recent_low":         round(recent_low,     4),
            "range_pos":          round(range_pos,      4),   # 0=bas, 1=haut du range
        }

    def detect_anomalies(self, features: dict) -> list[str]:
        anomalies: list[str] = []
        vol          = features.get("realized_volatility", 0.0)
        volume_ratio = features.get("volume_ratio", 1.0)
        momentum     = features.get("momentum", 0.0)
        rsi          = features.get("rsi", 50.0)
        atr_ratio    = features.get("atr_ratio", 0.0)

        if vol > 0.05:
            anomalies.append(f"high_volatility:{vol:.4f}")
        if volume_ratio > 3.0:
            anomalies.append(f"volume_spike:{volume_ratio:.1f}x")
        if abs(momentum) > 0.10:
            anomalies.append(f"extreme_momentum_{'up' if momentum > 0 else 'down'}:{momentum:.4f}")
        if rsi < 20:
            anomalies.append(f"rsi_extreme_oversold:{rsi:.1f}")
        if rsi > 80:
            anomalies.append(f"rsi_extreme_overbought:{rsi:.1f}")
        if atr_ratio > 0.04:
            anomalies.append(f"atr_extreme:{atr_ratio:.3f}")
        return anomalies

    # ── Indicateurs (stdlib pure, pas de pandas/ta-lib) ───────────────────────

    @staticmethod
    def _ema(prices: list[float], period: int) -> list[float]:
        if not prices:
            return []
        k   = 2.0 / (period + 1)
        out = [prices[0]]
        for p in prices[1:]:
            out.append(p * k + out[-1] * (1 - k))
        return out

    def _rsi(self, prices: list[float], period: int = 14) -> float:
        if len(prices) <= period:
            return 50.0
        gains, losses = [], []
        for i in range(1, period + 1):
            d = prices[i] - prices[i-1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        avg_g = sum(gains) / period
        avg_l = sum(losses) / period
        for i in range(period + 1, len(prices)):
            d = prices[i] - prices[i-1]
            avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
            avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
        rs = avg_g / (avg_l + 1e-9)
        return 100.0 - 100.0 / (1.0 + rs)

    def _atr(self, closes: list[float], highs: list[float], lows: list[float],
             period: int = 14) -> float:
        if len(closes) < 2:
            return 0.0
        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i]  - closes[i-1]),
            )
            trs.append(tr)
        if not trs:
            return 0.0
        window = trs[-period:] if len(trs) >= period else trs
        return sum(window) / len(window)

    def _macd(self, prices: list[float],
              fast: int = 12, slow: int = 26, signal_period: int = 9
              ) -> tuple[float, float, float]:
        if len(prices) < slow + signal_period:
            return 0.0, 0.0, 0.0
        ema_fast   = self._ema(prices, fast)
        ema_slow   = self._ema(prices, slow)
        n = min(len(ema_fast), len(ema_slow))
        macd_vals  = [ema_fast[-n+i] - ema_slow[-n+i] for i in range(n)]
        sig_vals   = self._ema(macd_vals, signal_period)
        macd_line  = macd_vals[-1]
        sig_line   = sig_vals[-1]
        return macd_line, sig_line, round(macd_line - sig_line, 6)

    @staticmethod
    def _bollinger(prices: list[float], period: int = 20,
                   nb_std: float = 2.0) -> tuple[float, float, float, float]:
        if len(prices) < period:
            p = prices[-1]
            return p, p, p, 0.5
        window = prices[-period:]
        mid    = sum(window) / period
        var    = sum((x - mid) ** 2 for x in window) / period
        std    = math.sqrt(var)
        upper  = mid + nb_std * std
        lower  = mid - nb_std * std
        pct    = (prices[-1] - lower) / (upper - lower) if upper != lower else 0.5
        return upper, mid, lower, pct

    def _empty_features(self) -> dict:
        return {
            "momentum": 0.0, "realized_volatility": 0.0, "trend_strength": 0.5,
            "avg_volume": 0.0, "volume_ratio": 1.0,
            "atr": 0.0, "atr_ratio": 0.0, "volatility": 0.0,
            "rsi": 50.0, "rsi_oversold": False, "rsi_overbought": False,
            "ema20": 0.0, "ema50": 0.0, "ema_cross": 0.0, "ema_bullish": False,
            "macd_line": 0.0, "macd_signal": 0.0, "macd_hist": 0.0, "macd_bullish": False,
            "bb_upper": 0.0, "bb_lower": 0.0, "bb_pct": 0.5, "bb_squeeze": False,
            "vwap": 0.0, "vwap_dist": 0.0,
            "recent_high": 0.0, "recent_low": 0.0, "range_pos": 0.5,
        }
