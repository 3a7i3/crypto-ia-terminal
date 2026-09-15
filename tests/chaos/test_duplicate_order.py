"""Scénario 4: Duplicate order - vérifier blocage."""
import pytest

def test_duplicate_order_blocked():
    """Deux fois le même order_id → le second doit être bloqué."""
    execution.execute(order)
    execution.execute(order)
    assert order_deduplicator.blocked_count == 1
    assert exchange.order_count() == 1
