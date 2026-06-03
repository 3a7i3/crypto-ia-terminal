"""
watchdog_vps.py — Démon de surveillance pour crypto_advisor (systemd Restart=always).
Vérifie toutes les 60s si core/advisor_loop.py tourne. Si mort, relance via vps_restart.sh.
"""

import logging
import os
import signal
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("watchdog")

CHECK_INTERVAL = 60  # secondes
RESTART_COOLDOWN = 120  # attente min entre deux redémarrages
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_last_restart: float = 0.0
_shutting_down = False


def _handle_signal(signum: int, _frame) -> None:
    global _shutting_down
    log.info("Signal %s reçu — arrêt propre", signum)
    _shutting_down = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _is_advisor_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "core/advisor_loop.py"], capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception as exc:
        log.warning("pgrep échoué: %s", exc)
        return False


def _restart_advisor() -> None:
    global _last_restart
    now = time.time()
    if now - _last_restart < RESTART_COOLDOWN:
        log.warning(
            "Redémarrage ignoré — cooldown actif (%ds restants)",
            int(RESTART_COOLDOWN - (now - _last_restart)),
        )
        return

    log.warning("advisor_loop absent — lancement via vps_restart.sh")
    restart_script = os.path.join(BASE_DIR, "scripts", "vps_restart.sh")
    try:
        result = subprocess.run(
            ["bash", restart_script],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=BASE_DIR,
        )
        log.info(
            "vps_restart.sh stdout: %s",
            result.stdout[-500:] if result.stdout else "(vide)",
        )
        if result.returncode != 0:
            log.error(
                "vps_restart.sh FAILED (code=%d): %s",
                result.returncode,
                result.stderr[-300:],
            )
        else:
            log.info("advisor_loop redémarré avec succès")
            _last_restart = time.time()
    except subprocess.TimeoutExpired:
        log.error("vps_restart.sh timeout (120s)")
    except Exception as exc:
        log.error("Erreur redémarrage: %s", exc)


def main() -> None:
    log.info(
        "Watchdog démarré (PID=%d, check_interval=%ds)", os.getpid(), CHECK_INTERVAL
    )
    while not _shutting_down:
        try:
            if not _is_advisor_running():
                _restart_advisor()
            else:
                log.debug("advisor_loop OK")
        except Exception as exc:
            log.error("Erreur watchdog: %s", exc)
        for _ in range(CHECK_INTERVAL):
            if _shutting_down:
                break
            time.sleep(1)
    log.info("Watchdog arrêté proprement")
    sys.exit(0)


if __name__ == "__main__":
    main()
