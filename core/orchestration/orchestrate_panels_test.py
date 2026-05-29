"""Orchestration manuelle des panels — exécuter: python orchestrate_panels_test.py"""

from __future__ import annotations

import subprocess
import sys

PANELS = [
    "🛡️ Supervision & Auto-Heal",
    "🩺 BotDoctor Dashboard",
    "🌐 Evolution Multi-Monde",
    "🌐 3D Evolution Viewer",
    "📊 Quant V16 Panel",
    "📈 Quant Terminal V12",
    "🧠 R&D Feedback Dashboard",
]


def main() -> None:
    for panel in PANELS:
        print(f"[TEST] Panel: {panel}")
        result = subprocess.run(
            [sys.executable, "evolution_3d_view.py", panel],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"[ERREUR] Panel {panel} a échoué :\n{result.stderr}")
        else:
            print(f"[OK] Panel {panel} fonctionne.")


if __name__ == "__main__":
    main()
