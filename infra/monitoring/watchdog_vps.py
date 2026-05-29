"""
watchdog_vps.py — Surveillance + redémarrage automatique du bot advisor_loop.

Tourne en boucle dans un screen séparé (ou géré par systemd) sur le VPS.
Lit live_snapshot.json toutes les INTERVAL secondes.
Si le snapshot est plus vieux que TIMEOUT secondes :
  1. Envoie une alerte Telegram
  2. Envoie un email de notification
  3. Tue le processus zombie éventuel (pkill)
  4. Redémarre advisor_loop.py automatiquement
  5. Envoie une confirmation de redémarrage

Usage VPS :
    screen -S watchdog python watchdog_vps.py

Variables d'env :
    WATCHDOG_INTERVAL   — intervalle de vérification en secondes (défaut: 60)
    WATCHDOG_TIMEOUT    — âge max du snapshot avant action (défaut: 300 = 5 min)
    WATCHDOG_SNAPSHOT   — chemin du snapshot (défaut: databases/live_snapshot.json)
    WATCHDOG_MAX_RESTARTS — redémarrages max avant abandon (défaut: 10)
    WATCHDOG_RESTART_DELAY — délai avant redémarrage en secondes (défaut: 15)
    TELEGRAM_BOT_TOKEN  — token bot Telegram
    TELEGRAM_CHAT_ID    — chat ID Telegram
    EMAIL_SMTP_SERVER / EMAIL_FROM_ADDR / EMAIL_SMTP_PASS / EMAIL_TO_ADDR
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import subprocess
import sys
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("watchdog")

INTERVAL = int(os.getenv("WATCHDOG_INTERVAL", "60"))
TIMEOUT = int(os.getenv("WATCHDOG_TIMEOUT", "300"))
SNAPSHOT_PATH = Path(os.getenv("WATCHDOG_SNAPSHOT", "databases/live_snapshot.json"))
MAX_RESTARTS = int(os.getenv("WATCHDOG_MAX_RESTARTS", "10"))
RESTART_DELAY = int(os.getenv("WATCHDOG_RESTART_DELAY", "15"))
USE_SYSTEMD = os.getenv("WATCHDOG_USE_SYSTEMD", "0") == "1"
RAM_ALERT_MB = int(os.getenv("WATCHDOG_RAM_ALERT_MB", "2048"))  # alert si RSS > 2 GB
RAM_RESTART_MB = int(
    os.getenv("WATCHDOG_RAM_RESTART_MB", "3072")
)  # restart si RSS > 3 GB
AUDIT_LOG = Path("supervision/watchdog_audit.jsonl")
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

BOT_SCRIPT = Path(__file__).parent / "advisor_loop.py"
PYTHON_BIN = Path(__file__).parent / ".venv" / "bin" / "python"
if not PYTHON_BIN.exists():
    PYTHON_BIN = Path(sys.executable)

_bot_process: subprocess.Popen | None = None
_restart_count = 0


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


def _send_email(subject: str, body: str) -> None:
    smtp_server = os.getenv("EMAIL_SMTP_SERVER", "")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    from_addr = os.getenv("EMAIL_FROM_ADDR", "")
    smtp_pass = os.getenv("EMAIL_SMTP_PASS", "")
    to_addr = os.getenv("EMAIL_TO_ADDR", "")
    if not all([smtp_server, from_addr, smtp_pass, to_addr]):
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[Crypto AI Watchdog] {subject}"
        msg["From"] = from_addr
        msg["To"] = to_addr
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as srv:
            srv.starttls()
            srv.login(from_addr, smtp_pass)
            srv.sendmail(from_addr, [to_addr], msg.as_string())
        logger.info("Email envoyé : %s", subject)
    except Exception as exc:
        logger.warning("Email échoué: %s", exc)


def _log_event(event_type: str, detail: str, age_s: float | None = None) -> None:
    entry: dict = {
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


def _kill_zombie() -> None:
    """Tue proprement tout processus advisor_loop.py zombie."""
    global _bot_process
    if _bot_process is not None:
        try:
            _bot_process.terminate()
            try:
                _bot_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _bot_process.kill()
        except Exception as exc:
            logger.warning("Impossible de tuer le processus géré: %s", exc)
        _bot_process = None

    # Tuer tout processus zombie par nom (cas où watchdog redémarre)
    try:
        subprocess.run(
            ["pkill", "-f", "advisor_loop.py"],
            timeout=5,
            check=False,
        )
        time.sleep(2)
    except Exception:
        pass


def _start_bot() -> bool:
    """Redémarre advisor_loop.py. Retourne True si succès."""
    global _bot_process, _restart_count

    if _restart_count >= MAX_RESTARTS:
        msg = (
            f"WATCHDOG ABANDON — {_restart_count} redémarrages atteints.\n"
            f"Intervention manuelle requise."
        )
        logger.critical(msg)
        _send_telegram(msg)
        _send_email("ABANDON — trop de redémarrages", msg)
        _log_event("WATCHDOG_GIVE_UP", msg)
        return False

    _restart_count += 1

    if USE_SYSTEMD:
        try:
            subprocess.run(
                ["sudo", "systemctl", "restart", "crypto_advisor.service"],
                timeout=30,
                check=True,
            )
            logger.info("Bot redémarré via systemd (restart #%d)", _restart_count)
            return True
        except Exception as exc:
            logger.error("systemctl restart échoué: %s", exc)
            return False

    log_out = open("logs/advisor_loop_stdout.log", "a", encoding="utf-8")
    log_err = open("logs/advisor_loop_stderr.log", "a", encoding="utf-8")
    try:
        _bot_process = subprocess.Popen(
            [str(PYTHON_BIN), str(BOT_SCRIPT)],
            cwd=str(BOT_SCRIPT.parent),
            stdout=log_out,
            stderr=log_err,
        )
        logger.info(
            "Bot démarré (PID=%d, restart #%d)", _bot_process.pid, _restart_count
        )
        return True
    except Exception as exc:
        logger.error("Impossible de démarrer le bot: %s", exc)
        return False


def _check_snapshot() -> tuple[bool, str, float]:
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
        return (
            False,
            f"BOT INACTIF depuis {age:.0f}s (seuil: {TIMEOUT}s)"
            f" | cycle #{cycle} | ${capital:,.2f}",
            age,
        )
    return True, f"OK — cycle #{cycle} | age {age:.0f}s | ${capital:,.2f}", age


def _get_bot_ram_mb() -> int:
    """Retourne la RAM RSS du processus advisor_loop en MB, ou 0 si indisponible."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "advisor_loop.py"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = result.stdout.strip().split()
        if not pids:
            return 0
        total_kb = 0
        for pid in pids:
            try:
                status = Path(f"/proc/{pid}/status").read_text()
                for line in status.splitlines():
                    if line.startswith("VmRSS:"):
                        total_kb += int(line.split()[1])
                        break
            except Exception:
                pass
        return total_kb // 1024
    except Exception:
        return 0


