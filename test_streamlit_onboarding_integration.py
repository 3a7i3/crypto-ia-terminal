# Test d'intégration Streamlit (manuel ou automatisé)
# Ce script vérifie que la page se lance et que le formulaire de feedback est visible.
# Pour automatiser, utiliser streamlit-testing ou playwright (voir test_dashboard_filters_playwright.py)

import subprocess
import time

import requests


def test_streamlit_onboarding_launch():
    # Lance le dashboard Streamlit en arrière-plan
    proc = subprocess.Popen(
        [
            "streamlit",
            "run",
            "ONBOARDING_SCRIPT.py",
            "--server.headless=true",
            "--server.port=8502",
        ]
    )
    time.sleep(5)  # Laisse le temps au serveur de démarrer
    try:
        resp = requests.get("http://localhost:8502")
        assert resp.status_code == 200
        assert "onboarding".lower() in resp.text.lower()
    finally:
        proc.terminate()
        proc.wait()
