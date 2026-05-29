"""
certification/doc_freeze.py — G-03
Gel documentaire.

Vérifie, hash et gèle les documents critiques du projet.
Une fois gelés, toute modification est détectée.

Documents gelés :
  - ARBORESCENCE.md
  - certification/PLAN.md
  - README.md (si présent)
  - scripts/deploy_vps.sh
  - scripts/setup_vps_deploy.sh

Usage:
  from certification.doc_freeze import DocFreeze
  df = DocFreeze()
  manifest = df.freeze()         # gèle l'état actuel
  ok, drifts = df.verify()       # vérifie les dérives post-gel
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent
_FREEZE_FILE = _ROOT / "certification" / "registry" / "doc_freeze.json"
_DEFAULT_KEY = b"p10_doc_freeze_key_v1"

_DOC_PATHS = [
    "ARBORESCENCE.md",
    "certification/PLAN.md",
    "scripts/deploy_vps.sh",
    "scripts/setup_vps_deploy.sh",
    "scripts/install_services.sh",
]

_OPTIONAL_DOCS = [
    "README.md",
    "docs/architecture.md",
]


@dataclass
class DocRecord:
    path: str
    sha256: str
    size_bytes: int
    optional: bool = False

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "optional": self.optional,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DocRecord":
        return cls(
            path=d["path"],
            sha256=d["sha256"],
            size_bytes=int(d.get("size_bytes", 0)),
            optional=bool(d.get("optional", False)),
        )


@dataclass
class FreezeManifest:
    docs: list[DocRecord] = field(default_factory=list)
    frozen_at: float = field(default_factory=time.time)
    frozen_date: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        from datetime import datetime, timezone

        self.frozen_date = datetime.fromtimestamp(
            self.frozen_at, tz=timezone.utc
        ).strftime("%Y-%m-%d")

    def _canonical(self) -> dict:
        return {
            "docs": [d.to_dict() for d in sorted(self.docs, key=lambda x: x.path)],
            "frozen_at": round(self.frozen_at, 3),
        }

    def sign(self, key: bytes = _DEFAULT_KEY) -> "FreezeManifest":
        canonical = json.dumps(self._canonical(), sort_keys=True)
        self.signature = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        return self

    def verify_signature(self, key: bytes = _DEFAULT_KEY) -> bool:
        if not self.signature:
            return False
        canonical = json.dumps(self._canonical(), sort_keys=True)
        expected = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    def to_dict(self) -> dict:
        d = self._canonical()
        d["frozen_date"] = self.frozen_date
        d["signature"] = self.signature
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FreezeManifest":
        m = cls(
            docs=[DocRecord.from_dict(d) for d in data.get("docs", [])],
            frozen_at=float(data.get("frozen_at", 0.0)),
        )
        m.frozen_date = data.get("frozen_date", "")
        m.signature = data.get("signature", "")
        return m


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class DocFreeze:
    """Gèle et vérifie l'intégrité des documents critiques."""

    def __init__(
        self,
        root: Optional[Path] = None,
        freeze_file: Optional[Path] = None,
        sign_key: bytes = _DEFAULT_KEY,
    ) -> None:
        self._root = root or _ROOT
        self._freeze_file = freeze_file or _FREEZE_FILE
        self._key = sign_key
        self._freeze_file.parent.mkdir(parents=True, exist_ok=True)

    # ── Freeze ────────────────────────────────────────────────────────────────

    def freeze(self) -> FreezeManifest:
        import os

        docs: list[DocRecord] = []
        for rel in _DOC_PATHS:
            full = self._root / rel.replace("/", os.sep)
            if full.exists():
                docs.append(
                    DocRecord(
                        path=rel,
                        sha256=_sha256_file(full),
                        size_bytes=full.stat().st_size,
                        optional=False,
                    )
                )
        for rel in _OPTIONAL_DOCS:
            full = self._root / rel.replace("/", os.sep)
            if full.exists():
                docs.append(
                    DocRecord(
                        path=rel,
                        sha256=_sha256_file(full),
                        size_bytes=full.stat().st_size,
                        optional=True,
                    )
                )

        manifest = FreezeManifest(docs=docs)
        manifest.sign(self._key)

        self._freeze_file.write_text(
            json.dumps(manifest.to_dict(), indent=2),
            encoding="utf-8",
        )
        return manifest

    # ── Verify ────────────────────────────────────────────────────────────────

    def verify(self) -> tuple[bool, list[str]]:
        """
        Vérifie les dérives depuis le gel.
        Retourne (all_ok, liste_de_dérives).
        """
        import os

        if not self._freeze_file.exists():
            return False, ["Aucun gel trouvé — lance freeze() d'abord"]

        manifest = FreezeManifest.from_dict(
            json.loads(self._freeze_file.read_text(encoding="utf-8"))
        )

        if not manifest.verify_signature(self._key):
            return False, ["Signature du manifest invalide — fichier altéré"]

        drifts: list[str] = []
        for doc in manifest.docs:
            full = self._root / doc.path.replace("/", os.sep)
            if not full.exists():
                if not doc.optional:
                    drifts.append(f"MANQUANT : {doc.path}")
                continue
            current = _sha256_file(full)
            if current != doc.sha256:
                drifts.append(f"MODIFIÉ : {doc.path} (hash actuel {current[:12]}...)")

        return len(drifts) == 0, drifts

    def is_frozen(self) -> bool:
        return self._freeze_file.exists()

    def load_manifest(self) -> Optional[FreezeManifest]:
        if not self._freeze_file.exists():
            return None
        return FreezeManifest.from_dict(
            json.loads(self._freeze_file.read_text(encoding="utf-8"))
        )

    def summary(self) -> str:
        ok, drifts = self.verify()
        status = "FROZEN — intact" if ok else "DRIFT DÉTECTÉ"
        lines = [f"DocFreeze — {status}"]
        m = self.load_manifest()
        if m:
            lines.append(f"  Gelé le : {m.frozen_date} ({len(m.docs)} documents)")
        for d in drifts:
            lines.append(f"  [FAIL] {d}")
        return "\n".join(lines)
