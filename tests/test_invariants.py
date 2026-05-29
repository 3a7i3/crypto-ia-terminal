"""Tests des 12 invariants système."""

import pytest
from datetime import datetime, timedelta


class TestInvariants:

    def test_invariant_no_duplicate_position(self):
        """Invariant 1: Pas de double position ouverte."""
        engine = ExecutionEngine()
        engine.open_position("BTCUSDT", 0.1)
        with pytest.raises(DuplicatePositionError):
            engine.open_position("BTCUSDT", 0.1)

    def test_invariant_stop_required(self):
        """Invariant 2: Position sans stop = REJECT."""
        with pytest.raises(MissingStopError):
            ExecutionEngine().open_position("BTCUSDT", 0.1, stop_loss=None)

    def test_invariant_approval_required(self):
        """Invariant 3: Execution sans approval = REJECT."""
        packet = DecisionPacket(symbol="BTCUSDT", approved_by=None)
        assert GlobalRiskGate().evaluate(packet) == "REJECTED"

    def test_invariant_drawdown_limit(self):
        """Invariant 4: Drawdown > limite = FREEZE."""
        gate = GlobalRiskGate(drawdown_limit=0.05)
        assert gate.evaluate_drawdown(0.06) is False

    def test_invariant_signal_timestamp(self):
        """Invariant 5: Signal sans timestamp = DROP."""
        signal = Signal(symbol="BTCUSDT", timestamp=None)
        assert LiveSignalEngine().validate(signal) == "DROP"

    def test_invariant_expired_order(self):
        """Invariant 6: Ordre expiré jamais exécuté."""
        engine = ExecutionEngine()
        order = Order(symbol="BTCUSDT", created_at=datetime.now() - timedelta(minutes=30))
        assert engine.check_ttl(order) is False

    def test_invariant_positive_size(self):
        """Invariant 7: Position size <= 0 = REJECT."""
        with pytest.raises(InvalidSizeError):
            OrderSizer().calculate_size(signal, portfolio, size=-1)

    def test_invariant_trace_id(self):
        """Invariant 8: Packet sans trace_id = REJECT."""
        packet = DecisionPacket(symbol="BTCUSDT")
        assert packet.trace_id is not None

    def test_invariant_cache_ttl(self):
        """Invariant 9: Cache stale > TTL = REFRESH."""
        cache = RuntimeCache(ttl=60)
        cache.set("regime", "TRENDING", timestamp=datetime.now() - timedelta(seconds=120))
        assert cache.is_stale("regime") is True

    def test_invariant_halted_state(self):
        """Invariant 10: Ordre après HALTED = IMPOSSIBLE."""
        state = RuntimeStateMachine()
        state.transition_to("HALTED")
        assert state.can_execute() is False

    def test_invariant_exchange_reconciliation(self):
        """Invariant 11: Position mismatch = ALERT."""
        reconciler = PositionReconciler()
        result = reconciler.compare(local={"BTCUSDT": 0.1}, exchange={"BTCUSDT": 0.05})
        assert result.mismatch is True

    def test_invariant_decision_authority(self):
        """Invariant 12: Décision sans FINAL AUTHORITY."""
        pipeline = DecisionPipeline()
        packet = DecisionPacket(symbol="BTCUSDT", final_authority=None)
        assert pipeline.validate_authority(packet) is False
