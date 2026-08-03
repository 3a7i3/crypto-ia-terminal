"""Objet scientifique — socle commun.

KNOWLEDGE_MODEL §0-§1. Trois propriétés non négociables :

  M1  immuable après création — une correction crée un SUCCESSEUR
  M2  provenance obligatoire
  M3  auto-descriptif — JSON/texte, jamais un embedding comme source

L'immuabilité est structurelle (`frozen=True`) et non conventionnelle : une
tentative de mutation lève, elle n'est pas seulement découragée.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, ClassVar

from scios.objects.identity import parse
from scios.objects.provenance import Provenance

SCHEMA_VERSION = "1.0.0"


class ObjectError(ValueError):
    """Objet scientifique irrecevable."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ScientificObject:
    """Base de tous les objets du modèle.

    `version` s'incrémente par succession, jamais par mutation : produire une
    v2 crée un nouvel objet portant `supersedes` vers la v1, et la v1 reçoit à
    son tour un successeur déclaré. Aucun champ n'est jamais réécrit.
    """

    KIND: ClassVar[str] = "ScientificObject"

    id: str
    created_at: str
    provenance: Provenance
    epoch_id: str | None = None
    version: int = 1
    schema_version: str = SCHEMA_VERSION
    supersedes: str | None = None
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        parsed = parse(self.id)
        if parsed.kind != self.KIND:
            raise ObjectError(
                f"préfixe {self.id!r} incompatible avec le type {self.KIND!r}"
            )
        if self.version < 1:
            raise ObjectError("version doit être >= 1")
        if self.supersedes is not None:
            parse(self.supersedes)
        if self.superseded_by is not None:
            parse(self.superseded_by)
        if self.supersedes == self.id or self.superseded_by == self.id:
            raise ObjectError("un objet ne peut pas se succéder à lui-même (G-05)")

    # ── sérialisation ────────────────────────────────────────────────────────

    def payload(self) -> dict[str, Any]:
        """Champs propres au type concret. Redéfini par les sous-classes."""
        return {}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.KIND,
            "id": self.id,
            "schema_version": self.schema_version,
            "version": self.version,
            "created_at": self.created_at,
            "epoch_id": self.epoch_id,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "provenance": self.provenance.to_dict(),
        }
        out.update(self.payload())
        return out

    def canonical_json(self) -> str:
        """Représentation canonique — clés triées, UTF-8, séparateurs fixes.

        Spécification unique de canonicalisation pour tout le paquet : les
        contrôles d'empreinte du SSC s'y adossent au lieu d'en définir chacun
        une (invariant `Single Fingerprint Canonicalization Spec`).
        """
        return json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    # ── succession ───────────────────────────────────────────────────────────

    def succeed(self, new_id: str, **changes: Any) -> ScientificObject:
        """Produit le successeur de cet objet. Ne modifie jamais l'original."""
        if "id" in changes or "supersedes" in changes:
            raise ObjectError("id et supersedes sont fixés par la succession")
        return replace(
            self,
            id=new_id,
            version=self.version + 1,
            created_at=changes.pop("created_at", utc_now()),
            supersedes=self.id,
            superseded_by=None,
            **changes,
        )

    def mark_superseded(self, successor_id: str) -> ScientificObject:
        """Retourne une copie portant le successeur déclaré.

        L'original reste intact : c'est l'appelant (le magasin) qui journalise
        la nouvelle révision, en append-only.
        """
        parse(successor_id)
        if self.superseded_by is not None:
            raise ObjectError(f"{self.id} a déjà un successeur: {self.superseded_by}")
        return replace(self, superseded_by=successor_id)
