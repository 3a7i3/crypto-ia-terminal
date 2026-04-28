"""Rapport UI Selenium sur les panels locaux — exécuter: python panel_selenium_test.py"""

from __future__ import annotations

import os
import time
from datetime import datetime

PANELS = [
    ("🛡️ Supervision & Auto-Heal", 5011),
    ("🩺 BotDoctor Dashboard", 5012),
    ("🌐 Evolution Multi-Monde", 5013),
    ("🌐 3D Evolution Viewer", 5014),
    ("📊 Quant V16 Panel", 5015),
    ("📈 Quant Terminal V12", 5016),
    ("🧠 R&D Feedback Dashboard", 5017),
]


def _safe_screenshot_basename(label: str) -> str:
    for ch in ("🛡️", "🩺", "🌐", "📊", "📈", "🧠", " "):
        label = label.replace(ch, "_")
    return f"screenshot_{label.strip('_')}.png"


def main() -> None:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By

    results: list[tuple[str, str, str, str, str]] = []
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    for label, port in PANELS:
        url = f"http://localhost:{port}/"
        status = "❌"
        detail = ""
        screenshot_path = _safe_screenshot_basename(label)
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(10)
            driver.get(url)
            time.sleep(2)
            if driver.title and "streamlit" in driver.title.lower():
                status = "✅"
                detail = driver.title
            else:
                status = "❌"
                detail = f"Titre inattendu : {driver.title}"
            try:
                btns = driver.find_elements(By.TAG_NAME, "button")
                if btns:
                    detail += f" | {len(btns)} boutons détectés."
                else:
                    detail += " | Aucun bouton détecté."
            except Exception:
                detail += " | Erreur détection boutons."
            driver.save_screenshot(screenshot_path)
            detail += f" | Screenshot: {screenshot_path}"
            driver.quit()
        except Exception as e:
            detail = str(e)
        results.append((label, url, status, detail, screenshot_path))

    html_lines = [
        "<html><head><meta charset='utf-8'><title>Rapport UI Selenium "
        f"{datetime.now()}</title></head><body>",
        f"<h1>Rapport UI Selenium - {datetime.now()}</h1>",
        "<table border='1' cellpadding='6'><tr><th>Panneau</th><th>URL</th>"
        "<th>Statut</th><th>Détail</th><th>Screenshot</th></tr>",
    ]
    for label, url, status, detail, screenshot_path in results:
        img_tag = (
            f'<img src="{screenshot_path}" width="200">'
            if os.path.exists(screenshot_path)
            else ""
        )
        html_lines.append(
            f"<tr><td>{label}</td><td>{url}</td><td>{status}</td>"
            f"<td>{detail}</td><td>{img_tag}</td></tr>"
        )
    html_lines.append("</table></body></html>")

    with open("panel_selenium_report.html", "w", encoding="utf-8") as f:
        f.write("\n".join(html_lines))

    print("Rapport UI Selenium enrichi généré : panel_selenium_report.html")


if __name__ == "__main__":
    main()
