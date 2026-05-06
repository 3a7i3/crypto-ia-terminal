"""
meta_memory.py — Mémoire persistante des décisions de trading par contexte

Format d'une entrée :
    {
        "context":    {"regime": "bull_trend", "volatility_bucket": "medium"},
        "decision":   {"exit_type": "tp_sl", "tp": 0.02, "sl": 0.01, "trail_pct": null},
        "performance":{"sharpe": 1.9, "win_rate": 0.64, "avg_pnl": 0.012, "n_trades": 50}
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("logs/meta_memory.json")


class MetaMemory:
    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = path
        self.memory: list[dict[str, Any]] = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.memory, indent=2), encoding="utf-8")

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, context: dict, decision: dict, performance: dict) -> None:
        """Ajoute ou met à jour une entrée (même contexte exact → update)."""
        for entry in self.memory:
            if entry["context"] == context:
                entry["decision"] = decision
                entry["performance"] = performance
                self.save()
                return
        self.memory.append({
            "context": context,
            "decision": decision,
            "performance": performance,
        })
        self.save()

    def all(self) -> list[dict]:
        return list(self.memory)

    def __len__(self) -> int:
        return len(self.memory)
