# Surveillance continue automatisée (exemple)


import datetime
import os
import smtplib
import subprocess
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
    print("[Surveillance] Variables d'environnement chargées depuis .env")
except ImportError:
    print(
        "[Surveillance] python-dotenv non installé, les variables .env ne seront pas chargées automatiquement."
    )

CHECK_INTERVAL_MINUTES = 30
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "ia.strategy.support@gmail.com")


def send_alert_email(
    subject,
    body,
    to_email=ALERT_EMAIL,
    smtp_user=None,
    smtp_pass=None,
    smtp_server=None,
    smtp_port=None,
):
    # SMTP générique, compatible Gmail/Outlook/Custom
    smtp_user = smtp_user or os.environ.get(
        "SMTP_USER", "ia.strategy.support@gmail.com"
    )
    smtp_pass = smtp_pass or os.environ.get("SMTP_PASS", "VOTRE_MDP_SMTP_ICI")
    smtp_server = smtp_server or os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = smtp_port or int(os.environ.get("SMTP_PORT", 587))
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_email, msg.as_string())
        server.quit()
        print(f"[ALERTE] Email envoyé à {to_email}")
    except Exception as e:
        print(f"[ALERTE] Erreur envoi email : {e}")


while True:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[SURVEILLANCE] Vérification à {now}")
    try:
        # Vérification de l'orchestration
        result = subprocess.run(
            [
                r"c:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe",
                "orchestrate_ecosystem.py",
            ],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if result.returncode == 0:
            print(f"[OK] Orchestration réussie à {now}")
        else:
            print(f"[ERREUR] Orchestration échouée à {now}\n{result.stderr}")
            send_alert_email(
                subject="[ALERTE QUANT] Orchestration échouée",
                body=f"Erreur d'orchestration à {now}\n\n{result.stderr}\n\nSortie:\n{result.stdout}",
            )

        # Vérification de l'importabilité des modules
        import_test = subprocess.run(
            [
                r"c:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe",
                "-m",
                "unittest",
                "test_imports_all_modules.py",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if import_test.returncode == 0:
            print(f"[OK] Importabilité des modules validée à {now}")
        else:
            print(
                f"[ERREUR] Importabilité échouée à {now}\n{import_test.stdout}\n{import_test.stderr}"
            )
            send_alert_email(
                subject="[ALERTE QUANT] Importabilité échouée",
                body=f"Erreur d'importabilité à {now}\n\n{import_test.stdout}\n{import_test.stderr}",
            )

        # Vérification du dashboard (ping du port 8501 par défaut Streamlit)
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result_dashboard = sock.connect_ex(("localhost", 8501))
        if result_dashboard == 0:
            print(f"[OK] Dashboard Streamlit accessible à {now}")
        else:
            print(f"[ERREUR] Dashboard Streamlit INACCESSIBLE à {now}")
            send_alert_email(
                subject="[ALERTE QUANT] Dashboard Streamlit INACCESSIBLE",
                body=f"Dashboard non accessible à {now} sur le port 8501.",
            )
        sock.close()
    except Exception as e:
        print(f"[EXCEPTION] {e}")
        send_alert_email(
            subject="[ALERTE QUANT] Exception système",
            body=f"Exception lors de la surveillance à {now}:\n{e}",
        )
    print(
        f"[SURVEILLANCE] Prochaine vérification dans {CHECK_INTERVAL_MINUTES} minutes..."
    )
    time.sleep(CHECK_INTERVAL_MINUTES * 60)
