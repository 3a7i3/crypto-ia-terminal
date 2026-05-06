"""
slack_notifier.py — Envoi de notifications via Slack webhook.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("SlackNotifier")


class SlackNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def notify(self, message: str) -> bool:
        try:
            import json
            import urllib.request

            payload = json.dumps({"text": message}).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                ok = resp.status == 200
            if not ok:
                logger.warning("Slack webhook a retourné un statut non-200")
            return ok
        except Exception as exc:
            logger.error("Erreur SlackNotifier: %s", exc)
            return False
