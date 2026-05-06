"""Trailing stop — suit le prix quand il va dans le bon sens."""
from __future__ import annotations
from typing import Optional
from tracker_system.exit_engine.base import ExitRule


class TrailingStopRule(ExitRule):
    """
    Active un trailing stop dès que le trade atteint `activation_pct` de gain.
    Distance du trail = `trail_pct` depuis le max favorable.

    Exemple : activation=0.005, trail=0.005
      → activation si +0.5%, then trail à -0.5% du plus haut
    """

    def __init__(self, trail_pct: float = 0.005, activation_pct: float = 0.0) -> None:
        self.trail_pct      = trail_pct
        self.activation_pct = activation_pct

    def check(self, position: dict, price: float, context: dict | None = None) -> Optional[str]:
        entry     = position["entry_price"]
        direction = position["direction"]

        if direction == "long":
            pnl_pct = (price - entry) / entry
            # Toujours mettre à jour trail_max si déjà activé, ou si activation atteinte
            if pnl_pct >= self.activation_pct:
                position["trail_activated"] = True
            if not position.get("trail_activated"):
                return None
            position["trail_max"] = max(position.get("trail_max", price), price)
            trail_stop = position["trail_max"] * (1 - self.trail_pct)
            if price <= trail_stop:
                return f"TRAILING_STOP @ {price:.4f} (max={position['trail_max']:.4f})"
        else:
            pnl_pct = (entry - price) / entry
            if pnl_pct >= self.activation_pct:
                position["trail_activated"] = True
            if not position.get("trail_activated"):
                return None
            position["trail_min"] = min(position.get("trail_min", price), price)
            trail_stop = position["trail_min"] * (1 + self.trail_pct)
            if price >= trail_stop:
                return f"TRAILING_STOP @ {price:.4f} (min={position['trail_min']:.4f})"

        return None
