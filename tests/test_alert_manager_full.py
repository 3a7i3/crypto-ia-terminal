"""
Tests couvrant les branches manquantes de AlertManager (83% → ~98%).
Cibles: raise_alert sans autoheal, get_alerts avec filtre, run_autoheal heal_func=None.
"""

import json

import pytest

from supervision.alert_manager import Alert, AlertManager


@pytest.fixture()
def manager(tmp_path):
    return AlertManager(audit_file=str(tmp_path / "audit.jsonl"))


def make_alert(severity="warning", module="mod", type_="cpu"):
    return Alert(type_=type_, severity=severity, module=module, message="msg")


class TestRaiseAlert:
    def test_alert_appended_to_memory(self, manager):
        a = make_alert()
        manager.raise_alert(a)
        assert len(manager.alerts) == 1

    def test_alert_written_to_file(self, manager, tmp_path):
        a = make_alert(type_="disk")
        manager.raise_alert(a)
        lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["type"] == "disk"

    def test_no_autoheal_for_non_critical(self, manager):
        healed = []
        manager.register_autoheal("mod", lambda a: healed.append(True))
        manager.raise_alert(make_alert(severity="warning"))
        assert healed == []

    def test_no_autoheal_when_module_not_registered(self, manager):
        healed = []
        manager.register_autoheal("other_module", lambda a: healed.append(True))
        manager.raise_alert(make_alert(severity="critical", module="mod"))
        assert healed == []

    def test_autoheal_triggered_for_critical_registered_module(self, manager):
        healed = []
        manager.register_autoheal("mod", lambda a: healed.append(True) or "ok")
        manager.raise_alert(make_alert(severity="critical"))
        assert healed == [True]

    def test_multiple_alerts_all_written(self, manager, tmp_path):
        manager.raise_alert(make_alert(type_="cpu"))
        manager.raise_alert(make_alert(type_="ram"))
        lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        types = [json.loads(l)["type"] for l in lines]
        assert "cpu" in types and "ram" in types


class TestGetAlerts:
    def test_no_filter_returns_all(self, manager):
        manager.raise_alert(make_alert(severity="info"))
        manager.raise_alert(make_alert(severity="critical"))
        assert len(manager.get_alerts()) == 2

    def test_filter_func_applied(self, manager):
        manager.raise_alert(make_alert(severity="info"))
        manager.raise_alert(make_alert(severity="critical"))
        critical = manager.get_alerts(filter_func=lambda a: a.severity == "critical")
        assert len(critical) == 1
        assert critical[0].severity == "critical"

    def test_filter_returns_empty_when_no_match(self, manager):
        manager.raise_alert(make_alert(severity="info"))
        result = manager.get_alerts(filter_func=lambda a: a.severity == "critical")
        assert result == []


class TestRunAutoheal:
    def test_returns_none_when_no_heal_func(self, manager):
        alert = make_alert(severity="critical")
        result = manager.run_autoheal(alert)
        assert result is None

    def test_returns_heal_result(self, manager):
        manager.register_autoheal("mod", lambda a: {"fixed": True})
        alert = make_alert(severity="critical")
        result = manager.run_autoheal(alert)
        assert result == {"fixed": True}

    def test_correction_written_to_audit(self, manager, tmp_path):
        manager.register_autoheal("mod", lambda a: "healed")
        manager.run_autoheal(make_alert(severity="critical"))
        lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        assert any(json.loads(l).get("correction") for l in lines)


class TestAlertToDict:
    def test_to_dict_has_all_fields(self):
        a = Alert(
            type_="cpu",
            severity="critical",
            module="m",
            message="msg",
            context={"k": 1},
        )
        d = a.to_dict()
        assert set(d) == {
            "type",
            "severity",
            "module",
            "message",
            "context",
            "timestamp",
        }

    def test_context_defaults_to_empty_dict(self):
        a = Alert(type_="cpu", severity="info", module="m", message="msg")
        assert a.to_dict()["context"] == {}
