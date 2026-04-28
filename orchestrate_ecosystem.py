# =============================================
# 📚 Documentation enrichie / Enhanced Docs
#
# - README_CONSOLIDATED.md : Guide d’installation, configuration, lancement rapide, FAQ, bonnes pratiques
# - DASHBOARD_USAGE_TEMPLATES.md : Exemples d’utilisation pour chaque dashboard (Panel/Streamlit)
# - ACTION_PLAN_CHECKLIST.md : Plan d’action détaillé pour finaliser et maintenir le système
#
# Conseil : commencez par le README_CONSOLIDATED.md pour une vue d’ensemble, puis utilisez les templates et le plan d’action pour accélérer votre onboarding ou vos évolutions.
#
# For a professional onboarding, usage examples, and a step-by-step action plan, see the above links.
# =============================================
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from supervision.notifications.email_notifier import EmailNotifier
from supervision.notifications.slack_notifier import SlackNotifier
from supervision.notifications.telegram_notifier import TelegramNotifier

RESULTS_DIR = Path("results")
ARCHIVE_DIR = Path("archives")
ARCHIVE_DIR.mkdir(exist_ok=True)


def run_and_archive():
    # --- Initialisation des notifiers si variables présentes ---
    slack = None
    telegram = None
    email = None
    if os.environ.get("SLACK_WEBHOOK_URL"):
        slack = SlackNotifier(webhook_url=os.environ["SLACK_WEBHOOK_URL"])
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        telegram = TelegramNotifier(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
        )
    if (
        os.environ.get("EMAIL_SMTP_SERVER")
        and os.environ.get("EMAIL_FROM")
        and os.environ.get("EMAIL_TO")
    ):
        email = EmailNotifier(
            smtp_server=os.environ["EMAIL_SMTP_SERVER"],
            from_addr=os.environ["EMAIL_FROM"],
            to_addr=os.environ["EMAIL_TO"],
        )

    print("[1] Lancement de la simulation multi-monde...")
    try:
        subprocess.run(
            [
                "c:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe",
                "run_strategy_factory.py",
            ],
            check=True,
        )
    except Exception as e:
        msg = f"[ALERTE] Échec simulation multi-monde : {e}"
        if slack:
            try:
                slack.notify(msg)
            except Exception as err:
                print(f"Erreur Slack: {err}")
        if telegram:
            try:
                telegram.notify(msg)
            except Exception as err:
                print(f"Erreur Telegram: {err}")
        if email:
            try:
                email.notify("Alerte Orchestration", msg)
            except Exception as err:
                print(f"Erreur Email: {err}")
        raise

    print("[2] Archivage des résultats...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = ARCHIVE_DIR / f"ecosystem_{timestamp}"
    archive_path.mkdir(exist_ok=True)
    # Archive tous les CSV, JSON, PNG, HTML, feedbacks
    for ext in ["*.csv", "*.json", "*.png", "*.html"]:
        for file in RESULTS_DIR.glob(ext):
            shutil.copy(file, archive_path / file.name)
    feedback_dir = Path("feedback_logs")
    if feedback_dir.exists():
        for file in feedback_dir.glob("*"):
            shutil.copy(file, archive_path / file.name)
    print(f"[ARCHIVE] Résultats archivés dans {archive_path}")

    print("[4] Profilage backtest & monitoring supervision...")
    try:
        ret1 = subprocess.run(
            [
                "c:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe",
                "strategy_factory/backtest_profiler.py",
                "--n",
                "5000",
                "--n_strat",
                "4",
                "--logfile",
                "results/backtest_profiler.log",
                "--save",
                "results/backtest_profiler_results.csv",
            ]
        )
        if ret1.returncode != 0:
            msg = "[ALERTE] backtest_profiler.py a échoué."
            print(msg)
            if slack:
                try:
                    slack.notify(msg)
                except Exception as err:
                    print(f"Erreur Slack: {err}")
            if telegram:
                try:
                    telegram.notify(msg)
                except Exception as err:
                    print(f"Erreur Telegram: {err}")
            if email:
                try:
                    email.notify("Alerte Orchestration", msg)
                except Exception as err:
                    print(f"Erreur Email: {err}")
        ret2 = subprocess.run(
            [
                "c:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe",
                "supervision/monitoring_profiler.py",
                "--duration",
                "5",
                "--logfile",
                "results/monitoring_profiler.log",
            ]
        )
        if ret2.returncode != 0:
            msg = "[ALERTE] monitoring_profiler.py a échoué."
            print(msg)
            if slack:
                try:
                    slack.notify(msg)
                except Exception as err:
                    print(f"Erreur Slack: {err}")
            if telegram:
                try:
                    telegram.notify(msg)
                except Exception as err:
                    print(f"Erreur Telegram: {err}")
            if email:
                try:
                    email.notify("Alerte Orchestration", msg)
                except Exception as err:
                    print(f"Erreur Email: {err}")
    except Exception as e:
        msg = f"[ALERTE] Erreur lors du profiling/monitoring: {e}"
        print(msg)
        if slack:
            try:
                slack.notify(msg)
            except Exception as err:
                print(f"Erreur Slack: {err}")
        if telegram:
            try:
                telegram.notify(msg)
            except Exception as err:
                print(f"Erreur Telegram: {err}")
        if email:
            try:
                email.notify("Alerte Orchestration", msg)
            except Exception as err:
                print(f"Erreur Email: {err}")
        raise

    print("[3] Lancement de l'analyse des niches et clusters...")
    try:
        subprocess.run(
            [
                "c:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe",
                "analyze_strategy_niches.py",
            ],
            check=True,
        )
    except Exception as e:
        msg = f"[ALERTE] Erreur analyse niches/clusters: {e}"
        print(msg)
        if slack:
            try:
                slack.notify(msg)
            except Exception as err:
                print(f"Erreur Slack: {err}")
        if telegram:
            try:
                telegram.notify(msg)
            except Exception as err:
                print(f"Erreur Telegram: {err}")
        if email:
            try:
                email.notify("Alerte Orchestration", msg)
            except Exception as err:
                print(f"Erreur Email: {err}")
        raise
    msg = "[OK] Orchestration complète terminée."
    print(msg)
    # Notifier succès global
    if slack:
        try:
            slack.notify(msg)
        except Exception as err:
            print(f"Erreur Slack: {err}")
    if telegram:
        try:
            telegram.notify(msg)
        except Exception as err:
            print(f"Erreur Telegram: {err}")
    if email:
        try:
            email.notify("Orchestration terminée", msg)
        except Exception as err:
            print(f"Erreur Email: {err}")


if __name__ == "__main__":
    run_and_archive()
