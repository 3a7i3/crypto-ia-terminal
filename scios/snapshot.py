"""Snapshot — le lien vérifiable entre le ledger et le dépôt.

Le ledger (L0) est la source de vérité. Git (L1) n'est pas un stockage, c'est
un **versionnement de constats**. Le manifeste est ce qui relie les deux : il
atteste, à un instant donné, du contenu exact des journaux.

Séquence de sortie du ledger hors du dépôt
------------------------------------------
Aujourd'hui le ledger est dans git, faute de réplication externe (L2). Le
retirer maintenant le ferait passer de mal répliqué à pas répliqué du tout.

Le manifeste inverse la dépendance : une fois qu'il existe et qu'il est
versionné, c'est LUI qui fait foi. La présence du JSONL brut dans le dépôt
devient redondante plutôt que porteuse, et son déplacement vers une
réplication externe devient une opération sans perte — il suffira de vérifier
que le ledger distant satisfait le manifeste versionné.

Le manifeste reste minuscule quel que soit le volume du ledger : c'est ce qui
permettra des millions d'événements sans transformer git en base de données.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scios.objects.base import canonical_dumps

MANIFEST_NAME = "SNAPSHOT.json"
JOURNALS = ("events.jsonl", "objects.jsonl", "identity.jsonl")


class SnapshotError(RuntimeError):
    """Le ledger ne satisfait pas son manifeste."""


def _digest(path: Path) -> tuple[str, int, int]:
    """-> (sha256, octets, lignes non vides). Lecture par blocs : le manifeste
    doit rester calculable sur un ledger de plusieurs gigaoctets."""
    sha = hashlib.sha256()
    size = 0
    lines = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            sha.update(chunk)
            size += len(chunk)
            lines += chunk.count(b"\n")
    return sha.hexdigest(), size, lines


@dataclass
class Snapshot:
    created_at: str
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        body = {
            "manifest_version": "1.0.0",
            "created_at": self.created_at,
            "files": self.files,
            "counts": self.counts,
        }
        body["manifest_fingerprint"] = hashlib.sha256(
            canonical_dumps(body).encode("utf-8")
        ).hexdigest()
        return body

    def render(self) -> str:
        lines = ["SNAPSHOT DU LEDGER", "", f"pris le {self.created_at}", ""]
        for name, meta in sorted(self.files.items()):
            if meta.get("present"):
                lines.append(
                    f"  {name:<18} {meta['lines']:>7} lignes  "
                    f"{meta['bytes']:>10} o  sha256:{meta['sha256'][:16]}"
                )
            else:
                lines.append(f"  {name:<18} absent")
        lines.append("")
        for kind, n in sorted(self.counts.items()):
            lines.append(f"  {kind:<18} {n:>7}")
        return "\n".join(lines)


def build(root: Path, created_at: str) -> Snapshot:
    """Calcule le manifeste. Lecture seule.

    `created_at` est fourni par l'appelant plutôt que lu de l'horloge : un
    manifeste doit être reproductible à l'identique à partir des mêmes fichiers.
    """
    root = Path(root)
    files: dict[str, dict[str, Any]] = {}
    for name in JOURNALS:
        path = root / name
        if not path.exists():
            files[name] = {"present": False}
            continue
        sha, size, lines = _digest(path)
        files[name] = {
            "present": True,
            "sha256": sha,
            "bytes": size,
            "lines": lines,
        }

    counts: dict[str, int] = {}
    objects = root / "objects.jsonl"
    if objects.exists():
        with objects.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                kind = json.loads(raw).get("kind", "?")
                counts[kind] = counts.get(kind, 0) + 1
    if files.get("events.jsonl", {}).get("present"):
        counts["Event"] = files["events.jsonl"]["lines"]

    return Snapshot(created_at=created_at, files=files, counts=counts)


def write(root: Path, created_at: str) -> Path:
    root = Path(root)
    dest = root / MANIFEST_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(build(root, created_at).to_dict(), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return dest


def verify(root: Path) -> list[str]:
    """Compare l'état des journaux au manifeste versionné.

    C'est le contrôle qui restera valable lorsque le ledger vivra hors du
    dépôt : il ne suppose rien de sa localisation, seulement de son contenu.
    """
    root = Path(root)
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        return [f"{MANIFEST_NAME} absent — aucun constat à opposer au ledger"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []

    declared = dict(manifest)
    claimed_fp = declared.pop("manifest_fingerprint", None)
    recomputed = hashlib.sha256(canonical_dumps(declared).encode("utf-8")).hexdigest()
    if claimed_fp != recomputed:
        problems.append(
            f"{MANIFEST_NAME} : empreinte du manifeste incohérente — "
            "le manifeste lui-même a été altéré"
        )

    for name, meta in manifest.get("files", {}).items():
        path = root / name
        if not meta.get("present"):
            if path.exists():
                problems.append(
                    f"{name} : présent alors que le manifeste le dit absent"
                )
            continue
        if not path.exists():
            problems.append(f"{name} : absent alors que le manifeste l'atteste")
            continue
        sha, size, lines = _digest(path)
        if sha != meta["sha256"]:
            problems.append(
                f"{name} : sha256 {sha[:16]} != {meta['sha256'][:16]} attendu — "
                f"contenu modifié ({meta['lines']} -> {lines} lignes)"
            )
    return problems
