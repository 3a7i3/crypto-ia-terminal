from __future__ import annotations

from typing import Protocol


class ExitRule(Protocol):
    def check(self, position: dict, price: float, context: dict | None = None) -> str | None:
        ...


class ExitEngine:
    def __init__(self, rules: list[ExitRule]) -> None:
        self.rules = rules

    def check_exit(self, position: dict, price: float, context: dict | None = None) -> str | None:
        for rule in self.rules:
            result = rule.check(position, price, context)
            if result:
                return result
        return None

    def check_path(self, position: dict, price_path: list[float], context: dict | None = None) -> tuple[str | None, float]:
        simulated = dict(position)
        for price in price_path:
            reason = self.check_exit(simulated, price, context)
            if reason:
                return reason, price
        fallback_price = price_path[-1] if price_path else float(position["entry_price"])
        return None, fallback_price