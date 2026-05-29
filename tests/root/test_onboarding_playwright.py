# Test Playwright pour le dashboard d'onboarding Streamlit
# Nécessite: pip install playwright pytest-playwright
# Lancer: pytest test_onboarding_playwright.py --headed

import subprocess
import time

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="module", autouse=True)
def launch_streamlit():
    proc = subprocess.Popen(
        [
            "streamlit",
            "run",
            "ONBOARDING_SCRIPT.py",
            "--server.headless=true",
            "--server.port=8503",
        ]
    )
    time.sleep(5)
    yield
    proc.terminate()
    proc.wait()


def test_onboarding_dashboard_visible():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://localhost:8503")
        # Vérifie la présence du titre ou du bouton feedback
        assert (
            page.locator("text=Bienvenue dans l'onboarding utilisateur").is_visible()
            or page.locator("text=Donnez votre feedback").is_visible()
        )
        browser.close()
