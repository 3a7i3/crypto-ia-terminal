"""
CompositeExitEngine — MVP minimaliste
Évalue plusieurs règles, log les décisions, retourne la première hit.
"""
from __future__ import annotations

from typing import Protocol
import json
from pathlib import Path
from datetime import datetime, timezone


class ExitRule(Protocol):
    def check(self, pos: dict, price: float, context: dict | None = None) -> str | None:
        ...


class CompositeExitEngine:
    """Multi-stack exit avec logging des décisions."""

    def __init__(self, rules: list[ExitRule], decision_log_file: Path | None = None):
        self.rules = rules
        self.decision_log_file = decision_log_file or Path("logs/exit_decisions.jsonl")

    def check(self, pos: dict, price: float, context: dict | None = None) -> dict | None:
        """
        Évalue toutes les règles, retourne la première décision (MVP).
        """
        decisions = []

        for rule in self.rules:
            result = rule.check(pos, price, context)
            if result:
                decisions.append({
                    "rule": rule.__class__.__name__,
                    "action": result,
                })

        if decisions:
            chosen = decisions[0]
            self._log_decision(pos, price, decisions, chosen)
            return chosen

        return None

    def check_exit(self, pos: dict, price: float, context: dict | None = None) -> str | None:
        """
        Interface compatible avec ExitEngine.
        Retourne la raison d'exit (string) ou None.
        """
        result = self.check(pos, price, context)
        if result:
            return result["action"]
        return None

    def check_path(
        self,
        pos: dict,
        price_path: list[float],
        context: dict | None = None,
    ) -> tuple[str | None, float]:
        """Interface compatible avec ExitEngine pour backtest."""
        simulated = dict(pos)
        for price in price_path:
            reason = self.check_exit(simulated, price, context)
            if reason:
                return reason, price
        fallback_price = price_path[-1] if price_path else float(pos.get("entry_price", 0))
        return None, fallback_price

    def _log_decision(
        self,
        pos: dict,
        price: float,
        decisions: list[dict],
        chosen: dict,
    ) -> None:
        """Log les décisions d'exit pour audit/debug/ML."""
        event = {
            "type": "exit_decision",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": pos.get("symbol"),
            "position_id": pos.get("id"),
            "entry_price": pos.get("entry_price"),
            "current_price": price,
            "pnl_pct": self._compute_pnl_pct(pos, price),
            "decisions_evaluated": decisions,
            "chosen": chosen,
            "regime": pos.get("regime"),
            "confidence": pos.get("confidence"),
        }

        self.decision_log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.decision_log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")

    @staticmethod
    def _compute_pnl_pct(pos: dict, price: float) -> float:
        """Calcule PnL % simplement."""
        entry = pos.get("entry_price", 0)
        if entry == 0:
            return 0.0
        side = pos.get("side", "BUY")
        if side == "BUY":
            return (price - entry) / entry
        else:
            return (entry - price) / entry
