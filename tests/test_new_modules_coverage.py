"""
Tests de couverture pour les modules supervision créés lors de l'audit.
Couvre: bot_doctor, custom_module, notifications (slack, telegram, multi).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from supervision.custom_module import CustomTradingModule

# ── custom_module ──────────────────────────────────────────────────────────────


def test_custom_module_healthy():
    m = CustomTradingModule("Bot1", is_healthy=True)
    assert m.name == "Bot1"
    assert m.is_healthy is True
    assert m.health_check() is True


def test_custom_module_unhealthy():
    m = CustomTradingModule("Bot2", is_healthy=False)
    assert m.is_healthy is False
    assert m.health_check() is False


def test_custom_module_default_healthy():
    m = CustomTradingModule("Bot3")
    assert m.is_healthy is True


# ── bot_doctor ─────────────────────────────────────────────────────────────────

from supervision.bot_doctor import BotDoctor, ModuleStatus


def test_module_status_to_dict():
    s = ModuleStatus("TestBot", True)
    d = s.to_dict()
    assert d["name"] == "TestBot"
    assert d["is_healthy"] is True
    assert d["error"] is None
    assert "last_checked" in d


def test_bot_doctor_all_healthy():
    modules = [CustomTradingModule("A", True), CustomTradingModule("B", True)]
    doctor = BotDoctor(modules)
    statuses = doctor.run()
    assert len(statuses) == 2
    assert all(s.is_healthy for s in statuses)


def test_bot_doctor_detects_unhealthy():
    modules = [CustomTradingModule("Good", True), CustomTradingModule("Bad", False)]
    doctor = BotDoctor(modules)
    statuses = doctor.run()
    assert statuses[0].is_healthy is True
    assert statuses[1].is_healthy is False
    assert "Bad" in statuses[1].error


def test_bot_doctor_notifies_on_unhealthy():
    modules = [CustomTradingModule("Broken", False)]
    notifier = MagicMock()
    doctor = BotDoctor(modules, notifier=notifier)
    doctor.run()
    notifier.notify.assert_called_once()
    assert "Broken" in notifier.notify.call_args[0][0]


def test_bot_doctor_no_notifier_does_not_crash():
    modules = [CustomTradingModule("Broken", False)]
    doctor = BotDoctor(modules, notifier=None)
    statuses = doctor.run()
    assert len(statuses) == 1


def test_bot_doctor_get_report():
    modules = [CustomTradingModule("X", True)]
    doctor = BotDoctor(modules)
    doctor.run()
    report = doctor.get_report()
    assert isinstance(report, list)
    assert report[0]["name"] == "X"


def test_bot_doctor_notifier_error_does_not_crash():
    modules = [CustomTradingModule("Broken", False)]
    bad_notifier = MagicMock()
    bad_notifier.notify.side_effect = RuntimeError("réseau mort")
    doctor = BotDoctor(modules, notifier=bad_notifier)
    statuses = doctor.run()  # ne doit pas lever
    assert statuses[0].is_healthy is False


def test_bot_doctor_module_raises_during_check():
    class BrokenModule:
        name = "Crasher"

        @property
        def is_healthy(self):
            raise ValueError("boom")

    doctor = BotDoctor([BrokenModule()])
    statuses = doctor.run()
    assert statuses[0].is_healthy is False
    assert "boom" in statuses[0].error


# ── notifications ──────────────────────────────────────────────────────────────

from supervision.notifications.multi_notifier import MultiNotifier


def test_multi_notifier_calls_all():
    n1, n2 = MagicMock(), MagicMock()
    multi = MultiNotifier([n1, n2])
    multi.notify("test message")
    n1.notify.assert_called_once_with("test message")
    n2.notify.assert_called_once_with("test message")


def test_multi_notifier_continues_on_error():
    n1 = MagicMock()
    n1.notify.side_effect = Exception("erreur réseau")
    n2 = MagicMock()
    multi = MultiNotifier([n1, n2])
    multi.notify("msg")  # ne doit pas lever
    n2.notify.assert_called_once_with("msg")


def test_multi_notifier_empty_list():
    multi = MultiNotifier([])
    multi.notify("rien")  # ne doit pas lever


from supervision.notifications.slack_notifier import SlackNotifier


def test_slack_notifier_success():
    notifier = SlackNotifier("https://hooks.slack.com/fake")
    mock_resp = MagicMock()
    mock_resp.status = 200
    with patch(
        "urllib.request.urlopen",
        return_value=__import__("contextlib").nullcontext(mock_resp),
    ):
        notifier.notify("test slack")
    # La fonction doit retourner True ou False sans lever


def test_slack_notifier_network_error():
    notifier = SlackNotifier("https://invalid.url")
    with patch("urllib.request.urlopen", side_effect=Exception("réseau mort")):
        result = notifier.notify("test")
    assert result is False


from supervision.notifications.telegram_notifier import TelegramNotifier


def test_telegram_notifier_network_error():
    notifier = TelegramNotifier("FAKE_TOKEN", "FAKE_CHAT")
    with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
        result = notifier.notify("test")
    assert result is False


# ── feature_cache ──────────────────────────────────────────────────────────────

from quant_hedge_ai.strategy_lab.feature_cache import (clear_cache,
                                                       compute_feature)


def test_feature_cache_mean():
    v = compute_feature("mean", (1.0, 2.0, 3.0))
    assert v == pytest.approx(2.0)


def test_feature_cache_rolling_volatility():
    values = tuple([1.0 + 0.01 * i for i in range(25)])
    v = compute_feature("rolling_volatility", values)
    assert isinstance(v, float)
    assert v >= 0.0


def test_feature_cache_correlation_perfect():
    xs = (1.0, 2.0, 3.0, 4.0, 5.0)
    ys = (2.0, 4.0, 6.0, 8.0, 10.0)
    v = compute_feature("correlation", xs, ys)
    assert v == pytest.approx(1.0, abs=1e-6)


def test_feature_cache_correlation_empty():
    v = compute_feature("correlation", (), ())
    assert v == 0.0


def test_feature_cache_mean_empty():
    v = compute_feature("mean", ())
    assert v == 0.0


def test_feature_cache_unknown_raises():
    with pytest.raises(ValueError, match="Feature inconnue"):
        compute_feature("unknown_feature_xyz")


def test_feature_cache_lru_works():
    clear_cache()
    compute_feature("mean", (1.0, 2.0))
    info = compute_feature.cache_info()
    assert info.currsize >= 1


def test_feature_cache_clear():
    compute_feature("mean", (5.0, 6.0))
    clear_cache()
    info = compute_feature.cache_info()
    assert info.currsize == 0


# ── alert_dashboard ────────────────────────────────────────────────────────────

import json

from dashboard.alert_dashboard import (filter_by_module,
                                       filter_by_severity)


def test_load_audit_missing_file(tmp_path, monkeypatch):
    import dashboard.alert_dashboard as mod

    monkeypatch.setattr(mod, "AUDIT_FILE", tmp_path / "nonexistent.jsonl")
    assert mod.load_audit() == []


def test_load_audit_valid(tmp_path, monkeypatch):
    import dashboard.alert_dashboard as mod

    p = tmp_path / "audit.jsonl"
    p.write_text(
        json.dumps({"alert": {"module": "A", "severity": "info"}, "ts": "now"}) + "\n"
    )
    monkeypatch.setattr(mod, "AUDIT_FILE", p)
    entries = mod.load_audit()
    assert len(entries) == 1
    assert entries[0]["alert"]["module"] == "A"


def test_load_audit_skips_corrupt_lines(tmp_path, monkeypatch):
    import dashboard.alert_dashboard as mod

    p = tmp_path / "audit.jsonl"
    p.write_text("not json\n" + json.dumps({"alert": {"module": "B"}}) + "\n")
    monkeypatch.setattr(mod, "AUDIT_FILE", p)
    entries = mod.load_audit()
    assert len(entries) == 1


def test_filter_by_module():
    entries = [
        {"alert": {"module": "trading", "severity": "info"}},
        {"alert": {"module": "risk", "severity": "warning"}},
        {"alert": {"module": "trading", "severity": "error"}},
    ]
    result = filter_by_module(entries, "trading")
    assert len(result) == 2


def test_filter_by_severity():
    entries = [
        {"alert": {"module": "A", "severity": "critical"}},
        {"alert": {"module": "B", "severity": "info"}},
    ]
    result = filter_by_severity(entries, "critical")
    assert len(result) == 1
    assert result[0]["alert"]["module"] == "A"


# ── core.quant.logging_alerts — chemins alert+notifier ────────────────────────

from core.quant.logging_alerts import log_and_alert as _log_and_alert


def test_log_and_alert_with_notifier():
    notifier = MagicMock()
    _log_and_alert("warning", "Alerte trading", alert=True, notifier=notifier)
    notifier.notify.assert_called_once()
    assert "WARNING" in notifier.notify.call_args[0][0]
    assert "Alerte trading" in notifier.notify.call_args[0][0]


def test_log_and_alert_notifier_error_caught():
    bad = MagicMock()
    bad.notify.side_effect = RuntimeError("notifier mort")
    _log_and_alert("error", "msg", alert=True, notifier=bad)  # ne doit pas lever


def test_log_and_alert_alert_false_notifier_not_called():
    notifier = MagicMock()
    _log_and_alert("info", "info silencieuse", alert=False, notifier=notifier)
    notifier.notify.assert_not_called()


def test_log_and_alert_unknown_level_defaults_info():
    _log_and_alert("superwarning", "msg inconnu")  # ne doit pas lever


# ── slack_notifier — statut non-200 ──────────────────────────────────────────


def test_slack_notifier_non_200():
    notifier = SlackNotifier("https://hooks.slack.com/fake")
    mock_resp = MagicMock()
    mock_resp.status = 400
    mock_resp.__enter__ = lambda s: mock_resp
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = notifier.notify("msg")
    assert result is False


# ── telegram_notifier — succès ────────────────────────────────────────────────


def test_telegram_notifier_success():
    from supervision.notifications.telegram_notifier import TelegramNotifier

    notifier = TelegramNotifier("TOKEN", "CHAT")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = lambda s: mock_resp
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = notifier.notify("hello")
    assert result is True
