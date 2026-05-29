"""
notifications.py — Façade unique pour toutes les alertes du système.

Canaux supportés (configurés via .env) :
  - Telegram : TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  - Slack    : SLACK_WEBHOOK_URL
  - Email    : EMAIL_SMTP_SERVER, EMAIL_FROM_ADDR, EMAIL_TO_ADDR, etc.

Fournit :
  - NOTIFIER              → MultiNotifier global (envoi sync)
  - send_alert(msg)       → raccourci sync
  - build_telegram_bot()  → adaptateur async compatible GlobalRiskGate
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger("notifications")


# ── Canaux sync ────────────────────────────────────────────────────────────────


def send_email(
    subject: str,
    body: str,
    to_email: str | None = None,
    smtp_server: str | None = None,
    smtp_port: int = 465,
    smtp_user: str | None = None,
    smtp_pass: str | None = None,
) -> None:
    """Envoi email via SMTP SSL. Paramètres lus depuis .env si absents."""
    to_email = to_email or os.getenv("EMAIL_TO_ADDR", "")
    smtp_server = smtp_server or os.getenv("EMAIL_SMTP_SERVER", "")
    smtp_user = smtp_user or os.getenv("EMAIL_FROM_ADDR", "")
    smtp_pass = smtp_pass or os.getenv("EMAIL_SMTP_PASS", "")
    if not all([to_email, smtp_server, smtp_user, smtp_pass]):
        logger.warning("[Email] Configuration incomplète — envoi ignoré")
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email
    with smtplib.SMTP_SSL(smtp_server, int(smtp_port)) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_email], msg.as_string())
    logger.info("[Email] Envoyé à %s", to_email)


def send_slack(message: str, webhook_url: str | None = None) -> None:
    """Envoi Slack via webhook. URL lue depuis .env si absente."""
    webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("[Slack] SLACK_WEBHOOK_URL absent — envoi ignoré")
        return
    try:
        import json
        import urllib.request

        payload = json.dumps({"text": message}).encode()
        req = urllib.request.Request(
            webhook_url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                logger.warning("[Slack] Statut non-200: %s", resp.status)
    except Exception as exc:
        logger.error("[Slack] Erreur: %s", exc)


# ── MultiNotifier global ───────────────────────────────────────────────────────


def _build_notifier():
    from supervision.notifications.multi_notifier import MultiNotifier
    from supervision.notifications.telegram_notifier import TelegramNotifier

    notifiers = []

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        notifiers.append(TelegramNotifier(token, chat))
        logger.info("[Notifications] Telegram activé (chat=%s)", chat)
    else:
        logger.info(
            "[Notifications] Telegram désactivé — définir TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID dans .env"
        )

    slack_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if slack_url:
        from supervision.notifications.slack_notifier import SlackNotifier

        notifiers.append(SlackNotifier(slack_url))
        logger.info("[Notifications] Slack activé")

    return MultiNotifier(notifiers)


NOTIFIER = _build_notifier()


def send_alert(message: str) -> None:
    """Envoi synchrone vers tous les canaux configurés (Telegram, Slack…)."""
    NOTIFIER.notify(message)


# ── Adaptateur async pour GlobalRiskGate ──────────────────────────────────────


class TelegramBotAdapter:
    """
    Pont entre TelegramNotifier (sync) et GlobalRiskGate (attend async send_message).
    Si aucun token n'est configuré, send_message() est un no-op silencieux.
    """

    def __init__(self) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self._active = bool(token and chat)
        if self._active:
            from supervision.notifications.telegram_notifier import \
                TelegramNotifier

            self._notifier = TelegramNotifier(token, chat)

    @property
    def active(self) -> bool:
        return self._active

    async def send_message(self, text: str) -> None:
        if not self._active:
            return
        try:
            self._notifier.notify(text)
        except Exception as exc:
            logger.error("[TelegramBotAdapter] Erreur: %s", exc)


def build_telegram_bot() -> TelegramBotAdapter | None:
    """
    Retourne l'adaptateur si TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID sont définis,
    None sinon (GlobalRiskGate accepte None sans planter).
    """
    adapter = TelegramBotAdapter()
    return adapter if adapter.active else None
