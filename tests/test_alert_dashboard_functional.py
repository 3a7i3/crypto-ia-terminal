import json
import pathlib
import sys

import pandas as pd

# Ajoute le workspace racine au PYTHONPATH si nécessaire
ws_root = str(pathlib.Path(__file__).parent.parent.resolve())
if ws_root not in sys.path:
    sys.path.insert(0, ws_root)

# Utilitaire pour créer un fichier d'audit temporaire


def make_audit_file(alerts, path):
    with open(path, "w", encoding="utf-8") as f:
        for alert in alerts:
            f.write(json.dumps(alert) + "\n")


def test_filtrage_module(tmp_path):
    """Teste le filtrage par module dans le dashboard."""
    audit_file = tmp_path / "alerts_audit.jsonl"
    alerts = [
        {
            "alert": {
                "type": "cpu",
                "severity": "critical",
                "module": "monitoring",
                "message": "CPU high",
            },
            "timestamp": "2024-01-01T10:00:00",
        },
        {
            "alert": {
                "type": "ram",
                "severity": "warning",
                "module": "monitoring",
                "message": "RAM high",
            },
            "timestamp": "2024-01-01T11:00:00",
        },
        {
            "alert": {
                "type": "disk",
                "severity": "info",
                "module": "storage",
                "message": "Disk ok",
            },
            "timestamp": "2024-01-01T12:00:00",
        },
    ]
    make_audit_file(alerts, audit_file)
    # Patch le Path utilisé dans le dashboard pour pointer sur ce fichier
    import dashboard.alert_dashboard as dash

    dash.AUDIT_FILE = audit_file
    data = dash.load_audit()
    df = pd.DataFrame(data)
    # Vérifie que le filtrage par module fonctionne
    modules = set(x["alert"]["module"] for x in data)
    assert "monitoring" in modules and "storage" in modules
    filtered = df[df["alert"].apply(lambda x: x["module"] == "monitoring")]
    assert len(filtered) == 2
    filtered = df[df["alert"].apply(lambda x: x["module"] == "storage")]
    assert len(filtered) == 1


def test_export_csv(tmp_path):
    """Teste l'export CSV des alertes filtrées."""
    audit_file = tmp_path / "alerts_audit.jsonl"
    alerts = [
        {
            "alert": {
                "type": "cpu",
                "severity": "critical",
                "module": "monitoring",
                "message": "CPU high",
            },
            "timestamp": "2024-01-01T10:00:00",
        },
        {
            "alert": {
                "type": "ram",
                "severity": "warning",
                "module": "monitoring",
                "message": "RAM high",
            },
            "timestamp": "2024-01-01T11:00:00",
        },
    ]
    make_audit_file(alerts, audit_file)
    import dashboard.alert_dashboard as dash

    dash.AUDIT_FILE = audit_file
    data = dash.load_audit()
    df = pd.DataFrame(data)
    csv = df.to_csv(index=False)
    assert "cpu" in csv and "ram" in csv
    assert "monitoring" in csv


def test_filtrage_severity(tmp_path):
    """Test filtrage par gravité."""
    audit_file = tmp_path / "alerts_audit.jsonl"
    alerts = [
        {
            "alert": {
                "type": "cpu",
                "severity": "critical",
                "module": "monitoring",
                "message": "CPU high",
            },
            "timestamp": "2024-01-01T10:00:00",
        },
        {
            "alert": {
                "type": "ram",
                "severity": "warning",
                "module": "monitoring",
                "message": "RAM high",
            },
            "timestamp": "2024-01-01T11:00:00",
        },
    ]
    make_audit_file(alerts, audit_file)
    import dashboard.alert_dashboard as dash

    dash.AUDIT_FILE = audit_file
    data = dash.load_audit()
    df = pd.DataFrame(data)
    filtered = df[df["alert"].apply(lambda x: x["severity"] == "critical")]
    assert len(filtered) == 1
    assert filtered.iloc[0]["alert"]["type"] == "cpu"
    filtered = df[df["alert"].apply(lambda x: x["severity"] == "warning")]
    assert len(filtered) == 1
    assert filtered.iloc[0]["alert"]["type"] == "ram"
