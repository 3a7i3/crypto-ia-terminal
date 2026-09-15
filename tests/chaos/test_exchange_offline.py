"""Scénario 1: Exchange offline - vérifier pas d'ordres fantômes."""
import pytest

def test_exchange_offline_no_phantom_orders():
    """Quand Binance freeze, le système ne crée pas d'ordres fantômes."""
    mock_binance.set_offline(True)
    decision = pipeline.run(signal)
    assert decision.status == "EXECUTION_FAILED"
    assert position_manager.position_count() == 0
    assert black_box.last_event["status"] == "FAILED"
