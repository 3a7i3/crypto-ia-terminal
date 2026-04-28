import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Usage: python send_orchestration_notification.py <results_dir> <to_email> <smtp_user> <smtp_pass> <provider> [smtp_server] [smtp_port]
if len(sys.argv) < 6:
    print(
        "Usage: python send_orchestration_notification.py <results_dir> <to_email> <smtp_user> <smtp_pass> <provider> [smtp_server] [smtp_port]"
    )
    sys.exit(1)

results_dir, to_email, smtp_user, smtp_pass, provider = sys.argv[1:6]
smtp_server = sys.argv[6] if len(sys.argv) > 6 else None
smtp_port = int(sys.argv[7]) if len(sys.argv) > 7 else None

# Compose le message
subject = f"Orchestration terminée : {os.path.basename(results_dir)}"
body = f"La simulation batch est terminée.\n\nDossier de résultats : {results_dir}\n\nConsultez le rapport HTML pour le résumé."

msg = MIMEMultipart()
msg["From"] = smtp_user
msg["To"] = to_email
msg["Subject"] = subject
msg.attach(MIMEText(body, "plain", "utf-8"))

# Préréglages SMTP
if provider == "Gmail":
    smtp_server = smtp_server or "smtp.gmail.com"
    smtp_port = smtp_port or 587
elif provider == "Outlook/Office365":
    smtp_server = smtp_server or "smtp.office365.com"
    smtp_port = smtp_port or 587
elif provider == "Yahoo":
    smtp_server = smtp_server or "smtp.mail.yahoo.com"
    smtp_port = smtp_port or 587
elif provider == "Custom SMTP":
    if not smtp_server or not smtp_port:
        print("Veuillez renseigner le serveur et port SMTP personnalisés.")
        sys.exit(1)
else:
    print("Fournisseur SMTP non supporté.")
    sys.exit(1)

try:
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(smtp_user, smtp_pass)
    server.sendmail(smtp_user, to_email, msg.as_string())
    server.quit()
    print(f"[OK] Notification envoyée à {to_email}")
except Exception as e:
    print(f"[ERREUR] Impossible d'envoyer la notification : {e}")
