from __future__ import annotations

from core.decision_packet import DecisionPacket, ReasoningCategory


def test_confidence_tracks_raw_and_adjusted_separately() -> None:
    packet = DecisionPacket(confidence=72.0)

    assert packet.confidence_raw == 72.0
    assert packet.adjusted_confidence == 72.0

    packet.add_reasoning(
        actor="test",
        message="positive update",
        confidence_impact=5.0,
        category=ReasoningCategory.SIGNAL_QUALITY,
    )

    assert packet.confidence_raw == 72.0
    assert packet.adjusted_confidence == 77.0
    assert packet.confidence == 77.0


def test_from_dict_backfills_confidence_channels_when_missing() -> None:
    packet = DecisionPacket(confidence=40.0)
    data = packet.to_dict()
    data.pop("confidence_raw", None)
    data.pop("adjusted_confidence", None)

    restored = DecisionPacket.from_dict(data)

    assert restored.confidence_raw == 40.0
    assert restored.adjusted_confidence == 40.0
