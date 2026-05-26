"""
multi_notifier.py — Diffuse les alertes vers plusieurs notificateurs.
"""

from __future__ import annotations

from typing import Any, List

from observability.json_logger import get_logger

_log = get_logger("MultiNotifier")


class MultiNotifier:
    def __init__(self, notifiers: List[Any]):
        self.notifiers = notifiers

    def notify(self, message: str) -> None:
        for notifier in self.notifiers:
            try:
                notifier.notify(message)
            except Exception as exc:
                _log.error("Erreur dans %s: %s", type(notifier).__name__, exc)
