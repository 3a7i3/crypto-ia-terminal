"""
Tests pour signal_engine.compute_signal — 6 indicateurs + edge cases.
"""

from __future__ import annotations

import pytest

from quant_hedge_ai.agents.execution.signal_engine import compute_signal


def _candles(prices: list[float]) -> list[dict]:
    return [
        {"close": p, "high": p * 1.01, "low": p * 0.99, "volume": 1000.0}
        for p in prices
    ]


def _flat(n: int = 20, price: float = 100.0) -> list[dict]:
    return _candles([price] * n)


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_candles_returns_hold():
    assert compute_signal({}, []) == "HOLD"


def test_too_few_candles_returns_hold():
    assert compute_signal({}, _candles([100, 101, 102, 103])) == "HOLD"


def test_unknown_indicator_returns_hold():
    assert compute_signal({"entry_indicator": "UNKNOWN"}, _flat(20)) == "HOLD"


# ── RSI ───────────────────────────────────────────────────────────────────────


def test_rsi_oversold_returns_buy():
    # Série en forte baisse → RSI < 30 → BUY
    prices = [100 - i * 3 for i in range(20)]
    result = compute_signal(
        {
            "entry_indicator": "RSI",
            "period": 14,
            "entry_threshold": 30,
            "exit_threshold": 70,
        },
        _candles(prices),
    )
    assert result == "BUY"


def test_rsi_overbought_returns_sell():
    # Série en forte hausse → RSI > 70 → SELL
    prices = [100 + i * 3 for i in range(20)]
    result = compute_signal(
        {
            "entry_indicator": "RSI",
            "period": 14,
            "entry_threshold": 30,
            "exit_threshold": 70,
        },
        _candles(prices),
    )
    assert result == "SELL"


def test_rsi_neutral_returns_hold():
    # Alternance hausse/baisse → RSI ~50 (entre les seuils 30/70)
    prices = [100 + (5 if i % 2 == 0 else -5) for i in range(20)]
    result = compute_signal(
        {
            "entry_indicator": "RSI",
            "period": 14,
            "entry_threshold": 30,
            "exit_threshold": 70,
        },
        _candles(prices),
    )
    assert result == "HOLD"


# ── EMA ───────────────────────────────────────────────────────────────────────


def test_ema_price_above_returns_buy():
    # Dernier prix très au-dessus de l'EMA → BUY
    prices = [100.0] * 19 + [120.0]  # spike haussier
    result = compute_signal(
        {
            "entry_indicator": "EMA",
            "period": 10,
            "entry_threshold": 50,
            "exit_threshold": 50,
        },
        _candles(prices),
    )
    assert result == "BUY"


def test_ema_price_below_returns_sell():
    prices = [100.0] * 19 + [80.0]  # spike baissier
    result = compute_signal(
        {
            "entry_indicator": "EMA",
            "period": 10,
            "entry_threshold": 50,
            "exit_threshold": 50,
        },
        _candles(prices),
    )
    assert result == "SELL"


def test_ema_price_at_ema_returns_hold():
    result = compute_signal(
        {
            "entry_indicator": "EMA",
            "period": 10,
            "entry_threshold": 1,
            "exit_threshold": 1,
        },
        _flat(20),
    )
    assert result == "HOLD"


# ── MACD ──────────────────────────────────────────────────────────────────────


def test_macd_bullish_crossover_returns_buy():
    # Downtrend long (MACD négatif) + dernier candle spike haussier fort
    # Force le crossover au dernier candle: macd_prev < 0, macd_line > 0
    prices = [100 - i for i in range(50)] + [500.0]
    result = compute_signal({"entry_indicator": "MACD"}, _candles(prices))
    assert result == "BUY"


def test_macd_bearish_crossover_returns_sell():
    # Uptrend long (MACD positif) + dernier candle spike baissier fort
    prices = [100 + i for i in range(50)] + [1.0]
    result = compute_signal({"entry_indicator": "MACD"}, _candles(prices))
    assert result == "SELL"


# ── BOLLINGER ─────────────────────────────────────────────────────────────────


def test_bollinger_price_below_lower_band_returns_buy():
    # Fluctuation normale puis crash → prix sous la bande inférieure
    prices = [100.0] * 18 + [100.0, 70.0]
    result = compute_signal(
        {"entry_indicator": "BOLLINGER", "period": 20},
        _candles(prices),
    )
    assert result == "BUY"


def test_bollinger_price_above_upper_band_returns_sell():
    prices = [100.0] * 18 + [100.0, 130.0]
    result = compute_signal(
        {"entry_indicator": "BOLLINGER", "period": 20},
        _candles(prices),
    )
    assert result == "SELL"


def test_bollinger_flat_returns_hold():
    result = compute_signal({"entry_indicator": "BOLLINGER", "period": 14}, _flat(20))
    assert result == "HOLD"


# ── VWAP ─────────────────────────────────────────────────────────────────────


def test_vwap_price_below_vwap_returns_buy():
    # Volumes identiques, dernier prix bien en-dessous du VWAP moyen
    candles = _candles([100.0] * 19 + [75.0])
    result = compute_signal(
        {"entry_indicator": "VWAP", "entry_threshold": 50, "exit_threshold": 50},
        candles,
    )
    assert result == "BUY"


def test_vwap_price_above_vwap_returns_sell():
    candles = _candles([100.0] * 19 + [130.0])
    result = compute_signal(
        {"entry_indicator": "VWAP", "entry_threshold": 50, "exit_threshold": 50},
        candles,
    )
    assert result == "SELL"


# ── ATR ───────────────────────────────────────────────────────────────────────


def test_atr_low_volatility_returns_buy():
    # ATR très faible (prix très stables) → pct < threshold → BUY
    result = compute_signal(
        {
            "entry_indicator": "ATR",
            "period": 10,
            "entry_threshold": 100,
            "exit_threshold": 0,
        },
        _flat(20),
    )
    assert result == "BUY"


def test_atr_high_volatility_returns_sell():
    # ATR très élevé (prix très volatils) → pct > threshold → SELL
    prices = [100 + (i % 2) * 20 for i in range(20)]  # oscillation ±20%
    result = compute_signal(
        {
            "entry_indicator": "ATR",
            "period": 10,
            "entry_threshold": 0,
            "exit_threshold": 1,
        },
        _candles(prices),
    )
    assert result == "SELL"


# ── Retour toujours string valide ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "indicator", ["RSI", "EMA", "MACD", "BOLLINGER", "VWAP", "ATR"]
)
def test_all_indicators_return_valid_signal(indicator):
    result = compute_signal({"entry_indicator": indicator}, _flat(30))
    assert result in (
        "BUY",
        "SELL",
        "HOLD",
    ), f"{indicator}: signal invalide: {result!r}"
