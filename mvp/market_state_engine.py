"""
market_state_engine.py — Market State Engine MVP

Question fondamentale : "Quel marché suis-je en train de trader ?"

Produit un MarketState cohérent et lisible en 3 dimensions :
  - trend     : bullish | bearish | chop
  - pressure  : neutral | long_squeeze | short_squeeze | liquidation_cascade
  - volatility: compression | normal | expansion | panic

Chaque dimension a un score de confiance.
Pas de magie. Explicable. Auditable.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MarketState:
    symbol: str
    timestamp: float = field(default_factory=time.time)

    # Dimensions
    trend: str = "chop"                     # bullish | bearish | chop
    pressure: str = "neutral"              # neutral | long_squeeze | short_squeeze | liquidation_cascade
    volatility: str = "normal"             # compression | normal | expansion | panic

    # Scores de confiance [0, 1]
    trend_confidence: float = 0.0
    pressure_confidence: float = 0.0
    volatility_confidence: float = 0.0

    # Score global — combinaison pondérée des 3 dimensions
    global_confidence: float = 0.0

    # Signaux bruts utilisés (pour audit/debug)
    inputs: dict[str, float] = field(default_factory=dict)

    def is_tradeable(self) -> bool:
        """Le marché est suffisamment lisible pour trader."""
        return self.global_confidence >= 0.45 and self.volatility != "panic"

    def is_favorable_for_long(self) -> bool:
        return (
            self.trend == "bullish"
            and self.pressure in ("neutral", "short_squeeze")
            and self.volatility in ("normal", "expansion")
            and self.trend_confidence >= 0.5
        )

    def is_favorable_for_short(self) -> bool:
        return (
            self.trend == "bearish"
            and self.pressure in ("neutral", "long_squeeze")
            and self.volatility in ("normal", "expansion")
            and self.trend_confidence >= 0.5
        )

    def summary(self) -> str:
        return (
            f"{self.symbol} | trend={self.trend}({self.trend_confidence:.0%}) "
            f"pressure={self.pressure}({self.pressure_confidence:.0%}) "
            f"vol={self.volatility}({self.volatility_confidence:.0%}) "
            f"conf={self.global_confidence:.0%}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "trend": self.trend,
            "pressure": self.pressure,
            "volatility": self.volatility,
            "trend_confidence": round(self.trend_confidence, 3),
            "pressure_confidence": round(self.pressure_confidence, 3),
            "volatility_confidence": round(self.volatility_confidence, 3),
            "global_confidence": round(self.global_confidence, 3),
            "is_tradeable": self.is_tradeable(),
        }


class MarketStateEngine:
    """
    Construit un MarketState à partir des données brutes disponibles.

    Inputs acceptés :
      - candles_1h  : liste OHLCV format ccxt  [ts, o, h, l, c, v]
      - candles_4h  : idem (optionnel, améliore la détection trend)
      - funding_rate: float (optionnel)
      - open_interest: float (optionnel)
      - ob_imbalance: float [-1, +1] (optionnel, depuis microstructure)

    Design :
      - Pas de ML ici — règles claires, reproductibles
      - Chaque règle est documentée et testable individuellement
      - Fallback gracieux si données manquantes
    """

    def analyze(
        self,
        symbol: str,
        candles_1h: list,
        candles_4h: list | None = None,
        funding_rate: float = 0.0,
        open_interest: float = 0.0,
        oi_delta_pct: float = 0.0,
        ob_imbalance: float = 0.0,
    ) -> MarketState:

        state = MarketState(symbol=symbol)

        if not candles_1h or len(candles_1h) < 20:
            logger.debug("[MarketState] %s — candles insuffisantes", symbol)
            return state

        closes_1h = [float(c[4]) for c in candles_1h if len(c) >= 5]
        highs_1h  = [float(c[2]) for c in candles_1h if len(c) >= 5]
        lows_1h   = [float(c[3]) for c in candles_1h if len(c) >= 5]
        volumes   = [float(c[5]) for c in candles_1h if len(c) >= 6]

        # ── TREND ─────────────────────────────────────────────────────────────
        trend, trend_conf = self._classify_trend(closes_1h, candles_4h)
        state.trend = trend
        state.trend_confidence = trend_conf

        # ── PRESSURE ──────────────────────────────────────────────────────────
        pressure, pres_conf = self._classify_pressure(
            closes_1h, funding_rate, oi_delta_pct, ob_imbalance, volumes
        )
        state.pressure = pressure
        state.pressure_confidence = pres_conf

        # ── VOLATILITY ────────────────────────────────────────────────────────
        volatility, vol_conf = self._classify_volatility(closes_1h, highs_1h, lows_1h)
        state.volatility = volatility
        state.volatility_confidence = vol_conf

        # ── CONFIANCE GLOBALE ─────────────────────────────────────────────────
        # Pondération : trend est le plus important
        state.global_confidence = (
            trend_conf * 0.45 +
            pres_conf  * 0.30 +
            vol_conf   * 0.25
        )

        # Inputs pour audit
        state.inputs = {
            "ema21": self._ema(closes_1h, 21),
            "ema55": self._ema(closes_1h, 55),
            "rsi14": self._rsi(closes_1h, 14),
            "atr_pct": self._atr_pct(highs_1h, lows_1h, closes_1h, 14),
            "funding_rate": funding_rate,
            "oi_delta_pct": oi_delta_pct,
            "ob_imbalance": ob_imbalance,
        }

        logger.debug("[MarketState] %s", state.summary())
        return state

    # ──────────────────────────────────────────────────────────────────────────
    # TREND
    # ──────────────────────────────────────────────────────────────────────────

    def _classify_trend(
        self, closes_1h: list[float], candles_4h: list | None
    ) -> tuple[str, float]:
        """
        Trend = consensus entre 1h et 4h.
        Signal : EMA21 vs EMA55 + pente de prix.
        """
        if len(closes_1h) < 55:
            return "chop", 0.3

        ema21 = self._ema(closes_1h, 21)
        ema55 = self._ema(closes_1h, 55)
        rsi   = self._rsi(closes_1h, 14)
        closes_1h[-1]

        # Score directionnel 1h [-1, +1]
        ema_signal = (ema21 - ema55) / ema55 if ema55 else 0.0
        rsi_signal = (rsi - 50) / 50.0

        # Pente récente (10 dernières bougies)
        slope = (closes_1h[-1] - closes_1h[-10]) / closes_1h[-10] if closes_1h[-10] else 0.0

        score_1h = ema_signal * 0.5 + rsi_signal * 0.3 + slope * 0.2

        # Confirmation 4h (améliore la confiance si disponible)
        score_4h = 0.0
        if candles_4h and len(candles_4h) >= 21:
            closes_4h = [float(c[4]) for c in candles_4h if len(c) >= 5]
            ema21_4h = self._ema(closes_4h, 21)
            ema55_4h = self._ema(closes_4h, min(55, len(closes_4h)))
            score_4h = (ema21_4h - ema55_4h) / ema55_4h if ema55_4h else 0.0

        final_score = score_1h * 0.6 + score_4h * 0.4 if candles_4h else score_1h

        if final_score > 0.015:
            trend = "bullish"
            confidence = min(abs(final_score) * 15, 1.0)
        elif final_score < -0.015:
            trend = "bearish"
            confidence = min(abs(final_score) * 15, 1.0)
        else:
            trend = "chop"
            confidence = max(0.3, 1.0 - abs(final_score) * 30)

        return trend, round(confidence, 3)

    # ──────────────────────────────────────────────────────────────────────────
    # PRESSURE
    # ──────────────────────────────────────────────────────────────────────────

    def _classify_pressure(
        self,
        closes: list[float],
        funding_rate: float,
        oi_delta_pct: float,
        ob_imbalance: float,
        volumes: list[float],
    ) -> tuple[str, float]:
        """
        Pressure = tension entre longs et shorts.
        Sources : funding, OI delta, imbalance order book, volume spike.
        """
        score = 0.0
        confidence = 0.4

        # Funding rate : positif = longs surpeuplés (short_squeeze possible si retournement)
        if abs(funding_rate) > 0.001:
            confidence += 0.2
            if funding_rate > 0.003:
                score -= 0.4    # longs surchauffés → pression vendeuse latente
            elif funding_rate < -0.003:
                score += 0.4    # shorts surchauffés → squeeze potentiel
            elif funding_rate > 0.001:
                score -= 0.2
            else:
                score += 0.2

        # OI delta : expansion haussière = longs qui rentrent
        if abs(oi_delta_pct) > 0.05:
            confidence += 0.15
            score += oi_delta_pct * 0.3

        # Order book imbalance
        if abs(ob_imbalance) > 0.2:
            confidence += 0.15
            score += ob_imbalance * 0.3

        # Volume spike (volume actuel vs moyenne)
        if len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            last_vol = volumes[-1]
            if avg_vol > 0 and last_vol > avg_vol * 2.0:
                confidence += 0.1

        # Cascade : combinaison funding extrême + OI spike + imbalance fort
        if abs(funding_rate) > 0.005 and abs(oi_delta_pct) > 0.15:
            if funding_rate > 0 and ob_imbalance < -0.3:
                return "liquidation_cascade", min(confidence + 0.2, 1.0)

        if score > 0.3:
            return "short_squeeze", min(confidence, 1.0)
        if score < -0.3:
            return "long_squeeze", min(confidence, 1.0)
        return "neutral", min(confidence, 1.0)

    # ──────────────────────────────────────────────────────────────────────────
    # VOLATILITY
    # ──────────────────────────────────────────────────────────────────────────

    def _classify_volatility(
        self,
        closes: list[float],
        highs: list[float],
        lows: list[float],
    ) -> tuple[str, float]:
        """
        Volatility = ATR% normalisé vs historique récent.
        """
        if len(closes) < 20:
            return "normal", 0.4

        atr_pct = self._atr_pct(highs, lows, closes, 14)

        # Historique pour comparer
        if len(closes) >= 50:
            atrs = []
            for i in range(20, min(50, len(closes))):
                a = self._atr_pct(highs[:i], lows[:i], closes[:i], 14)
                atrs.append(a)
            avg_atr = sum(atrs) / len(atrs) if atrs else atr_pct
        else:
            avg_atr = atr_pct

        ratio = atr_pct / avg_atr if avg_atr > 0 else 1.0

        # Classification
        if atr_pct > 0.05 or ratio > 2.5:
            volatility = "panic"
            confidence = min((ratio - 2.5) / 2 + 0.6, 1.0)
        elif ratio > 1.5:
            volatility = "expansion"
            confidence = min((ratio - 1.5) / 1.5 * 0.5 + 0.5, 1.0)
        elif ratio < 0.5:
            volatility = "compression"
            confidence = min((0.5 - ratio) / 0.5 * 0.5 + 0.5, 1.0)
        else:
            volatility = "normal"
            confidence = 1.0 - abs(ratio - 1.0) * 0.5

        return volatility, round(max(0.1, min(confidence, 1.0)), 3)

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers techniques (reproductibles, testables)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        if len(values) < period:
            return values[-1] if values else 0.0
        k = 2.0 / (period + 1)
        ema = sum(values[:period]) / period
        for v in values[period:]:
            ema = v * k + ema * (1 - k)
        return ema

    @staticmethod
    def _rsi(closes: list[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains  = [max(d, 0) for d in deltas[-period:]]
        losses = [abs(min(d, 0)) for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        return 100 - 100 / (1 + avg_gain / avg_loss)

    @staticmethod
    def _atr_pct(highs: list, lows: list, closes: list, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 0.01
        trs = [
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            for i in range(1, len(closes))
        ]
        atr = sum(trs[-period:]) / period
        return atr / closes[-1] if closes[-1] else 0.01
