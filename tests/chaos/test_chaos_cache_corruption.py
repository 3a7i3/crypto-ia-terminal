"""
Chaos #7 — Cache corruption.

Injecte des bougies OHLCV corrompues (NaN, négatif, champ manquant, spike).
Invariants vérifiés :
  - validate_candles rejette toutes les formes de corruption connues
  - compute_signal ne crash pas sur des données corrompues
  - Un dataset mixte (valides + corrompus) ne conserve que les bougies valides
"""

from __future__ import annotations

import math

import pytest

from quant_hedge_ai.agents.execution.signal_engine import compute_signal
from quant_hedge_ai.agents.market.ohlcv_validator import validate_candles


def _good(price: float = 100.0) -> dict:
    return {
        "open": price,
        "high": price * 1.01,
        "low": price * 0.99,
        "close": price,
        "volume": 1000.0,
        "source": "ccxt_live",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCacheCorruption:
    def test_nan_close_rejected(self):
        candles = [
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": math.nan,
                "volume": 1000.0,
            }
        ]
        valid, report = validate_candles(candles)
        assert len(valid) == 0
        assert report.dropped == 1
        assert "nan_inf_close" in report.reasons

    def test_inf_price_rejected(self):
        candles = [
            {
                "open": float("inf"),
                "high": float("inf"),
                "low": 99.0,
                "close": float("inf"),
                "volume": 1000.0,
            }
        ]
        valid, report = validate_candles(candles)
        assert report.dropped >= 1, "INVARIANT BRISÉ: prix infini accepté"

    def test_negative_close_rejected(self):
        candles = [
            {
                "open": -100.0,
                "high": 1.0,
                "low": -101.0,
                "close": -100.0,
                "volume": 1000.0,
            }
        ]
        valid, report = validate_candles(candles)
        assert report.dropped == 1, "INVARIANT BRISÉ: prix négatif accepté"

    def test_negative_volume_rejected(self):
        candles = [
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": -50.0}
        ]
        valid, report = validate_candles(candles)
        assert report.dropped == 1, "INVARIANT BRISÉ: volume négatif accepté"

    def test_missing_close_field_rejected(self):
        candles = [{"open": 100.0, "high": 101.0, "low": 99.0, "volume": 1000.0}]
        valid, report = validate_candles(candles)
        assert report.dropped == 1
        assert "missing_close" in report.reasons

    def test_high_below_close_rejected(self):
        """high < close viole l'intégrité OHLCV."""
        candles = [
            {"open": 100.0, "high": 90.0, "low": 89.0, "close": 100.0, "volume": 1000.0}
        ]
        valid, report = validate_candles(candles)
        assert report.dropped == 1, "INVARIANT BRISÉ: high < close accepté"

    def test_price_spike_ratio_rejected(self):
        """high/low > 10x (spike) est rejeté."""
        candles = [
            {
                "open": 100.0,
                "high": 1_100.0,
                "low": 100.0,
                "close": 100.0,
                "volume": 1000.0,
            }
        ]
        valid, report = validate_candles(candles)
        assert report.dropped == 1, "INVARIANT BRISÉ: spike prix x11 accepté"

    def test_all_zero_candle_rejected(self):
        """Bougie tout-zéro (cache poisoning typique) est rejetée."""
        candles = [{"open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0, "volume": 0.0}]
        valid, report = validate_candles(candles)
        assert report.dropped == 1, "INVARIANT BRISÉ: bougie tout-zéro acceptée"

    def test_non_numeric_field_rejected(self):
        """Valeur non-numérique dans un champ OHLCV est rejetée."""
        candles = [
            {
                "open": "corrupt",
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000.0,
            }
        ]
        valid, report = validate_candles(candles)
        assert report.dropped == 1

    def test_mixed_dataset_only_valid_kept(self):
        """Mélange valides + corrompus → seules les bougies valides passent."""
        candles = [
            _good(100.0),
            {
                "open": math.nan,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000.0,
            },
            _good(101.0),
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": -1.0,
                "volume": 1000.0,
            },
            _good(102.0),
        ]
        valid, report = validate_candles(candles)
        assert len(valid) == 3, f"INVARIANT BRISÉ: {len(valid)}/3 bougies valides"
        assert report.dropped == 2

    def test_compute_signal_no_crash_on_mixed_corruption(self):
        """compute_signal ne crash pas sur un mix valides/corrompus."""
        candles = [_good(100.0 - i) for i in range(15)] + [
            {
                "open": math.nan,
                "high": math.nan,
                "low": math.nan,
                "close": math.nan,
                "volume": 0.0,
            },
            {"open": -1.0, "high": -0.5, "low": -2.0, "close": -1.0, "volume": 1000.0},
            _good(85.0),
        ]
        try:
            result = compute_signal(
                {
                    "entry_indicator": "RSI",
                    "period": 14,
                    "entry_threshold": 30,
                    "exit_threshold": 70,
                },
                candles,
            )
        except Exception as exc:
            pytest.fail(f"CRASH SILENCIEUX sur données corrompues: {exc}")
        assert result in ("BUY", "SELL", "HOLD"), f"Signal invalide: {result}"

    def test_fully_corrupted_dataset_returns_no_valid(self):
        """Un dataset entièrement corrompu retourne 0 bougies valides."""
        candles = [
            {
                "open": math.nan,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000.0,
            },
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": -1.0},
            {"open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0, "volume": 0.0},
        ]
        valid, report = validate_candles(candles)
        assert len(valid) == 0
        assert report.dropped == 3
