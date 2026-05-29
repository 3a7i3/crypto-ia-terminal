"""
audit_trail.py — Piste d'audit SHA-256 chaînée (C-05)

Blockchain-style : chaque bloc contient le hash du bloc précédent.
Toute modification d'un bloc casse la chaîne et est détectée.

Format d'un bloc :
  {
    "index": int,
    "ts": float,
    "event": str,
    "data": dict,
    "prev_hash": str (hex SHA-256),
    "hash": str (hex SHA-256 de index+ts+event+data+prev_hash)
  }

Usage :
    trail = AuditTrail()
    trail.append("TRADE_EXECUTED", {"symbol": "BTC/USDT", "side": "BUY"})
    trail.append("RISK_OVERRIDE",  {"reason": "manual"})
    assert trail.verify_chain()
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from observability.json_logger import get_logger

_log = get_logger("crypto.audit_trail")

_TRAIL_PATH = Path(os.getenv("P10_AUDIT_TRAIL_PATH", "cache/startup/audit_trail.jsonl"))
_GENESIS_HASH = "0" * 64  # prev_hash du premier bloc


@dataclass
class AuditBlock:
    index: int
    ts: float
    event: str
    data: dict
    prev_hash: str
    hash: str = field(default="")

    def compute_hash(self) -> str:
        payload = json.dumps(
            {
                "index": self.index,
                "ts": self.ts,
                "event": self.event,
                "data": self.data,
                "prev_hash": self.prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def is_valid(self) -> bool:
        return self.hash == self.compute_hash()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "ts": self.ts,
            "event": self.event,
            "data": self.data,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AuditBlock":
        return cls(
            index=d["index"],
            ts=d["ts"],
            event=d["event"],
            data=d["data"],
            prev_hash=d["prev_hash"],
            hash=d["hash"],
        )


class AuditTrail:
    """
    Piste d'audit blockchain-style SHA-256.

    Certification C-05 :
      - Chaîne SHA-256 : prev_hash dans chaque bloc
      - Toute modification d'un bloc casse la chaîne
      - Vérification complète en O(n)
      - Persistance JSONL append-only
    """

    def __init__(self, trail_path: Optional[Path] = None) -> None:
        self._path = trail_path or _TRAIL_PATH
        self._blocks: List[AuditBlock] = []
        self._load()

    # ── API publique ──────────────────────────────────────────────────────────

    def append(self, event: str, data: Optional[dict] = None) -> AuditBlock:
        """Ajoute un bloc à la chaîne et le persiste."""
        prev_hash = self._blocks[-1].hash if self._blocks else _GENESIS_HASH
        block = AuditBlock(
            index=len(self._blocks),
            ts=round(time.time(), 6),
            event=event,
            data=data or {},
            prev_hash=prev_hash,
        )
        block.hash = block.compute_hash()
        self._blocks.append(block)
        self._persist(block)
        return block

    def verify_chain(self) -> bool:
        """
        Vérifie l'intégrité complète de la chaîne.
        Retourne False si un bloc est modifié ou si le chaînage est cassé.
        """
        if not self._blocks:
            return True

        # Premier bloc
        if not self._blocks[0].is_valid():
            _log.error("[AuditTrail] bloc #0 invalide")
            return False
        if self._blocks[0].prev_hash != _GENESIS_HASH:
            _log.error("[AuditTrail] bloc #0 prev_hash incorrect")
            return False

        for i in range(1, len(self._blocks)):
            blk = self._blocks[i]
            prev = self._blocks[i - 1]
            if not blk.is_valid():
                _log.error("[AuditTrail] bloc #%d invalide (hash corrompu)", i)
                return False
            if blk.prev_hash != prev.hash:
                _log.error("[AuditTrail] chaîne cassée entre #%d et #%d", i - 1, i)
                return False
            if blk.index != i:
                _log.error("[AuditTrail] index incorrect au bloc #%d", i)
                return False

        return True

    def find_tampered_block(self) -> Optional[int]:
        """Retourne l'index du premier bloc corrompu, ou None si chaîne intègre."""
        if not self._blocks:
            return None
        if not self._blocks[0].is_valid():
            return 0
        for i in range(1, len(self._blocks)):
            if (
                not self._blocks[i].is_valid()
                or self._blocks[i].prev_hash != self._blocks[i - 1].hash
            ):
                return i
        return None

    def blocks(self) -> List[AuditBlock]:
        return list(self._blocks)

    def __len__(self) -> int:
        return len(self._blocks)

    def last_hash(self) -> str:
        if not self._blocks:
            return _GENESIS_HASH
        return self._blocks[-1].hash

    # ── Persistance ───────────────────────────────────────────────────────────

    def _persist(self, block: AuditBlock) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(block.to_dict(), separators=(",", ":")) + "\n"
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    self._blocks.append(AuditBlock.from_dict(json.loads(raw)))
                except Exception as exc:
                    _log.warning("[AuditTrail] ligne ignorée (parse error): %s", exc)

    def reload(self) -> None:
        """Recharge la chaîne depuis le disque."""
        self._blocks.clear()
        self._load()
