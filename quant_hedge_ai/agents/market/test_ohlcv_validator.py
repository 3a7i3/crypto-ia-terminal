"""Tests unitaires — ohlcv_validator."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from quant_hedge_ai.agents.market.ohlcv_validator import (
    ValidationReport,
    is_series_fresh,
    validate_candles,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _candle(**kwargs) -> dict:
    base = {
        "symbol": "BTC/USDT",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 1000.0,
        "source": "ccxt_live",
    }
    base.update(kwargs)
    return base


def _fresh_ts(age_seconds: float = 0.0) -> str:
    t = time.time() - age_seconds
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


# ── validate_candles ──────────────────────────────────────────────────────────


class TestValidateCandles:
    def test_valid_candle_passes(self):
        clean, report = validate_candles([_candle()], symbol="BTC/USDT")
        assert len(clean) == 1
        assert report.valid == 1
        assert report.dropped == 0

    def test_empty_input(self):
        clean, report = validate_candles([], symbol="BTC/USDT")
        assert clean == []
        assert report.total == 0

    def test_missing_close_field(self):
        c = _candle()
        del c["close"]
        clean, report = validate_candles([c])
        assert len(clean) == 0
        assert report.dropped == 1
        assert any("missing" in k for k in report.reasons)

    def test_missing_volume_field(self):
        c = _candle()
        del c["volume"]
        clean, report = validate_candles([c])
        assert len(clean) == 0
        assert any("missing" in k for k in report.reasons)

    def test_nan_close_rejected(self):
        clean, report = validate_candles([_candle(close=float("nan"))])
        assert len(clean) == 0
        assert any("nan" in k for k in report.reasons)

    def test_inf_open_rejected(self):
        clean, report = validate_candles([_candle(open=float("inf"))])
        assert len(clean) == 0
        assert any("nan_inf" in k for k in report.reasons)

    def test_negative_inf_rejected(self):
        clean, report = validate_candles([_candle(high=float("-inf"))])
        assert len(clean) == 0

    def test_non_positive_price_rejected(self):
        clean, report = validate_candles([_candle(close=0.0)])
        assert len(clean) == 0
        assert any("non_positive" in k for k in report.reasons)

    def test_negative_price_rejected(self):
        clean, report = validate_candles([_candle(low=-1.0)])
        assert len(clean) == 0

    def test_non_numeric_string_rejected(self):
        clean, report = validate_candles([_candle(close="not_a_number")])
        assert len(clean) == 0
        assert any("non_numeric" in k or "missing" in k for k in report.reasons)

    def test_high_less_than_close_rejected(self):
        # high doit être >= max(open, close)
        clean, report = validate_candles(
            [_candle(open=100, close=105, high=102, low=90)]
        )
        assert len(clean) == 0
        assert any("high" in k for k in report.reasons)

    def test_low_greater_than_open_rejected(self):
        clean, report = validate_candles(
            [_candle(open=100, close=95, high=110, low=98)]
        )
        assert len(clean) == 0
        assert any("low" in k for k in report.reasons)

    def test_spike_ratio_rejected(self):
        # high/low > 10 → spike
        clean, report = validate_candles(
            [_candle(open=100, close=100, high=1100, low=99)]
        )
        assert len(clean) == 0
        assert any("spike" in k for k in report.reasons)

    def test_mixed_valid_invalid(self):
        candles = [
            _candle(),  # valide
            _candle(close=float("nan")),  # invalide
            _candle(open=50, high=60, low=40, close=55),  # valide
        ]
        clean, report = validate_candles(candles)
        assert len(clean) == 2
        assert report.valid == 2
        assert report.dropped == 1
        assert report.total == 3

    def test_report_real_ratio_all_live(self):
        candles = [_candle(source="ccxt_live"), _candle(source="ccxt_live")]
        _, report = validate_candles(candles)
        assert report.real_ratio == 1.0

    def test_report_real_ratio_all_synthetic(self):
        candles = [_candle(source="synthetic"), _candle(source="synthetic")]
        _, report = validate_candles(candles)
        assert report.real_ratio == 0.0

    def test_report_real_ratio_mixed(self):
        candles = [_candle(source="ccxt_live"), _candle(source="synthetic")]
        _, report = validate_candles(candles)
        assert report.real_ratio == 0.5

    def test_symbol_logged_in_report(self):
        _, report = validate_candles([_candle()], symbol="ETH/USDT")
        assert report.total == 1


# ── ValidationReport ─────────────────────────────────────────────────────────


class TestValidationReport:
    def test_real_ratio_zero_valid(self):
        report = ValidationReport(
            total=0, valid=0, dropped=0, reasons={}, source_counts={}
        )
        assert report.real_ratio == 0.0

    def test_real_ratio_no_live(self):
        report = ValidationReport(
            total=2, valid=2, dropped=0, reasons={}, source_counts={"synthetic": 2}
        )
        assert report.real_ratio == 0.0

    def test_real_ratio_all_live(self):
        report = ValidationReport(
            total=3, valid=3, dropped=0, reasons={}, source_counts={"ccxt_live": 3}
        )
        assert report.real_ratio == 1.0


# ── is_series_fresh ───────────────────────────────────────────────────────────


class TestIsSeriesFresh:
    def test_fresh_series(self):
        candles = [_candle(timestamp=_fresh_ts(age_seconds=30))]
        assert is_series_fresh(candles, max_age_seconds=3600.0) is True

    def test_stale_series(self):
        candles = [_candle(timestamp=_fresh_ts(age_seconds=7200))]
        assert is_series_fresh(candles, max_age_seconds=3600.0) is False

    def test_empty_series_is_not_fresh(self):
        assert is_series_fresh([], max_age_seconds=3600.0) is False

    def test_exactly_at_boundary(self):
        # Légèrement en-dessous du seuil = frais
        candles = [_candle(timestamp=_fresh_ts(age_seconds=3590))]
        assert is_series_fresh(candles, max_age_seconds=3600.0) is True

    def test_uses_last_candle_only(self):
        # Seule la dernière bougie compte
        old = _candle(timestamp=_fresh_ts(age_seconds=7200))
        fresh = _candle(timestamp=_fresh_ts(age_seconds=10))
        assert is_series_fresh([old, fresh], max_age_seconds=3600.0) is True
