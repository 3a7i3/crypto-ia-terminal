"""
certification/immutable_stamp.py — G-02
Scellement immuable par module.

Pour chaque module certifié (G-01) :
  - SHA256 du fichier source
  - Signature HMAC-SHA256 avec clé dérivée
  - Stockage dans certification/registry/stamps.json
  - verify_stamp() détecte toute modification post-certification

Usage:
  from certification.immutable_stamp import ImmutableStamp
  stamp = ImmutableStamp()
  stamp.stamp("A-01", sha256_from_cert)
  ok, delta = stamp.verify("A-01")   # (True, None) ou (False, "drift détecté")
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent
_REGISTRY_DIR = _ROOT / "certification" / "registry"
_STAMPS_FILE = _REGISTRY_DIR / "stamps.json"
_DEFAULT_KEY = b"p10_immutable_stamp_key_v1"


@dataclass
class StampRecord:
    module_id: str
    source_path: str
    sha256: str
    hmac_sig: str
    stamped_at: float = field(default_factory=time.time)
    stamped_date: str = ""

    def __post_init__(self) -> None:
        from datetime import datetime, timezone

        self.stamped_date = datetime.fromtimestamp(
            self.stamped_at, tz=timezone.utc
        ).strftime("%Y-%m-%d")

    def to_dict(self) -> dict:
        return {
            "module_id": self.module_id,
            "source_path": self.source_path,
            "sha256": self.sha256,
            "hmac_sig": self.hmac_sig,
            "stamped_at": self.stamped_at,
            "stamped_date": self.stamped_date,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StampRecord":
        r = cls(
            module_id=d["module_id"],
            source_path=d["source_path"],
            sha256=d["sha256"],
            hmac_sig=d["hmac_sig"],
            stamped_at=float(d.get("stamped_at", 0.0)),
        )
        r.stamped_date = d.get("stamped_date", "")
        return r


def _sign(sha256: str, key: bytes) -> str:
    return hmac.new(key, sha256.encode(), hashlib.sha256).hexdigest()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class ImmutableStamp:
    """Scelle et vérifie l'intégrité des modules certifiés."""

    def __init__(
        self,
        root: Optional[Path] = None,
        stamps_file: Optional[Path] = None,
        sign_key: bytes = _DEFAULT_KEY,
    ) -> None:
        self._root = root or _ROOT
        self._stamps_file = stamps_file or _STAMPS_FILE
        self._key = sign_key
        self._stamps_file.parent.mkdir(parents=True, exist_ok=True)

    # ── Persistance ───────────────────────────────────────────────────────────

    def _load_all(self) -> dict[str, StampRecord]:
        if not self._stamps_file.exists():
            return {}
        try:
            raw = json.loads(self._stamps_file.read_text(encoding="utf-8"))
            return {k: StampRecord.from_dict(v) for k, v in raw.items()}
        except Exception:
            return {}

    def _save_all(self, stamps: dict[str, StampRecord]) -> None:
        tmp = self._stamps_file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({k: v.to_dict() for k, v in stamps.items()}, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._stamps_file)

    # ── Opérations ────────────────────────────────────────────────────────────

    def stamp(self, module_id: str, sha256: str, source_path: str = "") -> StampRecord:
        """Crée ou met à jour le sceau pour module_id avec le sha256 fourni."""
        sig = _sign(sha256, self._key)
        record = StampRecord(
            module_id=module_id,
            source_path=source_path,
            sha256=sha256,
            hmac_sig=sig,
        )
        stamps = self._load_all()
        stamps[module_id] = record
        self._save_all(stamps)
        return record

    def stamp_from_disk(self, module_id: str, source_path: str) -> StampRecord:
        """Calcule le SHA256 depuis le fichier sur disque et crée le sceau."""
        full = self._root / source_path.replace("/", os.sep)
        sha256 = _file_sha256(full)
        return self.stamp(module_id, sha256, source_path)

    def verify(self, module_id: str) -> tuple[bool, Optional[str]]:
        """
        Vérifie l'intégrité du sceau.
        Retourne (True, None) si OK, (False, raison) sinon.
        """
        stamps = self._load_all()
        record = stamps.get(module_id)
        if record is None:
            return False, f"Aucun sceau pour {module_id}"

        # Vérifie la signature
        expected_sig = _sign(record.sha256, self._key)
        if not hmac.compare_digest(record.hmac_sig, expected_sig):
            return False, "Signature HMAC invalide — registre altéré"

        # Si fichier source connu, compare le hash actuel
        if record.source_path:
            full = self._root / record.source_path.replace("/", os.sep)
            if not full.exists():
                return False, f"Fichier source introuvable : {record.source_path}"
            current = _file_sha256(full)
            if current != record.sha256:
                return False, (
                    f"DRIFT DÉTECTÉ — hash actuel {current[:16]}... "
                    f"!= certifié {record.sha256[:16]}..."
                )

        return True, None

    def verify_all(self) -> dict[str, tuple[bool, Optional[str]]]:
        stamps = self._load_all()
        return {mid: self.verify(mid) for mid in stamps}

    def get(self, module_id: str) -> Optional[StampRecord]:
        return self._load_all().get(module_id)

    def count(self) -> int:
        return len(self._load_all())

    def summary(self) -> str:
        results = self.verify_all()
        ok = sum(1 for ok, _ in results.values() if ok)
        lines = [
            f"ImmutableStamp — {len(results)} sceaux ({ok} OK, {len(results)-ok} FAIL)"
        ]
        for mid, (passed, reason) in results.items():
            mark = "OK" if passed else "FAIL"
            detail = f": {reason}" if reason else ""
            lines.append(f"  [{mark}] {mid}{detail}")
        return "\n".join(lines)
