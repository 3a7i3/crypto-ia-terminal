"""
watchdog_vps.py — Surveillance externe du bot advisor_loop

Tourne en boucle dans un screen séparé sur le VPS.
Lit live_snapshot.json toutes les INTERVAL secondes.
Si le snapshot est plus vieux que TIMEOUT secondes : alerte Telegram + log.

Usage VPS :
    screen -S watchdog python watchdog_vps.py

Variables d'env :
    WATCHDOG_INTERVAL   — intervalle de vérification en secondes (défaut: 60)
    WATCHDOG_TIMEOUT    — âge max du snapshot avant alerte (défaut: 300 = 5 min)
    WATCHDOG_SNAPSHOT   — chemin du snapshot (défaut: databases/live_snapshot.json)
    TELEGRAM_BOT_TOKEN  — token bot Telegram (optionnel)
    TELEGRAM_CHAT_ID    — chat ID Telegram (optionnel)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("watchdog")

INTERVAL = int(os.getenv("WATCHDOG_INTERVAL", "60"))
TIMEOUT = int(os.getenv("WATCHDOG_TIMEOUT", "300"))
SNAPSHOT_PATH = Path(os.getenv("WATCHDOG_SNAPSHOT", "databases/live_snapshot.json"))
AUDIT_LOG = Path("supervision/watchdog_audit.jsonl")
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        import urllib.request

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.warning("Telegram échoué: %s", exc)


def _log_event(event_type: str, detail: str, age_s: float | None = None) -> None:
    entry = {
        "ts": time.time(),
        "ts_human": _utcnow(),
        "event": event_type,
        "detail": detail,
    }
    if age_s is not None:
        entry["snapshot_age_s"] = round(age_s, 0)
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _check_snapshot() -> tuple[bool, str, float]:
    """
    Retourne (ok, message, age_secondes).
    ok=True si le bot est vivant, False sinon.
    """
    if not SNAPSHOT_PATH.exists():
        return False, f"Snapshot introuvable : {SNAPSHOT_PATH}", -1.0

    try:
        data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"Snapshot illisible : {exc}", -1.0

    snap_ts = data.get("ts", 0.0)
    if not snap_ts:
        return False, "Snapshot sans timestamp", -1.0

    age = time.time() - snap_ts
    cycle = data.get("cycle", "?")
    capital = data.get("capital", 0.0)

    if age > TIMEOUT:
        msg = (
            f"BOT INACTIF depuis {age:.0f}s (seuil: {TIMEOUT}s)\n"
            f"Dernier cycle : #{cycle} | Capital : ${capital:,.2f}\n"
            f"Snapshot : {SNAPSHOT_PATH}"
        )
        return False, msg, age

    return True, f"OK — cycle #{cycle} | age {age:.0f}s | capital ${capital:,.2f}", age


def run() -> None:
    logger.info(
        "Watchdog démarré — snapshot: %s | intervalle: %ss | timeout: %ss",
        SNAPSHOT_PATH,
        INTERVAL,
        TIMEOUT,
    )
    _log_event("WATCHDOG_START", f"intervalle={INTERVAL}s timeout={TIMEOUT}s")

    alert_sent = False  # évite les spams répétés
    consecutive_failures = 0

    while True:
        ok, msg, age = _check_snapshot()

        if ok:
            logger.info(msg)
            if alert_sent:
                # Récupération après panne
                recovery_msg = f"[WATCHDOG] Bot RÉTABLI — {msg}"
                logger.info("Bot rétabli !")
                _send_telegram(recovery_msg)
                _log_event("BOT_RECOVERED", msg, age)
            alert_sent = False
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            logger.warning("Bot inactif — %s (échec #%d)", msg, consecutive_failures)
            _log_event("BOT_DOWN", msg, age if age > 0 else None)

            if not alert_sent or consecutive_failures % 10 == 0:
                alert_text = (
                    f"🚨 [WATCHDOG] {msg}\n"
                    f"Heure : {_utcnow()}\n"
                    f"Échecs consécutifs : {consecutive_failures}\n"
                    "→ Vérifier le VPS : screen -r bot"
                )
                _send_telegram(alert_text)
                logger.warning("Alerte Telegram envoyée")
                alert_sent = True

        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Watchdog arrêté manuellement.")
        _log_event("WATCHDOG_STOP", "KeyboardInterrupt")
