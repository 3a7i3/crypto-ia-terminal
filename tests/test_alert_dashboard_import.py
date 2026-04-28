def test_alert_dashboard_import():
    """Test minimal: vérifie que le module s'importe sans erreur fatale."""
    import importlib
    import os
    import pathlib
    import sys

    # Ajoute le workspace racine au PYTHONPATH si nécessaire
    ws_root = str(pathlib.Path(__file__).parent.parent.resolve())
    if ws_root not in sys.path:
        sys.path.insert(0, ws_root)
    try:
        importlib.import_module("dashboard.alert_dashboard")
    except SystemExit:
        # Attendu si streamlit/pandas manquant
        pass
    except Exception as e:
        assert False, f"Erreur d'import: {e}"
