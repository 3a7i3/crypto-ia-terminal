from __future__ import annotations

import datetime
import subprocess
import sys
from pathlib import Path

PANELS = [
    "🛡️ Supervision & Auto-Heal",
    "🩺 BotDoctor Dashboard",
    "🌐 Evolution Multi-Monde",
    "🌐 3D Evolution Viewer",
    "📊 Quant V16 Panel",
    "📈 Quant Terminal V12",
    "🧠 R&D Feedback Dashboard",
]


def main() -> int:
    failures: list[tuple[str, str]] = []
    tutorial_failures: list[str] = []
    for panel in PANELS:
        print(f"[TEST] Panel: {panel}")
        result = subprocess.run([sys.executable, "evolution_3d_view.py", panel], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[ERREUR] Panel {panel} a échoué :\n{result.stderr}")
            failures.append((panel, result.stderr))
            continue

        output = result.stdout + result.stderr
        if "Tutoriel interactif" not in output:
            print(f"[ERREUR] Tutoriel interactif absent dans le panel {panel}")
            tutorial_failures.append(panel)
        else:
            print(f"[OK] Panel {panel} fonctionne et tutoriel présent.")

    if failures or tutorial_failures:
        report = f"Rapport d'échec panels ({datetime.datetime.now()}):\n"
        for panel, error in failures:
            report += f"\n---\nPanel: {panel}\nErreur:\n{error}\n"
        if tutorial_failures:
            report += f"\nPanels sans tutoriel interactif : {', '.join(tutorial_failures)}\n"
        Path("panel_test_report.txt").write_text(report, encoding="utf-8")
        print("\n[!] Des panels ont échoué ou n'ont pas le tutoriel. Rapport généré : panel_test_report.txt")
        return 1

    print("\nTous les panels ont passé les tests avec succès et affichent le tutoriel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
