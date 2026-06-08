"""
Polling loop du SimBot.
Variables d'environnement requises :
  CMVK_BOT_TOKEN  — token du bot Telegram dédié simulation
  CMVK_CHAT_ID    — chat_id autorisé

Lancement :
  python -m src.telegram.bot_runner
"""

import json
import logging
import os
import time
import urllib.parse
import urllib.request

from src.telegram.sim_bot import SimBot

log = logging.getLogger("cmvk_bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_API = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 25


def _call(token: str, method: str, params: dict | None = None) -> dict:
    url = _API.format(token=token, method=method)
    data = urllib.parse.urlencode(params or {}).encode() if params else None
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=_TIMEOUT + 10) as resp:
        return json.loads(resp.read())


def _send(token: str, chat_id: str, text: str) -> None:
    try:
        _call(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
        )
    except Exception:
        # Fallback sans Markdown si le formatage casse l'API
        _call(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
            },
        )


def _clear_conflict(token: str) -> int:
    """Supprime webhook, vide la file, retourne le prochain offset."""
    try:
        _call(token, "deleteWebhook", {"drop_pending_updates": "true"})
        log.info("Webhook supprimé.")
    except Exception as exc:
        log.warning("deleteWebhook : %s", exc)

    # Vide toute la file en attente et calcule l'offset de départ
    offset = 0
    try:
        result = _call(token, "getUpdates", {"timeout": 0, "offset": -1})
        updates = result.get("result", [])
        if updates:
            offset = updates[-1]["update_id"] + 1
            log.info("File vidée — offset de départ : %d", offset)
    except Exception as exc:
        log.warning("Flush updates : %s", exc)

    time.sleep(1)
    return offset


def run_forever(token: str, chat_id: str, poll_timeout: int = _TIMEOUT) -> None:
    offset = _clear_conflict(token)

    bot = SimBot()
    seen_ids: set[int] = set()  # anti-doublon strict
    log.info("CMVK SimBot démarré. Chat autorisé : %s | offset : %d", chat_id, offset)

    while True:
        try:
            result = _call(
                token,
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": poll_timeout,
                    "allowed_updates": json.dumps(["message"]),
                },
            )
            updates = result.get("result", [])

            for upd in updates:
                uid = upd["update_id"]
                offset = uid + 1

                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                if len(seen_ids) > 500:  # évite la croissance illimitée
                    seen_ids.clear()

                msg = upd.get("message", {})
                from_chat = str(msg.get("chat", {}).get("id", ""))
                text = (msg.get("text") or "").strip()

                if from_chat != chat_id:
                    log.warning("Ignoré — chat non autorisé : %s", from_chat)
                    continue

                if not text.startswith("/"):
                    continue

                log.info("Commande : %s", text)
                try:
                    reply = bot.handle(text)
                except Exception as exc:
                    reply = f"❌ Erreur interne : {exc}"
                    log.exception("handle error")

                _send(token, chat_id, reply)

        except KeyboardInterrupt:
            log.info("Arrêt.")
            break
        except Exception as exc:
            err = str(exc)
            if "409" in err:
                log.warning(
                    "409 Conflict — autre instance active, pause 10s puis nettoyage."
                )
                time.sleep(10)
                offset = _clear_conflict(token)
            else:
                log.error("Erreur polling : %s — retry dans 3s", exc)
                time.sleep(3)


if __name__ == "__main__":
    _token = os.environ.get("CMVK_BOT_TOKEN", "")
    _chat = os.environ.get("CMVK_CHAT_ID", "")
    if not _token or not _chat:
        raise SystemExit("CMVK_BOT_TOKEN et CMVK_CHAT_ID doivent être définis.")
    run_forever(_token, _chat)
