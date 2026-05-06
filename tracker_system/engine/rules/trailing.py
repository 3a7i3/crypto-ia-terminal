from __future__ import annotations

from tracker_system.engine.rules.tp_sl import _is_long


class TrailingStopRule:
    def __init__(self, trail_pct: float = 0.005) -> None:
        self.trail_pct = float(trail_pct)

    def check(self, position: dict, price: float, context: dict | None = None) -> str | None:
        current_price = float(price)
        entry = float(position["entry_price"])

        if _is_long(position.get("side")):
            position["max_price"] = max(float(position.get("max_price", entry)), current_price)
            if current_price < float(position["max_price"]) * (1.0 - self.trail_pct):
                return f"TRAILING @ {current_price:.8f}"
        else:
            position["min_price"] = min(float(position.get("min_price", entry)), current_price)
            if current_price > float(position["min_price"]) * (1.0 + self.trail_pct):
                return f"TRAILING @ {current_price:.8f}"
        return None