def _is_bot_alive() -> bool:
    """Vérifie si le processus bot géré est encore vivant."""
    global _bot_process
    if _bot_process is None:
        return False
    poll = _bot_process.poll()
    if poll is not None:
        logger.warning("Bot process terminé (code=%d)", poll)
        _bot_process = None
        return False
    return True


def run() -> None:
    global _restart_count
    logger.info(
        "Watchdog démarré — snapshot: %s | intervalle: %ss"
        " | timeout: %ss | max_restarts: %d",
        SNAPSHOT_PATH,
        INTERVAL,
        TIMEOUT,
        MAX_RESTARTS,
    )
    _log_event(
        "WATCHDOG_START",
        f"intervalle={INTERVAL}s timeout={TIMEOUT}s max_restarts={MAX_RESTARTS}",
    )
    _send_email(
        "Watchdog démarré",
        f"Le watchdog Crypto AI est actif.\n"
        f"Surveillance toutes les {INTERVAL}s, timeout {TIMEOUT}s.",
    )

    alert_sent = False
    consecutive_failures = 0
    # Période de grâce au démarrage : le bot met ~2 min à écrire son premier snapshot
    _startup_grace = int(os.getenv("WATCHDOG_STARTUP_GRACE", "300"))
    _started_at = time.time()

    while True:
        # Ne pas intervenir pendant la période de grâce post-démarrage watchdog
        if time.time() - _started_at < _startup_grace:
            logger.info(
                "Grace period — %ds restants",
                int(_startup_grace - (time.time() - _started_at)),
            )
            time.sleep(INTERVAL)
            continue

        ok, msg, age = _check_snapshot()

        # ── RAM monitoring ───────────────────────────────────────────────────
        _ram_mb = _get_bot_ram_mb()
        if _ram_mb > 0:
            logger.info("RAM bot: %d MB", _ram_mb)
            _log_event("RAM_CHECK", f"{_ram_mb} MB")
            if _ram_mb > RAM_RESTART_MB:
                _ram_msg = (
                    f"[WATCHDOG] RAM critique : {_ram_mb} MB > {RAM_RESTART_MB} MB\n"
                    f"Redémarrage forcé — {_utcnow()}"
                )
                logger.critical(_ram_msg)
                _send_telegram(_ram_msg)
                _send_email("RAM critique — redémarrage", _ram_msg)
                _log_event("RAM_RESTART", f"{_ram_mb} MB")
                _kill_zombie()
                time.sleep(RESTART_DELAY)
                _start_bot()
                time.sleep(TIMEOUT // 2)
            elif _ram_mb > RAM_ALERT_MB:
                _ram_alert = (
                    f"[WATCHDOG] RAM élevée : {_ram_mb} MB"
                    f" > {RAM_ALERT_MB} MB — {_utcnow()}"
                )
                logger.warning(_ram_alert)
                _send_telegram(_ram_alert)
                _log_event("RAM_ALERT", f"{_ram_mb} MB")

        if ok:
            logger.info(msg)
            if alert_sent:
                recovery_msg = f"[WATCHDOG] Bot RÉTABLI — {msg}"
                logger.info("Bot rétabli !")
                _send_telegram(recovery_msg)
                _send_email("Bot rétabli", recovery_msg)
                _log_event("BOT_RECOVERED", msg, age)
                _restart_count = 0  # reset compteur après récupération réussie
            alert_sent = False
            consecutive_failures = 0

        else:
            consecutive_failures += 1
            logger.warning("Bot inactif — %s (échec #%d)", msg, consecutive_failures)
            _log_event("BOT_DOWN", msg, age if age > 0 else None)

            # Alerte + email
            if not alert_sent or consecutive_failures % 10 == 0:
                alert_text = (
                    f"[WATCHDOG] {msg}\n"
                    f"Heure : {_utcnow()}\n"
                    f"Échecs consécutifs : {consecutive_failures}\n"
                    f"Redémarrage automatique dans {RESTART_DELAY}s..."
                )
                _send_telegram(alert_text)
                if not alert_sent:
                    _send_email("BOT DOWN — redémarrage en cours", alert_text)
                logger.warning("Alerte envoyée")
                alert_sent = True

            # Redémarrage automatique après 2 échecs consécutifs
            if consecutive_failures >= 2:
                logger.warning(
                    "Redémarrage automatique (échec #%d)...", consecutive_failures
                )
                _kill_zombie()
                time.sleep(RESTART_DELAY)

                if _start_bot():
                    restart_msg = (
                        f"[WATCHDOG] Bot redémarré (tentative #{_restart_count})\n"
                        f"PID : {_bot_process.pid if _bot_process else '?'}\n"
                        f"Heure : {_utcnow()}"
                    )
                    _send_telegram(restart_msg)
                    _send_email(f"Bot redémarré (#{_restart_count})", restart_msg)
                    _log_event(
                        "BOT_RESTARTED",
                        f"restart #{_restart_count}",
                    )
                    # Attendre que le bot produise son premier snapshot
                    time.sleep(TIMEOUT // 2)
                    consecutive_failures = 0
                    alert_sent = False
                else:
                    # MAX_RESTARTS atteint — watchdog s'arrête
                    break

        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Watchdog arrêté manuellement.")
        _log_event("WATCHDOG_STOP", "KeyboardInterrupt")
        _send_email("Watchdog arrêté", "Le watchdog a été arrêté manuellement.")
