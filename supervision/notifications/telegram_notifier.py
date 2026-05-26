"""
telegram_notifier.py — Envoi de notifications via l'API Telegram Bot.
"""

from __future__ import annotations

import urllib.parse
import urllib.request

from observability.json_logger import get_logger

_log = get_logger("TelegramNotifier")


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def notify(self, message: str) -> bool:
        try:
            import json

            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = json.dumps({"chat_id": self.chat_id, "text": message}).encode(
                "utf-8"
            )
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as exc:
            _log.error("Erreur TelegramNotifier: %s", exc)
            return False
