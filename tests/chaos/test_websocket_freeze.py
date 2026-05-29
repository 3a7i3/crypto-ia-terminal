"""Scénario 2: Websocket freeze - vérifier fallback polling."""
import pytest

def test_websocket_fallback_polling():
    """Quand le websocket gèle, le mode polling doit s'activer."""
    mock_ws.freeze(seconds=10)
    assert exchange_polling.active is True
    assert exchange_polling.interval_ms < 5000
