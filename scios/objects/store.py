"""Magasin append-only des objets scientifiques.

Contrat C-04 / invariant M1 : un objet écrit n'est jamais modifié ni supprimé.
Une révision est une nouvelle ligne journalisée ; l'état courant d'un objet est
sa dernière révision, et l'historique complet reste rejouable.

Le fichier JSONL est la source de vérité. L'index en mémoire est un cache
reconstructible — perdre l'index ne perd aucune connaissance (PM-1).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Iterator

from scios.objects.base import ObjectError, ScientificObject, utc_now
from scios.objects.identity import IdRegistry
from scios.objects.observation import Observation
from scios.objects.provenance import Provenance

# Types concrets connus du magasin. Un `kind` absent de cette table est refusé
# à la relecture : mieux vaut échouer que désérialiser en objet générique.
DECODERS: dict[str, Any] = {
    "Observation": Observation.from_dict,
}


class StoreError(RuntimeError):
    """Violation d'un invariant du magasin."""


class ObjectStore:
    """Journal append-only + registre d'identité."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._journal = self._root / "objects.jsonl"
        self._lock = threading.Lock()
        self.ids = IdRegistry(self._root / "identity.jsonl")

    @property
    def journal(self) -> Path:
        return self._journal

    # ── écriture ─────────────────────────────────────────────────────────────

    def new_id(self, kind: str, year: int) -> str:
        return self.ids.allocate(kind, year)

    def append(self, obj: ScientificObject) -> ScientificObject:
        """Journalise une révision. N'écrase jamais une ligne existante."""
        if not self.ids.is_allocated(obj.id):
            raise StoreError(
                f"{obj.id} n'a pas été alloué par le registre d'identité — "
                "utiliser new_id() ou ids.reserve()"
            )
        record = {
            "_written_at": utc_now(),
            "_fingerprint": obj.fingerprint(),
            **obj.to_dict(),
        }
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            with self._journal.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return obj

    def create(self, cls: type, year: int, **fields: Any) -> ScientificObject:
        """Alloue un identifiant, construit l'objet et le journalise."""
        obj_id = self.new_id(cls.KIND, year)
        obj = cls(id=obj_id, created_at=fields.pop("created_at", utc_now()), **fields)
        return self.append(obj)

    def supersede(
        self, previous: ScientificObject, year: int, **changes: Any
    ) -> ScientificObject:
        """Crée le successeur et journalise les DEUX révisions.

        L'ancien objet n'est pas réécrit : une nouvelle ligne le déclare
        remplacé. Relire le journal donne l'historique complet.
        """
        successor_id = self.new_id(previous.KIND, year)
        successor = previous.succeed(successor_id, **changes)
        self.append(successor)
        self.append(previous.mark_superseded(successor_id))
        return successor

    # ── lecture ──────────────────────────────────────────────────────────────

    def read_all(self) -> Iterator[ScientificObject]:
        """Toutes les révisions, dans l'ordre d'écriture."""
        if not self._journal.exists():
            return
        for line_no, raw in enumerate(
            self._journal.read_text(encoding="utf-8").splitlines(), 1
        ):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise StoreError(f"{self._journal}:{line_no} corrompu: {exc}") from exc
            kind = rec.get("kind")
            decoder = DECODERS.get(kind)
            if decoder is None:
                raise StoreError(
                    f"{self._journal}:{line_no} type inconnu: {kind!r} — "
                    "ajouter un décodeur avant de relire ce journal"
                )
            yield decoder(rec)

    def current(self) -> dict[str, ScientificObject]:
        """État courant : dernière révision de chaque identifiant."""
        out: dict[str, ScientificObject] = {}
        for obj in self.read_all():
            out[obj.id] = obj
        return out

    def get(self, identifier: str) -> ScientificObject:
        obj = self.current().get(identifier)
        if obj is None:
            raise StoreError(f"objet introuvable: {identifier}")
        return obj

    def history(self, identifier: str) -> list[ScientificObject]:
        return [o for o in self.read_all() if o.id == identifier]

    # ── intégrité ────────────────────────────────────────────────────────────

    def verify(self) -> list[str]:
        """Contrôle d'intégrité. Retourne la liste des violations (vide = sain)."""
        problems: list[str] = []
        if not self._journal.exists():
            return problems
        for line_no, raw in enumerate(
            self._journal.read_text(encoding="utf-8").splitlines(), 1
        ):
            raw = raw.strip()
            if not raw:
                continue
            rec = json.loads(raw)
            kind = rec.get("kind")
            decoder = DECODERS.get(kind)
            if decoder is None:
                problems.append(f"ligne {line_no}: type inconnu {kind!r}")
                continue
            try:
                obj = decoder(rec)
            except (ObjectError, KeyError, ValueError) as exc:
                problems.append(f"ligne {line_no}: objet invalide — {exc}")
                continue
            expected = rec.get("_fingerprint")
            if expected and obj.fingerprint() != expected:
                problems.append(
                    f"ligne {line_no}: empreinte incohérente pour {obj.id} — "
                    "contenu altéré après écriture"
                )
            if not self.ids.is_allocated(obj.id):
                problems.append(
                    f"ligne {line_no}: {obj.id} absent du registre d'identité"
                )
        return problems


__all__ = ["ObjectStore", "StoreError", "Observation", "Provenance"]
