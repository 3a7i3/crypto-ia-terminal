"""Provenance — le bloc qui rend le projet indépendant des modèles.

KNOWLEDGE_MODEL §2. Distinction structurante :

  actor_id   : le RÔLE, permanent          ex. "council.statistician"
  actor_impl : l'IMPLÉMENTATION, remplaçable  ex. "claude-opus-5"

Quand un modèle disparaît, le rôle survit, l'historique reste interprétable et
les taux de validation par rôle restent comparables dans le temps.

`limitations` est obligatoire et non vide : un acteur qui ne déclare pas ce
qu'il ne sait pas produit un objet irrecevable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ActorType(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    TOOL = "tool"
    RUNTIME = "runtime"


class ConfidenceBasis(str, Enum):
    """Sur quoi repose une confiance déclarée.

    Sans ce champ, un nombre de confiance est décoratif : 0.9 fondé sur
    l'intuition d'un modèle et 0.6 adossé à un verdict ne sont pas comparables.
    """

    VERDICT = "verdict_existant"
    REASONING = "raisonnement"
    ANALOGY = "analogie"
    MODEL_INTUITION = "intuition_du_modele"
    MEASUREMENT = "mesure"


class ProvenanceError(ValueError):
    """Bloc de provenance irrecevable."""


_SENTINELS = {"", "-", "n/a", "na", "none", "aucune", "rien", "tbd", "todo", "?"}


@dataclass(frozen=True)
class Provenance:
    actor_type: ActorType
    actor_id: str
    method: str
    limitations: str
    actor_impl: str | None = None
    actor_version: str | None = None
    inputs: tuple[str, ...] = ()
    confidence: float | None = None
    confidence_basis: ConfidenceBasis | None = None

    def __post_init__(self) -> None:
        if not self.actor_id or not self.actor_id.strip():
            raise ProvenanceError("actor_id obligatoire (INV-G03, K-08)")
        if not self.method or not self.method.strip():
            raise ProvenanceError(
                "method obligatoire — le procédé doit être reproductible"
            )
        if self.limitations.strip().lower() in _SENTINELS:
            raise ProvenanceError(
                "limitations obligatoire et non sentinelle — déclarer ce que "
                "l'acteur ne sait pas fait partie de l'objet"
            )
        if self.confidence is not None:
            if not 0.0 <= self.confidence <= 1.0:
                raise ProvenanceError("confidence doit être dans [0, 1]")
            if self.confidence_basis is None:
                raise ProvenanceError(
                    "confidence_basis obligatoire dès qu'une confidence est "
                    "déclarée — un nombre sans base n'est pas comparable"
                )
        if self.actor_type is ActorType.AGENT and not self.actor_impl:
            raise ProvenanceError(
                "actor_impl obligatoire pour un agent — le rôle survit au "
                "modèle, mais le modèle doit être nommé au moment des faits"
            )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "actor_type": self.actor_type.value,
            "actor_id": self.actor_id,
            "method": self.method,
            "limitations": self.limitations,
        }
        if self.actor_impl:
            out["actor_impl"] = self.actor_impl
        if self.actor_version:
            out["actor_version"] = self.actor_version
        if self.inputs:
            out["inputs"] = list(self.inputs)
        if self.confidence is not None:
            out["confidence"] = self.confidence
            out["confidence_basis"] = (
                self.confidence_basis.value if self.confidence_basis else None
            )
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Provenance:
        basis = data.get("confidence_basis")
        return cls(
            actor_type=ActorType(data["actor_type"]),
            actor_id=data["actor_id"],
            method=data["method"],
            limitations=data["limitations"],
            actor_impl=data.get("actor_impl"),
            actor_version=data.get("actor_version"),
            inputs=tuple(data.get("inputs", ())),
            confidence=data.get("confidence"),
            confidence_basis=ConfidenceBasis(basis) if basis else None,
        )


def measurement(
    tool: str, method: str, limitations: str, inputs: tuple[str, ...] = ()
) -> Provenance:
    """Provenance d'une mesure produite par un instrument du dépôt."""
    return Provenance(
        actor_type=ActorType.TOOL,
        actor_id=tool,
        method=method,
        limitations=limitations,
        inputs=inputs,
        confidence=1.0,
        confidence_basis=ConfidenceBasis.MEASUREMENT,
    )
