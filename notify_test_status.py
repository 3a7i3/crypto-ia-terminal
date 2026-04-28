# Simple notification script for test results
# This version prints to console and can be extended for email/discord/telegram

import json
import os
import smtplib
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests


def send_discord_notification(message, webhook_url):
    data = {"content": message}
    try:
        response = requests.post(webhook_url, json=data)
        if response.status_code == 204:
            print("✅ Discord notification sent.")
        else:
            print(f"❌ Discord notification failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Discord notification error: {e}")


def send_email_notification(
    subject, body, to_email, smtp_server, smtp_port, smtp_user, smtp_password
):
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        print("✅ Email notification sent.")
    except Exception as e:
        print(f"❌ Email notification error: {e}")


def send_telegram_notification(message, bot_token, chat_id):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {"chat_id": chat_id, "text": message}
    try:
        import requests

        response = requests.post(url, data=data)
        if response.status_code == 200:
            print("✅ Telegram notification sent.")
        else:
            print(
                f"❌ Telegram notification failed: {response.status_code} {response.text}"
            )
    except Exception as e:
        print(f"❌ Telegram notification error: {e}")


def check_test_report(
    report_path="test_report.md", webhook_url=None, email_conf=None, telegram_conf=None
):
    if not os.path.exists(report_path):
        print("No test report found.")
        return "no_report"
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
    status = None
    if "failed" in content or "error" in content.lower():
        print("❌ Test(s) failed!")
        status = "fail"
    elif "warning" in content.lower():
        print("⚠️ Test(s) warning!")
        status = "warning"
    elif "skipped" in content.lower():
        print("ℹ️ Test(s) skipped.")
        status = "skipped"
    else:
        print("✅ All tests passed!")
        status = "success"

    # Message enrichi
    summary = content[:500]
    report_link = os.environ.get("TEST_REPORT_URL", None)
    msg = f"[Test Suite] Status: {status.upper()}\n"
    if report_link:
        msg += f"Rapport complet : {report_link}\n"
    msg += f"Résumé :\n{summary}"

    # Discord notification (succès ou échec)
    if webhook_url:
        send_discord_notification(msg, webhook_url)
    # Email notification (succès, fail, warning)
    if email_conf:
        send_email_notification(
            subject=f"Test status: {status.upper()}",
            body=msg,
            to_email=email_conf["to_email"],
            smtp_server=email_conf["smtp_server"],
            smtp_port=email_conf["smtp_port"],
            smtp_user=email_conf["smtp_user"],
            smtp_password=email_conf["smtp_password"],
        )
    # Telegram notification (succès, fail, warning)
    if telegram_conf:
        send_telegram_notification(
            message=msg,
            bot_token=telegram_conf["bot_token"],
            chat_id=telegram_conf["chat_id"],
        )
    return status


def run_tests_and_notify():
    # Run pytest and generate report
    print("Running tests (quant-ai-system/quant_ai_tests)...")
    subprocess.run(
        "C:/Users/WINDOWS/AppData/Local/Programs/Python/Python314/python.exe -m pytest quant-ai-system/quant_ai_tests > all_tests_output2.txt 2>&1",
        shell=True,
    )
    print("Running tests (crypto_quant_v16/tests)...")
    subprocess.run(
        "C:/Users/WINDOWS/AppData/Local/Programs/Python/Python314/python.exe -m pytest crypto_quant_v16/tests >> all_tests_output2.txt 2>&1",
        shell=True,
    )
    # Ajoute ici d'autres dossiers de tests si besoin
    subprocess.run(
        [
            "C:/Users/WINDOWS/AppData/Local/Programs/Python/Python314/python.exe",
            "generate_test_report.py",
        ]
    )
    # Notify Discord/email/Telegram (rapport global)
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", None)
    email_conf = None
    if os.environ.get("EMAIL_ENABLED", "0") == "1":
        email_conf = {
            "to_email": os.environ.get("EMAIL_TO"),
            "smtp_server": os.environ.get("EMAIL_SMTP_SERVER"),
            "smtp_port": int(os.environ.get("EMAIL_SMTP_PORT", "587")),
            "smtp_user": os.environ.get("EMAIL_SMTP_USER"),
            "smtp_password": os.environ.get("EMAIL_SMTP_PASSWORD"),
        }
    telegram_conf = None
    if os.environ.get("TELEGRAM_ENABLED", "0") == "1":
        telegram_conf = {
            "bot_token": os.environ.get("TELEGRAM_BOT_TOKEN"),
            "chat_id": os.environ.get("TELEGRAM_CHAT_ID"),
        }
    # Utilise le rapport global si présent
    report_path = (
        "all_tests_report.md"
        if os.path.exists("all_tests_report.md")
        else "test_report.md"
    )
    check_test_report(
        report_path=report_path,
        webhook_url=webhook_url,
        email_conf=email_conf,
        telegram_conf=telegram_conf,
    )


if __name__ == "__main__":
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", None)
    # Email config via env vars
    email_conf = None
    if os.environ.get("EMAIL_ENABLED", "0") == "1":
        email_conf = {
            "to_email": os.environ.get("EMAIL_TO"),
            "smtp_server": os.environ.get("EMAIL_SMTP_SERVER"),
            "smtp_port": int(os.environ.get("EMAIL_SMTP_PORT", "587")),
            "smtp_user": os.environ.get("EMAIL_SMTP_USER"),
            "smtp_password": os.environ.get("EMAIL_SMTP_PASSWORD"),
        }
    # Telegram config via env vars
    telegram_conf = None
    if os.environ.get("TELEGRAM_ENABLED", "0") == "1":
        telegram_conf = {
            "bot_token": os.environ.get("TELEGRAM_BOT_TOKEN"),
            "chat_id": os.environ.get("TELEGRAM_CHAT_ID"),
        }
    run_tests_and_notify = globals().get("run_tests_and_notify")
    if run_tests_and_notify:
        run_tests_and_notify()
    else:
        check_test_report(
            webhook_url=webhook_url, email_conf=email_conf, telegram_conf=telegram_conf
        )
