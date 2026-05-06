"""
ExitEngine — Compose plusieurs règles d'exit, retourne la première qui se déclenche.

Usage:
    engine = ExitEngine([
        TPSLRule(),
        TrailingStopRule(trail_pct=0.005, activation_pct=0.01),
        BreakEvenRule(trigger_pct=0.01),
    ])
    reason = engine.check(position, current_price)
    if reason:
        close_position(...)
"""
from __future__ import annotations
from typing import Optional
from tracker_system.exit_engine.base import ExitRule


class ExitEngine:
    def __init__(self, rules: list[ExitRule]) -> None:
        self.rules = rules

    def check(
        self, position: dict, price: float, context: dict | None = None
    ) -> Optional[str]:
        """Parcourt les règles dans l'ordre, retourne la première raison de sortie."""
        for rule in self.rules:
            reason = rule.check(position, price, context)
            if reason:
                return reason
        return None

    def check_path(
        self, position: dict, price_path: list[float], context: dict | None = None
    ) -> tuple[Optional[str], float]:
        """
        Simule le trade sur un price_path complet.
        Retourne (raison_exit, prix_exit) ou (None, dernier_prix).
        Utile pour le backtester.
        """
        import copy
        sim_pos = copy.deepcopy(position)
        for price in price_path:
            reason = self.check(sim_pos, price, context)
            if reason:
                return reason, price
        last_price = price_path[-1] if price_path else position["entry_price"]
        return None, last_price
