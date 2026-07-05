"""
watchdog_vps.py — Démon de surveillance pour core/advisor_loop.py (systemd Restart=always).

Vérifie toutes les CHECK_INTERVAL secondes si le moteur réel tourne (motif
ancré core/advisor_loop.py — jamais de sous-chaîne, cf. DS-002 ci-dessous).
S'il est mort :
  - RESTART_DISABLED_UNTIL_RECONCILIATION=1 (défaut, .env) : mode ALERTE
    SEULE — aucune relance automatique, Telegram + log structuré, répété
    toutes les DEAD_ALERT_REPEAT_S secondes tant que non résolu. Voir
    RECOVERY.md pour la reprise manuelle.
  - =0 (uniquement après réconciliation main/feat-stack-unification) :
    relance via scripts/vps_restart.sh, mais seulement si core/advisor_loop.py
    existe sur disque et a une syntaxe valide (refus bruyant sinon — mieux
    vaut un échec explicite qu'un moteur remplacé silencieusement par un
    processus mort).

DS-002 (incident 2026-07-04) : l'ancien pkill/pgrep "-f advisor_loop.py" (sans
ancrage) matchait indifféremment core/advisor_loop.py (moteur réel) et
advisor_loop.py racine (bot d'observation passif, géré séparément par
systemd crypto_advisor.service — Restart=always, sans rapport avec ce
watchdog, aucun conflit possible puisque les cibles sont disjointes).
"""

from __future__ import annotations

import ast
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("watchdog")

CHECK_INTERVAL = int(os.getenv("WATCHDOG_INTERVAL", "60"))  # secondes
RESTART_COOLDOWN = int(os.getenv("WATCHDOG_RESTART_COOLDOWN", "120"))
DEAD_ALERT_REPEAT_S = int(os.getenv("WATCHDOG_DEAD_ALERT_REPEAT_S", "900"))  # 15 min
BASE_DIR = Path(__file__).resolve().parent
AUDIT_LOG = BASE_DIR / "supervision" / "watchdog_audit.jsonl"
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

# Cible ancrée — jamais de sous-chaîne (DS-002). "core/advisor_loop.py$"
# exclut par construction advisor_loop.py racine (bot passif).
ENGINE_PGREP_PATTERN = r"core/advisor_loop\.py$"
ENGINE_SCRIPT = BASE_DIR / "core" / "advisor_loop.py"

_last_restart: float = 0.0
_last_dead_alert: float = 0.0
_shutting_down = False


def _handle_signal(signum: int, _frame) -> None:
    global _shutting_down
    log.info("Signal %s reçu — arrêt propre", signum)
    _shutting_down = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _restart_disabled() -> bool:
    """Lu à chaque décision, jamais figé à l'import — .env est la source de
    vérité UNIQUE, partagée avec scripts/deploy_vps.sh --restart."""
    return os.getenv("RESTART_DISABLED_UNTIL_RECONCILIATION", "1").strip() == "1"


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
        log.warning("Telegram échoué: %s", exc)


def _log_event(event: str, detail: str) -> None:
    entry = {
        "ts": time.time(),
        "ts_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "event": event,
        "detail": detail,
    }
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _is_engine_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", ENGINE_PGREP_PATTERN], capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception as exc:
        log.warning("pgrep échoué: %s", exc)
        return False


def _engine_file_ok() -> tuple[bool, str]:
    """Refus bruyant si le script cible est absent ou syntaxiquement invalide
    — mieux vaut un échec explicite qu'un moteur silencieusement mort."""
    if not ENGINE_SCRIPT.exists():
        return False, f"{ENGINE_SCRIPT} introuvable sur disque"
    try:
        ast.parse(ENGINE_SCRIPT.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return False, f"{ENGINE_SCRIPT} syntaxe invalide: {exc}"
    return True, "ok"


def _alert_dead_no_restart() -> None:
    """Mode ALERTE SEULE (RESTART_DISABLED_UNTIL_RECONCILIATION=1) — ne
    relance RIEN automatiquement. Voir RECOVERY.md pour la reprise manuelle."""
    global _last_dead_alert
    now = time.time()
    if now - _last_dead_alert < DEAD_ALERT_REPEAT_S:
        return
    msg = (
        "[WATCHDOG] MOTEUR MORT — relance automatique désactivée "
        "(RESTART_DISABLED_UNTIL_RECONCILIATION=1)\n"
        "Suivre RECOVERY.md pour la procédure de reprise manuelle."
    )
    log.critical(msg)
    _send_telegram(msg)
    _log_event("ENGINE_DEAD_NO_AUTO_RESTART", msg)
    _last_dead_alert = now


def _restart_advisor() -> None:
    """Relance autorisée uniquement après réconciliation
    (RESTART_DISABLED_UNTIL_RECONCILIATION=0), et seulement si le fichier
    cible existe sur disque avec une syntaxe valide."""
    global _last_restart
    now = time.time()
    if now - _last_restart < RESTART_COOLDOWN:
        log.warning(
            "Redémarrage ignoré — cooldown actif (%ds restants)",
            int(RESTART_COOLDOWN - (now - _last_restart)),
        )
        return

    ok, reason = _engine_file_ok()
    if not ok:
        msg = f"[WATCHDOG] Redémarrage refusé — {reason}"
        log.critical(msg)
        _send_telegram(msg)
        _log_event("RESTART_REFUSED", reason)
        return

    log.warning(
        "core/advisor_loop.py absent des process — lancement via vps_restart.sh"
    )
    restart_script = BASE_DIR / "scripts" / "vps_restart.sh"
    try:
        result = subprocess.run(
            ["bash", str(restart_script)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BASE_DIR),
        )
        log.info(
            "vps_restart.sh stdout: %s",
            result.stdout[-500:] if result.stdout else "(vide)",
        )
        if result.returncode != 0:
            msg = (
                f"[WATCHDOG] vps_restart.sh ÉCHOUÉ (code={result.returncode}): "
                f"{result.stderr[-300:]}"
            )
            log.error(msg)
            _send_telegram(msg)
            _log_event("RESTART_FAILED", msg)
        else:
            msg = "[WATCHDOG] Moteur redémarré avec succès (core/advisor_loop.py)"
            log.info(msg)
            _send_telegram(msg)
            _log_event("RESTART_OK", msg)
            _last_restart = time.time()
    except subprocess.TimeoutExpired:
        log.error("vps_restart.sh timeout (120s)")
        _log_event("RESTART_TIMEOUT", "vps_restart.sh > 120s")
    except Exception as exc:
        log.error("Erreur redémarrage: %s", exc)
        _log_event("RESTART_ERROR", str(exc))


def _tick() -> None:
    """Une itération de décision — isolée de la boucle infinie pour être
    testable directement (voir tests/test_watchdog_vps.py)."""
    if not _is_engine_running():
        if _restart_disabled():
            _alert_dead_no_restart()
        else:
            _restart_advisor()
    else:
        log.debug("core/advisor_loop.py OK")


def main() -> None:
    log.info(
        "Watchdog démarré (PID=%d, check_interval=%ds, cible=%s, disabled=%s)",
        os.getpid(),
        CHECK_INTERVAL,
        ENGINE_PGREP_PATTERN,
        _restart_disabled(),
    )
    _log_event(
        "WATCHDOG_START",
        f"pid={os.getpid()} restart_disabled={_restart_disabled()}",
    )
    while not _shutting_down:
        try:
            _tick()
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
