"""
custom_module.py — Module de trading personnalisé pour la supervision.

Exemple d'utilisation:
    module = CustomTradingModule("MonBot", is_healthy=True)
"""

from __future__ import annotations


class CustomTradingModule:
    """Module de trading supervisable par BotDoctor."""

    def __init__(self, name: str, is_healthy: bool = True):
        self.name = name
        self.is_healthy = is_healthy

    def health_check(self) -> bool:
        return self.is_healthy
