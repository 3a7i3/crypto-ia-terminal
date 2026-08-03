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

SCHEMA_VERSION = "1.1.0"

# Historique des schémas — un enregistrement se relit sous la version sous
# laquelle il a été écrit, jamais sous la version courante.
#
#   1.0.0  socle initial ; `source_events` acceptait n'importe quelle chaîne.
#   1.1.0  `source_events` n'accepte plus que des identifiants Event ; les
#          références de fichier ou d'outil passent par `source_artifacts`.
#
# Durcir une règle ne doit jamais rendre le passé illisible : un journal
# append-only ne se réécrit pas. Les contrôles introduits par une version ne
# s'appliquent donc qu'aux enregistrements écrits sous cette version ou après.


def schema_at_least(version: str, floor: str) -> bool:
    """Compare deux versions de schéma en ordre naturel (major.minor.patch)."""

    def parts(v: str) -> tuple[int, ...]:
        try:
            return tuple(int(x) for x in v.split("."))
        except ValueError:
            return (0,)

    return parts(version) >= parts(floor)


class ObjectError(ValueError):
    """Objet scientifique irrecevable."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_dumps(data: dict[str, Any]) -> str:
    """Sérialisation canonique unique du paquet — clés triées, séparateurs fixes.

    Invariant `Single Fingerprint Canonicalization Spec` : aucun autre endroit
    du code ne définit sa propre règle de hachage.
    """
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint_dict(data: dict[str, Any]) -> str:
    """Empreinte d'un enregistrement, calculée sur les DONNÉES ÉCRITES.

    Volontairement `dict -> str`, et non `objet -> str` : une empreinte doit
    attester des octets journalisés, jamais de ce que le code courant
    reconstruirait. Sans cela, ajouter un champ à la sérialisation invaliderait
    rétroactivement tout le journal — défaut constaté et corrigé lors de
    l'introduction de `source_artifacts` en schéma 1.1.0.

    Les clés de métadonnées de journalisation (préfixe `_`) sont exclues :
    elles décrivent l'écriture, pas l'objet.
    """
    return hashlib.sha256(
        canonical_dumps(
            {k: v for k, v in data.items() if not k.startswith("_")}
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class Recorded:
    """Socle de tout ce qui est enregistré : identité, provenance, empreinte.

    **Ne porte aucune machinerie de succession.** C'est délibéré : un `Event`
    (couche L1) a pour cycle de vie `RECORDED` -> jamais autre chose. Lui donner
    `supersedes` reviendrait à admettre qu'il puisse être révisé, ce que le
    modèle gelé interdit. La succession appartient à `ScientificObject` (L2+).
    """

    KIND: ClassVar[str] = "Recorded"

    id: str
    created_at: str
    provenance: Provenance
    epoch_id: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        parsed = parse(self.id)
        if parsed.kind != self.KIND:
            raise ObjectError(
                f"préfixe {self.id!r} incompatible avec le type {self.KIND!r}"
            )

    # ── sérialisation ────────────────────────────────────────────────────────

    def payload(self) -> dict[str, Any]:
        """Champs propres au type concret. Redéfini par les sous-classes."""
        return {}

    def header(self) -> dict[str, Any]:
        return {
            "kind": self.KIND,
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "epoch_id": self.epoch_id,
            "provenance": self.provenance.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        out = self.header()
        out.update(self.payload())
        return out

    def canonical_json(self) -> str:
        return canonical_dumps(self.to_dict())

    def fingerprint(self) -> str:
        return fingerprint_dict(self.to_dict())


@dataclass(frozen=True)
class ScientificObject(Recorded):
    """Objet des couches L2 et au-dessus — révisable par succession.

    `version` s'incrémente par succession, jamais par mutation : produire une
    v2 crée un nouvel objet portant `supersedes` vers la v1, et la v1 reçoit à
    son tour un successeur déclaré. Aucun champ n'est jamais réécrit.
    """

    KIND: ClassVar[str] = "ScientificObject"

    version: int = 1
    supersedes: str | None = None
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.version < 1:
            raise ObjectError("version doit être >= 1")
        if self.supersedes is not None:
            parse(self.supersedes)
        if self.superseded_by is not None:
            parse(self.superseded_by)
        if self.supersedes == self.id or self.superseded_by == self.id:
            raise ObjectError("un objet ne peut pas se succéder à lui-même (G-05)")

    def header(self) -> dict[str, Any]:
        out = super().header()
        out.update(
            {
                "version": self.version,
                "supersedes": self.supersedes,
                "superseded_by": self.superseded_by,
            }
        )
        return out

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
