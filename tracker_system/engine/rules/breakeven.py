from __future__ import annotations

from tracker_system.engine.rules.tp_sl import _is_long


class BreakEvenRule:
    def __init__(self, trigger_pct: float = 0.01, buffer_pct: float = 0.0) -> None:
        self.trigger_pct = float(trigger_pct)
        self.buffer_pct = float(buffer_pct)

    def check(self, position: dict, price: float, context: dict | None = None) -> str | None:
        current_price = float(price)
        entry = float(position["entry_price"])

        if _is_long(position.get("side")):
            pnl_pct = (current_price - entry) / entry
            if pnl_pct >= self.trigger_pct:
                position["breakeven_stop"] = entry * (1.0 + self.buffer_pct)
            if current_price <= float(position.get("breakeven_stop", float("-inf"))):
                return f"BREAKEVEN @ {current_price:.8f}"
        else:
            pnl_pct = (entry - current_price) / entry
            if pnl_pct >= self.trigger_pct:
                position["breakeven_stop"] = entry * (1.0 - self.buffer_pct)
            if current_price >= float(position.get("breakeven_stop", float("inf"))):
                return f"BREAKEVEN @ {current_price:.8f}"
        return None
