import sys
import types

import pytest


# Simule un notifier (Slack ou Telegram)
class DummyNotifier:
    def __init__(self):
        self.last_msg = None

    def notify(self, msg):
        self.last_msg = msg


# Simule un BotDoctor minimal
class MiniBotDoctor:
    def __init__(self, notifier):
        self.notifier = notifier

    def alert_if_critical(self, health_score, msg):
        if health_score < 50:
            self.notifier.notify(f"ALERTE CRITIQUE: {msg}")
            return True
        return False


def test_alert_on_critical():
    notifier = DummyNotifier()
    doctor = MiniBotDoctor(notifier)
    triggered = doctor.alert_if_critical(40, "Drawdown excessif")
    assert triggered
    assert "ALERTE CRITIQUE" in notifier.last_msg


def test_no_alert_on_healthy():
    notifier = DummyNotifier()
    doctor = MiniBotDoctor(notifier)
    triggered = doctor.alert_if_critical(80, "Tout va bien")
    assert not triggered
    assert notifier.last_msg is None
