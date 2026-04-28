"""
logging_alerts.py — Logging centralisé avec support d'alertes optionnelles.

Interface publique:
    logger       : logging.Logger — logger du système quant
    logging      : module stdlib logging (exposé pour faciliter les tests/patches)
    log_and_alert(level, message, alert=False, notifier=None)
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Optional

logger = logging.getLogger("quant_system")

if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)

_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def log_and_alert(
    level: str,
    message: str,
    alert: bool = False,
    notifier: Optional[Any] = None,
) -> None:
    """Log un message et déclenche éventuellement une alerte.

    Args:
        level:    Niveau de log ('info', 'warning', 'error', 'critical', 'debug').
        message:  Texte du message.
        alert:    Si True, transmet le message au notifier (si fourni).
        notifier: Objet avec méthode .notify(str) — ex. MultiNotifier.
    """
    lvl = _LEVEL_MAP.get(level.lower(), logging.INFO)
    logger.log(lvl, message)

    if alert and notifier is not None:
        try:
            notifier.notify(f"[{level.upper()}] {message}")
        except Exception as exc:
            logger.error("Erreur notifier dans log_and_alert: %s", exc)
