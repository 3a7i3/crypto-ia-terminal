"""Test HTTP des panels — exécuter: python panel_http_test.py (ou SELENIUM_PANEL_E2E=1 + pytest)."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import requests

PANELS = [
    ("🛡️ Supervision & Auto-Heal", "dashboard/alert_dashboard.py", 5011, "/"),
    ("🩺 BotDoctor Dashboard", "supervision/botdoctor_dashboard.py", 5012, "/"),
    ("🌐 Evolution Multi-Monde", "evolution_dashboard.py", 5013, "/"),
    ("🌐 3D Evolution Viewer", "evolution_3d_view.py", 5014, "/"),
    ("📊 Quant V16 Panel", "crypto_quant_v16/ui/quant_dashboard.py", 5015, "/"),
    (
        "📈 Quant Terminal V12",
        "quant_hedge_ai/dashboard/quant_terminal_v12.py",
        5016,
        "/",
    ),
    (
        "🧠 R&D Feedback Dashboard",
        "ai_autonomous_loop/feedback_dashboard.py",
        5017,
        "/",
    ),
]


def wait_for_port(port: int, timeout: float = 10) -> bool:
    import socket

    start = time.time()
    while time.time() - start < timeout:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> None:
    report: list[tuple] = []
    for label, path, port, endpoint in PANELS:
        abs_path = os.path.abspath(path)
        status = "❌"
        http_status = "❌"
        http_code = ""
        if not os.path.exists(abs_path):
            report.append(
                (label, "Fichier introuvable", abs_path, status, http_status, http_code)
            )
            continue
        proc = subprocess.Popen(
            [sys.executable, abs_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if wait_for_port(port, timeout=10):
            status = "✅"
            try:
                url = f"http://127.0.0.1:{port}{endpoint}"
                resp = requests.get(url, timeout=5)
                http_code = str(resp.status_code)
                if resp.status_code == 200:
                    http_status = "✅"
                else:
                    http_status = "❌"
            except Exception as e:
                http_code = str(e)
        proc.terminate()
        report.append((label, "OK", abs_path, status, http_status, http_code))

    with open("panel_http_report.txt", "w", encoding="utf-8") as f:
        for label, msg, path, st, http_st, code in report:
            f.write(f"{label}\t{msg}\t{path}\tPort:{st}\tHTTP:{http_st}\tCode:{code}\n")

    print("Rapport HTTP/UI généré : panel_http_report.txt")


if __name__ == "__main__":
    main()
