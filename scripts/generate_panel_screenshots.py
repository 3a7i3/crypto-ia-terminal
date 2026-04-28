# Script de génération automatique de screenshots Streamlit (panel par panel)
# Nécessite : pip install playwright pytest-playwright
# Usage : python scripts/generate_panel_screenshots.py

import os
import subprocess
import time
from pathlib import Path

PANELS = [
    ("🛡️ Supervision & Auto-Heal", "supervision_autoheal.png"),
    ("🩺 BotDoctor Dashboard", "botdoctor_dashboard.png"),
    ("🌐 Evolution Multi-Monde", "evolution_multimonde.png"),
    ("🌐 3D Evolution Viewer", "evolution_3d_viewer.png"),
    ("📊 Quant V16 Panel", "quant_v16_panel.png"),
    ("📈 Quant Terminal V12", "quant_terminal_v12.png"),
    ("🧠 R&D Feedback Dashboard", "feedback_dashboard.png"),
]

SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Lancement du serveur Streamlit pour chaque panel et capture via Playwright
for panel, filename in PANELS:
    print(f"[INFO] Lancement du panel : {panel}")
    proc = subprocess.Popen(["streamlit", "run", "evolution_3d_view.py", "--", panel])
    time.sleep(8)  # Laisse le temps au dashboard de démarrer
    # Capture avec Playwright (nécessite playwright install)
    url = "http://localhost:8501"
    out_path = SCREENSHOT_DIR / filename
    try:
        subprocess.run(
            [
                "playwright",
                "screenshot",
                "--wait-until",
                "networkidle",
                url,
                str(out_path),
            ],
            check=True,
        )
        print(f"[OK] Screenshot sauvegardé : {out_path}")
    except Exception as e:
        print(f"[ERREUR] Screenshot échoué pour {panel} : {e}")
    proc.terminate()
    time.sleep(2)

print("\nTous les screenshots générés dans le dossier 'screenshots/'.")
