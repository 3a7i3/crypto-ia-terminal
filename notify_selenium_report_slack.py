import os
from datetime import datetime

import requests

# Slack webhook URL (à configurer)
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK_URL", "")

REPORT_FILE = "panel_selenium_report.html"

if not SLACK_WEBHOOK:
    print("[ERREUR] Variable d'environnement SLACK_WEBHOOK_URL non définie.")
    exit(1)

with open(REPORT_FILE, "r", encoding="utf-8") as f:
    html_content = f.read()

# Slack ne supporte pas HTML, on extrait un résumé texte
from bs4 import BeautifulSoup

soup = BeautifulSoup(html_content, "html.parser")
rows = soup.find_all("tr")[1:]  # skip header
summary = f"Rapport UI Selenium ({datetime.now()}):\n"
for row in rows:
    cols = [td.get_text(strip=True) for td in row.find_all("td")]
    summary += f"- {cols[0]}: {cols[2]} ({cols[3]})\n"

payload = {"text": summary}
resp = requests.post(SLACK_WEBHOOK, json=payload)
if resp.status_code == 200:
    print("Notification Slack envoyée.")
else:
    print(f"[ERREUR] Slack status {resp.status_code}: {resp.text}")
