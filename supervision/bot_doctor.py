"""
bot_doctor.py — Superviseur de modules avec détection de pannes et auto-heal.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional

logger = logging.getLogger("BotDoctor")


class ModuleStatus:
    def __init__(self, name: str, is_healthy: bool):
        self.name = name
        self.is_healthy = is_healthy
        self.last_checked = datetime.utcnow().isoformat()
        self.error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "is_healthy": self.is_healthy,
            "last_checked": self.last_checked,
            "error": self.error,
        }


class BotDoctor:
    """Superviseur de modules: vérifie leur santé et déclenche des alertes."""

    def __init__(self, modules: List[Any], notifier: Optional[Any] = None):
        self.modules = modules
        self.notifier = notifier
        self.statuses: List[ModuleStatus] = []

    def check_module(self, module: Any) -> ModuleStatus:
        name = getattr(module, "name", str(module))
        try:
            raw = getattr(module, "is_healthy", True)
            healthy = bool(raw() if callable(raw) else raw)
            status = ModuleStatus(name, healthy)
            if not healthy:
                status.error = f"Module {name} reported unhealthy"
        except Exception as exc:
            status = ModuleStatus(name, False)
            status.error = str(exc)
        return status

    def run(self) -> List[ModuleStatus]:
        self.statuses = [self.check_module(m) for m in self.modules]
        for status in self.statuses:
            if not status.is_healthy:
                msg = f"[BotDoctor] ALERTE — {status.name}: {status.error}"
                logger.warning(msg)
                if self.notifier:
                    try:
                        self.notifier.notify(msg)
                    except Exception as exc:
                        logger.error("Erreur notifier: %s", exc)
        return self.statuses

    @property
    def health_score(self) -> float:
        """Pourcentage de modules sains (0.0–100.0). Retourne 100.0 si aucun module."""
        if not self.statuses:
            return 100.0
        healthy = sum(1 for s in self.statuses if s.is_healthy)
        return round(healthy / len(self.statuses) * 100, 2)

    def get_report(self) -> List[dict]:
        return [s.to_dict() for s in self.statuses]
