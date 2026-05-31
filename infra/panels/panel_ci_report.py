import os
import socket
import subprocess
import sys
import time
from datetime import datetime

PANELS = [
    ("🛡️ Supervision & Auto-Heal", "dashboard/alert_dashboard.py", 5011),
    ("🩺 BotDoctor Dashboard", "supervision/botdoctor_dashboard.py", 5012),
    ("🌐 Evolution Multi-Monde", "evolution_dashboard.py", 5013),
    ("🌐 3D Evolution Viewer", "evolution_3d_view.py", 5014),
    ("📊 Quant V16 Panel", "crypto_quant_v16/ui/quant_dashboard.py", 5015),
    ("📈 Quant Terminal V12", "quant_hedge_ai/dashboard/quant_terminal_v12.py", 5016),
    ("🧠 R&D Feedback Dashboard", "ai_autonomous_loop/feedback_dashboard.py", 5017),
]

REPORT = []

html = [
    f"<html><head><meta charset='utf-8'><title>Rapport CI Panels {datetime.now()}</title></head><body>",
    f"<h1>Rapport CI Panels - {datetime.now()}</h1>",
    "<table border='1' cellpadding='6'><tr><th>Panneau</th><th>Fichier</th><th>Port</th><th>Ouverture</th><th>Exécution</th><th>Port</th><th>Résumé</th></tr>",
]


def check_port(port, timeout=2):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False


for label, path, port in PANELS:
    abs_path = os.path.abspath(path)
    open_status = "❌"
    exec_status = "❌"
    port_status = "❌"
    summary = ""
    # Test ouverture
    if os.path.exists(abs_path):
        open_status = "✅"
    else:
        summary += "Fichier introuvable. "
    # Test exécution
    if open_status == "✅" and abs_path.endswith(".py"):
        try:
            proc = subprocess.Popen(
                [sys.executable, abs_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(5)
            # Vérification port
            if check_port(port):
                port_status = "✅"
                summary += f"Port {port} ouvert. "
            else:
                summary += f"Port {port} non détecté. "
            proc.terminate()
            out, err = proc.communicate()
            if proc.returncode == 0:
                exec_status = "✅"
            else:
                summary += f"Erreur code {proc.returncode}. "
        except Exception as e:
            summary += f"Exception: {e}. "
    html.append(
        f"<tr><td>{label}</td><td>{abs_path}</td><td>{port}</td><td>{open_status}</td><td>{exec_status}</td><td>{port_status}</td><td>{summary}</td></tr>"
    )

html.append("</table></body></html>")

with open("panel_ci_report.html", "w", encoding="utf-8") as f:
    f.write("\n".join(html))

print("Rapport HTML généré : panel_ci_report.html")
try:
    import webbrowser

    webbrowser.open("file://" + os.path.abspath("panel_ci_report.html"))
    print("Ouverture automatique du rapport dans le navigateur.")
except Exception as e:
    print(f"[WARN] Impossible d’ouvrir le navigateur automatiquement : {e}")
