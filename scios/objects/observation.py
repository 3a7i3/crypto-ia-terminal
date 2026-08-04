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

from scios.objects.base import ObjectError, ScientificObject, schema_at_least
from scios.objects.identity import IdentityError, parse

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
    source_artifacts: tuple[str, ...] = ()
    # Provenance d'une observation DERIVEE d'un grand nombre d'evenements :
    # inscrire les identifiants un a un couterait plus cher que le fait. Le
    # selecteur dit comment re-choisir exactement le meme ensemble, l'empreinte
    # atteste qu'il n'a pas change. Verification totale, cout constant.
    source_selector: dict[str, Any] = field(default_factory=dict)
    source_event_count: int | None = None
    source_event_digest: str | None = None
    allow_causal_terms: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.statement.strip():
            raise ObjectError("statement obligatoire")
        if self.n is not None and self.n < 0:
            raise ObjectError("n ne peut pas être négatif")
        # `source_events` référence des OBJETS du ledger, jamais des chemins.
        # Un fichier, un outil ou un rapport est une source d'ARTEFACT : la
        # distinction est ce qui rend la chaîne de provenance parcourable
        # jusqu'à l'atome (contrat C-02).
        #
        # Règle introduite en schéma 1.1.0. Les enregistrements antérieurs
        # restent lisibles tels quels : durcir une règle ne réécrit pas le
        # passé (voir base.SCHEMA_VERSION).
        if schema_at_least(self.schema_version, "1.1.0"):
            for ref in self.source_events:
                try:
                    kind = parse(ref).kind
                except IdentityError:
                    kind = None
                if kind != "Event":
                    detail = f" ({kind})" if kind else " (identifiant malformé)"
                    raise ObjectError(
                        f"source_events n'accepte que des identifiants Event, "
                        f"reçu {ref!r}{detail} — pour un fichier, un outil ou un "
                        "rapport, utiliser source_artifacts"
                    )
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
            "source_artifacts": list(self.source_artifacts),
            "source_selector": self.source_selector,
            "source_event_count": self.source_event_count,
            "source_event_digest": self.source_event_digest,
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
            schema_version=data.get("schema_version", "1.0.0"),  # legacy par défaut
            supersedes=data.get("supersedes"),
            superseded_by=data.get("superseded_by"),
            statement=data["statement"],
            metrics=data.get("metrics", {}),
            n=data.get("n"),
            source_events=tuple(data.get("source_events", ())),
            source_artifacts=tuple(data.get("source_artifacts", ())),
            source_selector=data.get("source_selector", {}),
            source_event_count=data.get("source_event_count"),
            source_event_digest=data.get("source_event_digest"),
            allow_causal_terms=data.get("allow_causal_terms", False),
        )
