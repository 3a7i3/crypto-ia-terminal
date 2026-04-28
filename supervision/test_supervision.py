"""Tests de couverture pour le module supervision."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from supervision.alert_manager import Alert, AlertManager
from supervision.notifications.multi_notifier import MultiNotifier
from supervision.notifications.telegram_notifier import TelegramNotifier

# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------


class TestAlert:
    def test_to_dict_keys(self):
        a = Alert(type_="test", severity="info", module="mod", message="msg")
        d = a.to_dict()
        assert set(d.keys()) == {
            "type",
            "severity",
            "module",
            "message",
            "context",
            "timestamp",
        }

    def test_to_dict_values(self):
        a = Alert(
            type_="t",
            severity="critical",
            module="m",
            message="hello",
            context={"k": 1},
        )
        d = a.to_dict()
        assert d["type"] == "t"
        assert d["severity"] == "critical"
        assert d["module"] == "m"
        assert d["message"] == "hello"
        assert d["context"] == {"k": 1}

    def test_default_context(self):
        a = Alert(type_="t", severity="info", module="m", message="x")
        assert a.context == {}

    def test_timestamp_is_string(self):
        a = Alert(type_="t", severity="info", module="m", message="x")
        assert isinstance(a.timestamp, str)
        assert len(a.timestamp) > 0


# ---------------------------------------------------------------------------
# AlertManager
# ---------------------------------------------------------------------------


class TestAlertManager:
    def test_raise_alert_appends(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        mgr = AlertManager(audit_file=str(audit))
        a = Alert(type_="t", severity="info", module="m", message="msg")
        mgr.raise_alert(a)
        assert len(mgr.alerts) == 1
        assert audit.exists()

    def test_raise_alert_writes_jsonl(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        mgr = AlertManager(audit_file=str(audit))
        a = Alert(type_="x", severity="warning", module="mod", message="test")
        mgr.raise_alert(a)
        lines = audit.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["type"] == "x"

    def test_get_alerts_no_filter(self, tmp_path):
        mgr = AlertManager(audit_file=str(tmp_path / "a.jsonl"))
        mgr.raise_alert(Alert(type_="t1", severity="info", module="m", message="a"))
        mgr.raise_alert(Alert(type_="t2", severity="warning", module="m", message="b"))
        assert len(mgr.get_alerts()) == 2

    def test_get_alerts_with_filter(self, tmp_path):
        mgr = AlertManager(audit_file=str(tmp_path / "a.jsonl"))
        mgr.raise_alert(Alert(type_="t1", severity="info", module="m", message="a"))
        mgr.raise_alert(Alert(type_="t2", severity="critical", module="m", message="b"))
        critical = mgr.get_alerts(lambda a: a.severity == "critical")
        assert len(critical) == 1
        assert critical[0].type == "t2"

    def test_register_and_run_autoheal(self, tmp_path):
        mgr = AlertManager(audit_file=str(tmp_path / "a.jsonl"))
        healed = []

        def heal(alert):
            healed.append(alert.module)
            return {"fixed": True}

        mgr.register_autoheal("mod", heal)
        a = Alert(type_="t", severity="critical", module="mod", message="boom")
        mgr.raise_alert(a)
        assert healed == ["mod"]

    def test_autoheal_not_triggered_for_non_critical(self, tmp_path):
        mgr = AlertManager(audit_file=str(tmp_path / "a.jsonl"))
        healed = []
        mgr.register_autoheal("mod", lambda a: healed.append(1))
        a = Alert(type_="t", severity="warning", module="mod", message="ok")
        mgr.raise_alert(a)
        assert healed == []

    def test_run_autoheal_no_handler(self, tmp_path):
        mgr = AlertManager(audit_file=str(tmp_path / "a.jsonl"))
        a = Alert(type_="t", severity="critical", module="unknown", message="x")
        result = mgr.run_autoheal(a)
        assert result is None

    def test_autoheal_result_appended_to_audit(self, tmp_path):
        audit = tmp_path / "a.jsonl"
        mgr = AlertManager(audit_file=str(audit))
        mgr.register_autoheal("m", lambda a: {"ok": True})
        a = Alert(type_="t", severity="critical", module="m", message="x")
        mgr.raise_alert(a)
        lines = audit.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        correction = json.loads(lines[1])
        assert correction["correction"] is True


# ---------------------------------------------------------------------------
# MultiNotifier
# ---------------------------------------------------------------------------


class TestMultiNotifier:
    def test_notify_calls_all(self):
        n1, n2 = MagicMock(), MagicMock()
        mn = MultiNotifier([n1, n2])
        mn.notify("hello")
        n1.notify.assert_called_once_with("hello")
        n2.notify.assert_called_once_with("hello")

    def test_notify_continues_on_error(self):
        n1 = MagicMock()
        n1.notify.side_effect = RuntimeError("boom")
        n2 = MagicMock()
        mn = MultiNotifier([n1, n2])
        mn.notify("msg")
        n2.notify.assert_called_once_with("msg")

    def test_empty_notifiers(self):
        mn = MultiNotifier([])
        mn.notify("x")

    def test_notify_with_empty_message(self):
        n = MagicMock()
        mn = MultiNotifier([n])
        mn.notify("")
        n.notify.assert_called_once_with("")


# ---------------------------------------------------------------------------
# TelegramNotifier
# ---------------------------------------------------------------------------


class TestTelegramNotifier:
    def test_notify_success(self):
        tn = TelegramNotifier(bot_token="TOKEN", chat_id="123")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = tn.notify("test message")
        assert result is True

    def test_notify_failure_returns_false(self):
        tn = TelegramNotifier(bot_token="BAD", chat_id="0")
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            result = tn.notify("test")
        assert result is False

    def test_notify_builds_correct_url(self):
        tn = TelegramNotifier(bot_token="MYTOKEN", chat_id="MYCHAT")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            tn.notify("hello")
            req = mock_open.call_args[0][0]
            assert "MYTOKEN" in req.full_url
            assert "sendMessage" in req.full_url
