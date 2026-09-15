"""Scénario 6: Cache corruption - vérifier refus des NaN."""
import pytest, math

def test_nan_ohlcv_rejected():
    """OHLCV corrompu avec NaN → refus."""
    ohlcv = [{"open": 100, "high": 101, "low": 99, "close": 100.5},
             {"open": 101, "high": 102, "low": math.nan, "close": 101}]
    assert ohlcv_validator.validate(ohlcv) is False
