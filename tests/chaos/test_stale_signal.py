"""Scénario 5: Stale signal - vérifier EXPIRED."""
import pytest
from datetime import datetime, timedelta

def test_stale_signal_expired():
    """Signal avec TTL dépassé → EXPIRED."""
    signal = Signal(symbol="BTCUSDT", timestamp=datetime.now() - timedelta(minutes=30))
    result = pipeline.run(signal)
    assert result.status == "EXPIRED"
