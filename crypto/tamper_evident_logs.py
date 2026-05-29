"""
tamper_evident_logs.py — Logs infalsifiables HMAC-SHA256 (C-06)

Chaque ligne est signée avec HMAC-SHA256.
Le hash de la ligne précédente est inclus dans le calcul du HMAC courant
(chaînage) : toute suppression ou insertion est détectée.

Format d'une ligne de log (JSON) :
  {
    "seq": int,
    "ts": float,
    "level": str,
    "message": str,
    "data": dict,
    "prev_hmac": str (hex),
    "hmac": str (hex HMAC-SHA256 de seq+ts+level+message+data+prev_hmac)
  }

Perf : 10 000 lignes vérifiées < 1 s (batch HMAC sans I/O).

Usage :
    log = TamperEvidentLog()
    log.write("INFO", "démarrage", {"version": "1.0"})
    log.write("TRADE", "BUY BTC", {"price": 50000})
    assert log.verify_all()
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from crypto.key_derivation import CTX_TAMPER_LOG, derive_key
from observability.json_logger import get_logger

_log = get_logger("crypto.tamper_evident_logs")

_LOG_PATH = Path(os.getenv("P10_TAMPER_LOG_PATH", "cache/startup/tamper_evident.jsonl"))
_GENESIS_HMAC = "0" * 64


@dataclass
class LogEntry:
    seq: int
    ts: float
    level: str
    message: str
    data: dict
    prev_hmac: str
    hmac: str = field(default="")

    def compute_hmac(self, key: bytes) -> str:
        payload = json.dumps(
            {
                "seq": self.seq,
                "ts": self.ts,
                "level": self.level,
                "message": self.message,
                "data": self.data,
                "prev_hmac": self.prev_hmac,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return _hmac.new(key, payload, hashlib.sha256).hexdigest()

    def is_valid(self, key: bytes) -> bool:
        return _hmac.compare_digest(self.hmac, self.compute_hmac(key))

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "level": self.level,
            "message": self.message,
            "data": self.data,
            "prev_hmac": self.prev_hmac,
            "hmac": self.hmac,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LogEntry":
        return cls(
            seq=d["seq"],
            ts=d["ts"],
            level=d["level"],
            message=d["message"],
            data=d.get("data", {}),
            prev_hmac=d["prev_hmac"],
            hmac=d["hmac"],
        )


class TamperEvidentLog:
    """
    Journal HMAC-SHA256 chaîné — infalsifiable et append-only.

    Certification C-06 :
      - HMAC-SHA256 par ligne (clé dérivée du master_secret)
      - prev_hmac dans chaque ligne (chaînage)
      - Suppression ou insertion de ligne détectée
      - 10 000 lignes vérifiées < 1 s
    """

    def __init__(
        self,
        master_secret: Optional[bytes] = None,
        log_path: Optional[Path] = None,
    ) -> None:
        self._path = log_path or _LOG_PATH
        self._key = derive_key(CTX_TAMPER_LOG, master_secret=master_secret)
        self._entries: List[LogEntry] = []
        self._load()

    # ── API publique ──────────────────────────────────────────────────────────

    def write(self, level: str, message: str, data: Optional[dict] = None) -> LogEntry:
        """Ajoute une entrée signée et chaînée."""
        prev_hmac = self._entries[-1].hmac if self._entries else _GENESIS_HMAC
        entry = LogEntry(
            seq=len(self._entries),
            ts=round(time.time(), 6),
            level=level.upper(),
            message=message,
            data=data or {},
            prev_hmac=prev_hmac,
        )
        entry.hmac = entry.compute_hmac(self._key)
        self._entries.append(entry)
        self._persist(entry)
        return entry

    def verify_all(self) -> bool:
        """
        Vérifie l'intégrité complète du journal.
        Retourne False si un HMAC est invalide ou si le chaînage est cassé.
        10 000 lignes < 1 s (HMAC-SHA256 batch).
        """
        if not self._entries:
            return True

        if not self._entries[0].is_valid(self._key):
            _log.error("[TamperEvidentLog] entrée #0 HMAC invalide")
            return False
        if self._entries[0].prev_hmac != _GENESIS_HMAC:
            _log.error("[TamperEvidentLog] entrée #0 prev_hmac incorrect")
            return False

        for i in range(1, len(self._entries)):
            e = self._entries[i]
            prev = self._entries[i - 1]
            if not e.is_valid(self._key):
                _log.error("[TamperEvidentLog] entrée #%d HMAC invalide", i)
                return False
            if not _hmac.compare_digest(e.prev_hmac, prev.hmac):
                _log.error(
                    "[TamperEvidentLog] chaîne cassée entre #%d et #%d", i - 1, i
                )
                return False
            if e.seq != i:
                _log.error("[TamperEvidentLog] seq incorrect à l'entrée #%d", i)
                return False

        return True

    def find_tampered_entry(self) -> Optional[int]:
        """Retourne le seq de la première entrée corrompue, ou None si intègre."""
        if not self._entries:
            return None
        if not self._entries[0].is_valid(self._key):
            return 0
        for i in range(1, len(self._entries)):
            e = self._entries[i]
            prev = self._entries[i - 1]
            if not e.is_valid(self._key) or not _hmac.compare_digest(
                e.prev_hmac, prev.hmac
            ):
                return i
        return None

    def entries(self) -> List[LogEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def last_hmac(self) -> str:
        if not self._entries:
            return _GENESIS_HMAC
        return self._entries[-1].hmac

    # ── Persistance ───────────────────────────────────────────────────────────

    def _persist(self, entry: LogEntry) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.to_dict(), separators=(",", ":")) + "\n"
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
                    self._entries.append(LogEntry.from_dict(json.loads(raw)))
                except Exception as exc:
                    _log.warning("[TamperEvidentLog] ligne ignorée: %s", exc)

    def reload(self) -> None:
        self._entries.clear()
        self._load()
