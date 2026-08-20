#!/usr/bin/env python3
"""scripts/quant_observer_pin_bootstrap.py — cree le message epingle initial.

Le bot @QuantCrypto_bot rafraichit toutes les 10 min un message epingle du
chat (les "logs auto" de SDOS Live). Il a besoin de l'ID de ce message dans
QC_PINNED_MSG_ID. Ce script fait le bootstrap une fois :

  1. Envoie un placeholder au chat via QC_BOT_TOKEN / QC_CHAT_ID
  2. Tente de l'epingler (necessite que le bot soit admin du chat).
     Si le pin echoue (bot non-admin), le script continue quand meme
     et te dit d'epingler a la main dans Telegram.
  3. Affiche le message_id — a copier dans .env sous QC_PINNED_MSG_ID
  4. Redemarre le service pour prendre en compte le nouvel ID :
       sudo systemctl restart crypto-quant-observer.service

Usage :
    .venv/bin/python scripts/quant_observer_pin_bootstrap.py

Idempotent : peut etre relance en cas de reperte de l'ID (nouveau message,
nouvel ID a mettre en .env).

Exit codes :
    0 — succes (message envoye, ID affiche)
    1 — QC_BOT_TOKEN ou QC_CHAT_ID manquant
    2 — envoi Telegram echoue
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

# Charger .env
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

QC_BOT_TOKEN = os.getenv("QC_BOT_TOKEN", "").strip()
QC_CHAT_ID = os.getenv("QC_CHAT_ID", "").strip()

if not QC_BOT_TOKEN or not QC_CHAT_ID:
    print(
        "[ERREUR] QC_BOT_TOKEN ou QC_CHAT_ID manquant dans .env",
        file=sys.stderr,
    )
    sys.exit(1)

API_BASE = f"https://api.telegram.org/bot{QC_BOT_TOKEN}"

PLACEHOLDER = (
    "📍 <b>SDOS LIVE</b> — bootstrap\n"
    "\n"
    "Ce message sera rafraichi automatiquement toutes les 10 min par "
    "<code>crypto-quant-observer.service</code>.\n"
    "\n"
    "<i>Si tu vois ceci apres 15 min sans update, verifie :</i>\n"
    "  - <code>QC_PINNED_MSG_ID</code> dans <code>.env</code>\n"
    "  - <code>systemctl status crypto-quant-observer</code>\n"
    "  - <code>journalctl -u crypto-quant-observer -n 50</code>"
)


def _post(method: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{API_BASE}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main() -> int:
    # 1. Envoi
    print(f"[bootstrap] envoi placeholder au chat {QC_CHAT_ID} ...")
    try:
        res = _post(
            "sendMessage",
            {"chat_id": QC_CHAT_ID, "text": PLACEHOLDER, "parse_mode": "HTML"},
        )
    except Exception as exc:
        print(f"[ERREUR] envoi Telegram: {exc}", file=sys.stderr)
        return 2

    if not res.get("ok"):
        print(f"[ERREUR] Telegram a rejete l'envoi: {res}", file=sys.stderr)
        return 2

    message_id = res["result"]["message_id"]
    print(f"[bootstrap] message envoye — message_id = {message_id}")

    # 2. Tentative de pin (necessite bot admin)
    print("[bootstrap] tentative d'epinglage ...")
    try:
        pin_res = _post(
            "pinChatMessage",
            {
                "chat_id": QC_CHAT_ID,
                "message_id": message_id,
                "disable_notification": True,
            },
        )
        if pin_res.get("ok"):
            print("[bootstrap] pin OK — le bot etait admin du chat")
        else:
            print(
                f"[bootstrap] pin echoue (bot non-admin ?) : {pin_res.get('description')}"
            )
            print(
                "[bootstrap]   -> epingle le message a la main dans Telegram "
                "(clic long > Epingler)"
            )
    except Exception as exc:
        print(f"[bootstrap] pin echoue: {exc}")
        print("[bootstrap]   -> epingle le message a la main dans Telegram")

    # 3. Instructions finales
    print()
    print("=" * 60)
    print(f"[bootstrap] ID a copier dans .env :")
    print()
    print(f"    QC_PINNED_MSG_ID={message_id}")
    print()
    print("[bootstrap] puis relance le service :")
    print()
    print("    sudo systemctl restart crypto-quant-observer.service")
    print("    sudo systemctl status crypto-quant-observer.service")
    print("    journalctl -u crypto-quant-observer -n 30 --no-pager")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
