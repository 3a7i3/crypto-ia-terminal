# Test Playwright : export CSV du dashboard d'alertes
# Nécessite : pip install playwright pytest
# Avant le premier lancement : playwright install

import os
import time

import pytest
from playwright.sync_api import sync_playwright

DASHBOARD_URL = "http://localhost:8502"  # Adapter le port si besoin


@pytest.mark.skipif(os.getenv("CI") == "true", reason="Test UI désactivé en CI")
def test_export_csv():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(DASHBOARD_URL)
        # Attendre que le dashboard charge
        page.wait_for_selector("text=Export des alertes filtrées", timeout=10000)
        # Cliquer sur le bouton d'export CSV
        with page.expect_download() as download_info:
            page.click("text=Export CSV")
        download = download_info.value
        # Sauver le fichier téléchargé
        csv_path = download.path()
        assert csv_path and os.path.exists(
            csv_path
        ), "Le fichier CSV n'a pas été téléchargé."
        # Vérifier le contenu du CSV
        with open(csv_path, encoding="utf-8") as f:
            content = f.read()
            assert (
                "Alerte" in content or "Alert" in content
            ), "Le CSV ne contient pas la colonne attendue."
        browser.close()


if __name__ == "__main__":
    test_export_csv()
    print("Test Playwright export CSV : OK")
