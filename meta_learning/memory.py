"""
Meta Memory — Storage des decisions et performances
Stocke: context + decision + performance
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    timestamp: str
    context: dict[str, Any]
    decision: dict[str, Any]
    performance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MetaMemory:
    def __init__(self, memory_file: Path | None = None):
        self.memory_file = memory_file or Path("logs/meta_memory.jsonl")
        self.memory: list[MemoryEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.memory_file.exists():
            return
        try:
            import json
            with open(self.memory_file, "r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        self.memory.append(MemoryEntry(**data))
        except Exception:
            pass

    def add(self, context: dict[str, Any], decision: dict[str, Any], performance: dict[str, Any]) -> None:
        entry = MemoryEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            context=dict(context),
            decision=dict(decision),
            performance=dict(performance),
        )
        self.memory.append(entry)
        self._save_entry(entry)

    def _save_entry(self, entry: MemoryEntry) -> None:
        import json
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.memory_file, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def get_all(self) -> list[MemoryEntry]:
        return self.memory

    def get_by_regime(self, regime: str) -> list[MemoryEntry]:
        return [e for e in self.memory if e.context.get("regime") == regime]
