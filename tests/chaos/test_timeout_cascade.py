"""Scénario 7: Timeout cascade - vérifier résilience."""
import pytest

def test_timeout_cascade_safe_mode():
    """3 modules timeout → SAFE_MODE."""
    with mock_timeout(["RiskEngine", "SignalEngine", "ExecutionEngine"]):
        result = pipeline.run(signal)
        assert runtime_state.current_mode == "SAFE_MODE"
        assert black_box.last_event["trigger"] == "TIMEOUT_CASCADE"
