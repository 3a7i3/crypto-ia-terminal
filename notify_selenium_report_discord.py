import os
from datetime import datetime

import requests

# Discord webhook URL (à configurer)
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")

REPORT_FILE = "panel_selenium_report.html"

if not DISCORD_WEBHOOK:
    print("[ERREUR] Variable d'environnement DISCORD_WEBHOOK_URL non définie.")
    exit(1)

with open(REPORT_FILE, "r", encoding="utf-8") as f:
    html_content = f.read()

# Discord ne supporte pas HTML, on extrait un résumé texte
from bs4 import BeautifulSoup

soup = BeautifulSoup(html_content, "html.parser")
rows = soup.find_all("tr")[1:]  # skip header
summary = f"Rapport UI Selenium ({datetime.now()}):\n"
for row in rows:
    cols = [td.get_text(strip=True) for td in row.find_all("td")]
    summary += f"- {cols[0]}: {cols[2]} ({cols[3]})\n"

payload = {"content": summary}
resp = requests.post(DISCORD_WEBHOOK, json=payload)
if resp.status_code == 204:
    print("Notification Discord envoyée.")
else:
    print(f"[ERREUR] Discord status {resp.status_code}: {resp.text}")
