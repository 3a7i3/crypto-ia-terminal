import logging
import os
import time

from supervision.bot_doctor import BotDoctor
from supervision.custom_module import CustomTradingModule
from supervision.notifications.multi_notifier import MultiNotifier
from supervision.notifications.slack_notifier import SlackNotifier
from supervision.notifications.telegram_notifier import TelegramNotifier


class CustomNotifier:
    def notify(self, message):
        if "custom" in message.lower():
            print(f"[ALERTE CUSTOM] {message}")


def build_doctor(modules=None, notifier=None) -> BotDoctor:
    """Construit et retourne un BotDoctor prêt à l'emploi."""
    if modules is None:
        modules = [
            CustomTradingModule("Custom1", True),
            CustomTradingModule("Custom2", False),
        ]
    if notifier is None:
        slack = SlackNotifier(
            os.getenv("SLACK_WEBHOOK", "https://hooks.slack.com/placeholder")
        )
        telegram = TelegramNotifier(
            os.getenv("TELEGRAM_TOKEN", "BOT_TOKEN"),
            os.getenv("TELEGRAM_CHAT_ID", "CHAT_ID"),
        )
        notifier = MultiNotifier([slack, telegram, CustomNotifier()])
    return BotDoctor(modules, notifier=notifier)


def run_once(doctor: BotDoctor) -> dict:
    """Exécute un cycle de supervision et retourne le rapport."""
    doctor.run()
    return {
        "health_score": doctor.health_score,
        "report": doctor.get_report(),
    }


def main(interval: int = 60) -> None:
    os.makedirs("logs", exist_ok=True)
    handler = logging.FileHandler("logs/botdoctor_alerts.log")
    handler.setLevel(logging.WARNING)
    logging.getLogger("BotDoctor").addHandler(handler)

    doctor = build_doctor()
    while True:
        result = run_once(doctor)
        print(f"[Supervision] score={result['health_score']}%")
        time.sleep(interval)


if __name__ == "__main__":
    main()
