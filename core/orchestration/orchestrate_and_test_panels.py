import os
import subprocess
import sys
import time

# Panels and their dashboard files
PANELS = [
    ("🛡️ Supervision & Auto-Heal", "dashboard/alert_dashboard.py"),
    ("🩺 BotDoctor Dashboard", "supervision/botdoctor_dashboard.py"),
    ("🌐 Evolution Multi-Monde", "evolution_dashboard.py"),
    ("🌐 3D Evolution Viewer", "evolution_3d_view.py"),
    ("📊 Quant V16 Panel", "crypto_quant_v16/ui/quant_dashboard.py"),
    ("📈 Quant Terminal V12", "quant_hedge_ai/dashboard/quant_terminal_v12.py"),
    ("🧠 R&D Feedback Dashboard", "ai_autonomous_loop/feedback_dashboard.py"),
]

REPORT = []

for label, path in PANELS:
    abs_path = os.path.abspath(path)
    print(f"[TEST] {label} → {abs_path}")
    if not os.path.exists(abs_path):
        REPORT.append((label, "Fichier introuvable", abs_path))
        print(f"[ERREUR] Fichier introuvable : {abs_path}")
        continue
    # Tentative d'ouverture dans VS Code (si installé)
    try:
        subprocess.run(["code", abs_path], check=False)
        print("[OK] Ouverture dans VS Code (si installé)")
    except Exception as e:
        print(f"[WARN] Impossible d’ouvrir dans VS Code : {e}")
    # Tentative d’exécution si c’est un dashboard Streamlit ou Python
    if abs_path.endswith(".py"):
        print(f"[INFO] Test d’exécution du fichier : {abs_path}")
        try:
            proc = subprocess.Popen(
                [sys.executable, abs_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(3)  # Laisse le temps de démarrer
            proc.terminate()
            out, err = proc.communicate()
            if proc.returncode == 0:
                print("[OK] Exécution sans erreur fatale.")
                REPORT.append((label, "OK", abs_path))
            else:
                print(
                    f"[ERREUR] Retour code {proc.returncode}\n{err.decode(errors='ignore')}"
                )
                REPORT.append(
                    (
                        label,
                        f"Erreur code {proc.returncode}",
                        err.decode(errors="ignore"),
                    )
                )
        except Exception as e:
            print(f"[ERREUR] Exception à l’exécution : {e}")
            REPORT.append((label, "Exception", str(e)))
    else:
        REPORT.append((label, "Non testé (pas un .py)", abs_path))

# Rapport final
print("\n--- Rapport d’orchestration panels ---")
for label, status, info in REPORT:
    print(f"- {label}: {status}\n  {info}")
print("--- Fin du rapport ---")
