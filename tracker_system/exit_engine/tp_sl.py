"""Règle TP/SL fixe — utilise les niveaux posés à l'entrée."""
from __future__ import annotations
from typing import Optional
from tracker_system.exit_engine.base import ExitRule


class TPSLRule(ExitRule):
    """
    Sort si le prix atteint le stop_loss ou le take_profit enregistrés
    dans la position. Priorité au SL (risk management first).

    Si override_tp/sl sont fournis, ils remplacent les niveaux de la position
    (utile pour les tests avec paramètres dynamiques).
    """

    def __init__(
        self,
        tp_override: float | None = None,
        sl_override: float | None = None,
    ) -> None:
        self.tp_override = tp_override
        self.sl_override = sl_override

    def check(self, position: dict, price: float, context: dict | None = None) -> Optional[str]:
        entry     = position["entry_price"]
        direction = position["direction"]

        if self.sl_override and self.tp_override:
            # Paramètres en % relatif
            sl_price = entry * (1 - self.sl_override) if direction == "long" else entry * (1 + self.sl_override)
            tp_price = entry * (1 + self.tp_override) if direction == "long" else entry * (1 - self.tp_override)
        else:
            sl_price = position.get("stop_loss", 0)
            tp_price = position.get("take_profit", float("inf"))

        if direction == "long":
            if price <= sl_price:
                return f"SL_FIXED @ {price:.4f}"
            if price >= tp_price:
                return f"TP_FIXED @ {price:.4f}"
        else:
            if price >= sl_price:
                return f"SL_FIXED @ {price:.4f}"
            if price <= tp_price:
                return f"TP_FIXED @ {price:.4f}"

        return None
