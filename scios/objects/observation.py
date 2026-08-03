"""Observation — ce qui a été vu.

SCIENTIFIC_PROTOCOL §2 : l'observation décrit ce qui a été vu, **jamais
pourquoi**. Toute phrase causale la reclasse en hypothèse.

Contre-exemple gelé dans le protocole :
    « Le score ne classe pas les trades »            -> inférence, irrecevable
    « rho = 0.16 entre score et rendement à 12-24 h,
      N = 139, époque V4 »                            -> observation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from scios.objects.base import ObjectError, ScientificObject

# Marqueurs causaux : leur présence signale une inférence déguisée en
# observation. Détection lexicale volontairement grossière — elle ne prouve
# pas l'absence de causalité, elle attrape les cas les plus fréquents et force
# une reformulation. Un faux positif se contourne par `allow_causal_terms`,
# ce qui rend le contournement explicite et visible en revue.
_CAUSAL_MARKERS = (
    "parce que",
    "car ",
    "donc ",
    "à cause",
    "a cause",
    "en raison de",
    "provoque",
    "provoqué",
    "cause ",
    "causé",
    "entraîne",
    "entraine",
    "explique",
    "expliqué",
    "résulte de",
    "resulte de",
    "puisque",
    "s'ensuit",
    "il s'agit d'un bug",
    "le problème vient",
)


@dataclass(frozen=True)
class Observation(ScientificObject):
    """Un fait constaté, mesuré, sans interprétation."""

    KIND = "Observation"

    statement: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    n: int | None = None
    source_events: tuple[str, ...] = ()
    allow_causal_terms: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.statement.strip():
            raise ObjectError("statement obligatoire")
        if self.n is not None and self.n < 0:
            raise ObjectError("n ne peut pas être négatif")
        if not self.allow_causal_terms:
            found = self._causal_markers(self.statement)
            if found:
                raise ObjectError(
                    "l'énoncé contient un marqueur causal "
                    f"({', '.join(repr(f) for f in found)}) : une observation "
                    "décrit ce qui a été vu, jamais pourquoi "
                    "(SCIENTIFIC_PROTOCOL §2). Reformuler, ou déposer une "
                    "Hypothesis, ou passer allow_causal_terms=True en le "
                    "justifiant dans provenance.limitations."
                )

    @staticmethod
    def _causal_markers(text: str) -> list[str]:
        low = " " + re.sub(r"\s+", " ", text.lower()) + " "
        return [m for m in _CAUSAL_MARKERS if m in low]

    def payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "statement": self.statement,
            "metrics": self.metrics,
            "n": self.n,
            "source_events": list(self.source_events),
        }
        if self.allow_causal_terms:
            out["allow_causal_terms"] = True
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Observation:
        from scios.objects.provenance import Provenance

        return cls(
            id=data["id"],
            created_at=data["created_at"],
            provenance=Provenance.from_dict(data["provenance"]),
            epoch_id=data.get("epoch_id"),
            version=data.get("version", 1),
            schema_version=data.get("schema_version", "1.0.0"),
            supersedes=data.get("supersedes"),
            superseded_by=data.get("superseded_by"),
            statement=data["statement"],
            metrics=data.get("metrics", {}),
            n=data.get("n"),
            source_events=tuple(data.get("source_events", ())),
            allow_causal_terms=data.get("allow_causal_terms", False),
        )
