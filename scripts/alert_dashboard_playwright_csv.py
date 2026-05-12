from __future__ import annotations

import os


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        print(f"Dépendance manquante pour ce script: {exc}")
        print("Installez-la avec: pip install playwright ; playwright install")
        return 1

    dashboard_url = "http://localhost:8502"
    if os.getenv("CI") == "true":
        print("Test UI désactivé en CI")
        return 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(dashboard_url)
        page.wait_for_selector("text=Export des alertes filtrées", timeout=10000)
        with page.expect_download() as download_info:
            page.click("text=Export CSV")
        download = download_info.value
        csv_path = download.path()
        if not (csv_path and os.path.exists(csv_path)):
            print("Le fichier CSV n'a pas été téléchargé.")
            browser.close()
            return 1
        with open(csv_path, encoding="utf-8") as handle:
            content = handle.read()
            if "Alerte" not in content and "Alert" not in content:
                print("Le CSV ne contient pas la colonne attendue.")
                browser.close()
                return 1
        browser.close()
    print("Test Playwright export CSV : OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
