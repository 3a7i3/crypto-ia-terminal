"""
signal_engine.py — Traduit une stratégie (dict) + candles en signal BUY/HOLD/SELL.

Utilisé par PaperTradingEngine pour décider l'action à chaque cycle.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

_INDICATORS = {"RSI", "EMA", "MACD", "BOLLINGER", "VWAP", "ATR"}


def compute_signal(strategy: dict, candles: list[dict]) -> str:
    """
    Retourne "BUY", "SELL" ou "HOLD".

    Args:
        strategy: dict avec au moins entry_indicator, period,
                  entry_threshold, exit_threshold.
        candles:  liste de dicts OHLCV (ordre chronologique).
    """
    if not candles or len(candles) < 5:
        return "HOLD"

    closes = [float(c["close"]) for c in candles]
    indicator = str(strategy.get("entry_indicator", "RSI")).upper()
    period = max(2, int(strategy.get("period", 14)))
    entry_thr = float(strategy.get("entry_threshold", 30))
    exit_thr = float(strategy.get("exit_threshold", 70))

    try:
        if indicator == "RSI":
            val = _rsi(closes, period)
            if val < entry_thr:
                return "BUY"
            if val > exit_thr:
                return "SELL"

        elif indicator == "EMA":
            ema = _ema(closes, period)
            if closes[-1] > ema * (1 + entry_thr / 1000):
                return "BUY"
            if closes[-1] < ema * (1 - exit_thr / 1000):
                return "SELL"

        elif indicator == "MACD":
            fast, slow = 12, 26
            macd_line = _ema(closes, fast)[-1] - _ema(closes, slow)[-1]
            macd_prev = (
                _ema(closes[:-1], fast)[-1] - _ema(closes[:-1], slow)[-1]
                if len(closes) > 1
                else macd_line
            )
            if macd_prev < 0 and macd_line > 0:
                return "BUY"
            if macd_prev > 0 and macd_line < 0:
                return "SELL"

        elif indicator == "BOLLINGER":
            n = min(period, len(closes))
            window = closes[-n:]
            mean = sum(window) / n
            std = math.sqrt(sum((x - mean) ** 2 for x in window) / n) + 1e-9
            lower = mean - 2 * std
            upper = mean + 2 * std
            if closes[-1] < lower:
                return "BUY"
            if closes[-1] > upper:
                return "SELL"

        elif indicator == "VWAP":
            volumes = [float(c.get("volume", 1.0)) for c in candles]
            total_vol = sum(volumes) + 1e-9
            vwap = sum(closes[i] * volumes[i] for i in range(len(closes))) / total_vol
            if closes[-1] < vwap * (1 - entry_thr / 1000):
                return "BUY"
            if closes[-1] > vwap * (1 + exit_thr / 1000):
                return "SELL"

        elif indicator == "ATR":
            highs = [float(c.get("high", closes[i])) for i, c in enumerate(candles)]
            lows = [float(c.get("low", closes[i])) for i, c in enumerate(candles)]
            n = min(period, len(closes) - 1)
            trs = [
                max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
                for i in range(1, n + 1)
            ]
            atr = sum(trs) / len(trs) if trs else 0.0
            atr_pct = atr / closes[-1] * 100 if closes[-1] else 0.0
            if atr_pct < entry_thr / 10:
                return "BUY"
            if atr_pct > exit_thr / 10:
                return "SELL"

    except Exception as exc:
        logger.debug("[SignalEngine] %s: %s", indicator, exc)

    return "HOLD"


# ── Indicateurs internes (stdlib pure) ────────────────────────────────────────


def _ema(prices: list[float], period: int) -> list[float]:
    if not prices:
        return []
    k = 2.0 / (period + 1)
    out = [prices[0]]
    for p in prices[1:]:
        out.append(p * k + out[-1] * (1 - k))
    return out


def _rsi(prices: list[float], period: int) -> float:
    if len(prices) <= period:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        d = prices[i] - prices[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    for i in range(period + 1, len(prices)):
        d = prices[i] - prices[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
    rs = avg_g / (avg_l + 1e-9)
    return 100.0 - 100.0 / (1.0 + rs)
