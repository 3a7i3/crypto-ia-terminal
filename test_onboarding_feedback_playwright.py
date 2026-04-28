# Test Playwright : soumission de feedback sur ONBOARDING_SCRIPT.py
# Nécessite: pip install playwright pytest-playwright
# Lancer: pytest test_onboarding_feedback_playwright.py --headed

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
            "--server.port=8504",
        ]
    )
    time.sleep(5)
    yield
    proc.terminate()
    proc.wait()


def test_feedback_submission():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://localhost:8504")
        # Remplit le formulaire
        page.fill(
            'input[aria-label="Votre nom ou pseudo (optionnel)"]', "playwright-test"
        )
        page.fill(
            'textarea[aria-label="Commentaire ou suggestion"]',
            "Test feedback Playwright",
        )
        page.click("text=Envoyer le feedback")
        # Vérifie le message de succès
        assert page.locator("text=Merci pour votre feedback").is_visible()
        browser.close()
