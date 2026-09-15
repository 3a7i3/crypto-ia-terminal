"""Scénario 3: Partial fill - vérifier cohérence position."""
import pytest

def test_partial_fill_position_consistency():
    """50% de l'ordre exécuté → position doit être 50% de la taille."""
    mock_exchange.set_partial_fill(0.5)
    decision = pipeline.run(signal)
    assert position_manager.current_quantity == expected_size * 0.5
    assert black_box.last_event["fill_ratio"] == 0.5
