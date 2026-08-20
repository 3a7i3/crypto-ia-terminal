"""
tests/test_telegram_failure_tracker.py

Preuve du fix « silence Telegram invisible » (incident 2026-08-12→20) :
un canal qui échoue en série doit devenir VISIBLE (escalade) au lieu de
rester silencieux. Horloge injectée → test déterministe du cooldown.
"""

from __future__ import annotations

import pytest

from src.telegram.failure_tracker import ChannelFailureTracker


class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_success_keeps_streak_at_zero():
    tr = ChannelFailureTracker(escalate_after=5)
    for _ in range(10):
        tr.record_success()
    assert tr.streak == 0


def test_escalates_after_threshold_exactly_once():
    clock = _FakeClock()
    tr = ChannelFailureTracker(escalate_after=5, cooldown_s=1800.0, clock=clock)

    verdicts = [tr.record_failure() for _ in range(5)]
    # Les 4 premiers échecs n'escaladent pas
    assert [v.should_escalate for v in verdicts[:4]] == [False, False, False, False]
    # Le 5e franchit le seuil
    assert verdicts[4].should_escalate is True
    assert verdicts[4].streak == 5


def test_no_reescalation_during_cooldown():
    clock = _FakeClock()
    tr = ChannelFailureTracker(escalate_after=3, cooldown_s=1800.0, clock=clock)

    for _ in range(3):
        tr.record_failure()  # 3e escalade
    # Nouveaux échecs pendant le cooldown → pas de ré-escalade
    clock.t = 1000.0  # < 1800
    assert tr.record_failure().should_escalate is False
    assert tr.record_failure().should_escalate is False


def test_reescalates_after_cooldown_elapsed():
    clock = _FakeClock()
    tr = ChannelFailureTracker(escalate_after=3, cooldown_s=1800.0, clock=clock)

    for _ in range(3):
        tr.record_failure()  # escalade à t=0
    clock.t = 1900.0  # > cooldown
    assert tr.record_failure().should_escalate is True


def test_success_resets_streak_and_requires_full_threshold_again():
    tr = ChannelFailureTracker(escalate_after=3)
    tr.record_failure()
    tr.record_failure()
    tr.record_success()  # canal revenu
    assert tr.streak == 0
    v1 = tr.record_failure()
    v2 = tr.record_failure()
    v3 = tr.record_failure()
    assert (v1.should_escalate, v2.should_escalate, v3.should_escalate) == (
        False,
        False,
        True,
    )


def test_invalid_threshold_rejected():
    with pytest.raises(ValueError):
        ChannelFailureTracker(escalate_after=0)
