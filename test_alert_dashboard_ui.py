import os
import sys

import pytest
import streamlit as st

# Ensure workspace root is in sys.path for dashboard import
WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

try:
    from dashboard.alert_dashboard import render
except ModuleNotFoundError:
    from alert_dashboard import render


def test_alert_dashboard_ui():
    # Ce test vérifie que le dashboard s'affiche sans erreur (Streamlit UI, non testable headless)
    try:
        render()
    except Exception as e:
        pytest.fail(f"Erreur lors de l'affichage du dashboard : {e}")
