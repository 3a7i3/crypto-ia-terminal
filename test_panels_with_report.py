import datetime
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

failures = []
tuto_failures = []
for panel in PANELS:
    print(f"[TEST] Panel: {panel}")
    result = subprocess.run(
        [sys.executable, "evolution_3d_view.py", panel], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[ERREUR] Panel {panel} a échoué :\n{result.stderr}")
        failures.append((panel, result.stderr))
    else:
        # Vérifie la présence du bouton Tutoriel interactif dans la sortie
        output = result.stdout + result.stderr
        if "Tutoriel interactif" not in output:
            print(f"[ERREUR] Tutoriel interactif absent dans le panel {panel}")
            tuto_failures.append(panel)
        else:
            print(f"[OK] Panel {panel} fonctionne et tutoriel présent.")

if failures or tuto_failures:
    report = f"Rapport d'échec panels ({datetime.datetime.now()}):\n"
    for panel, err in failures:
        report += f"\n---\nPanel: {panel}\nErreur:\n{err}\n"
    if tuto_failures:
        report += f"\nPanels sans tutoriel interactif : {', '.join(tuto_failures)}\n"
    with open("panel_test_report.txt", "w", encoding="utf-8") as f:
        f.write(report)
    print(
        "\n[!] Des panels ont échoué ou n'ont pas le tutoriel. Rapport généré : panel_test_report.txt"
    )
else:
    print("\nTous les panels ont passé les tests avec succès et affichent le tutoriel.")
