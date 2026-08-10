
from supervision.alert_manager import Alert, AlertManager


def test_alert_and_autoheal(tmp_path):
    # Utilise un fichier temporaire pour l'audit
    audit_file = tmp_path / "alerts_audit.jsonl"
    manager = AlertManager(audit_file=str(audit_file))
    autoheal_called = {}

    def fake_autoheal(alert):
        autoheal_called["called"] = True
        autoheal_called["alert_type"] = alert.type
        return {"status": "healed"}

    manager.register_autoheal("monitoring", fake_autoheal)
    alert = Alert(
        type_="cpu_overload",
        severity="critical",
        module="monitoring",
        message="CPU > 90%",
        context={"cpu": 91},
    )
    manager.raise_alert(alert)
    # Vérifie que l'auto-heal a été appelé
    assert autoheal_called["called"] is True
    assert autoheal_called["alert_type"] == "cpu_overload"
    # Vérifie que l'audit trail contient l'alerte et la correction
    with open(audit_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert any('"type": "cpu_overload"' in line for line in lines)
    assert any('"correction": true' in line for line in lines)
