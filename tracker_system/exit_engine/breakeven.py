"""Break-even rule — déplace le SL à l'entrée quand le trade est en profit."""
from __future__ import annotations
from typing import Optional
from tracker_system.exit_engine.base import ExitRule


class BreakEvenRule(ExitRule):
    """
    Dès que le trade atteint `trigger_pct` de gain, place un stop
    à `buffer_pct` au-dessus de l'entrée (pour couvrir les frais).

    Exemple : trigger=0.01, buffer=0.001
      → si +1% : stop à entry + 0.1%
    """

    def __init__(self, trigger_pct: float = 0.01, buffer_pct: float = 0.001) -> None:
        self.trigger_pct = trigger_pct
        self.buffer_pct  = buffer_pct

    def check(self, position: dict, price: float, context: dict | None = None) -> Optional[str]:
        entry     = position["entry_price"]
        direction = position["direction"]

        if direction == "long":
            pnl_pct = (price - entry) / entry
            if pnl_pct >= self.trigger_pct:
                position["breakeven_active"] = True
                position["breakeven_stop"]   = entry * (1 + self.buffer_pct)
            if position.get("breakeven_active") and price <= position["breakeven_stop"]:
                return f"BREAKEVEN @ {price:.4f}"
        else:
            pnl_pct = (entry - price) / entry
            if pnl_pct >= self.trigger_pct:
                position["breakeven_active"] = True
                position["breakeven_stop"]   = entry * (1 - self.buffer_pct)
            if position.get("breakeven_active") and price >= position["breakeven_stop"]:
                return f"BREAKEVEN @ {price:.4f}"

        return None
