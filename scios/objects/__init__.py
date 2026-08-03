"""Objets scientifiques — Phase B1.

Socle : identité permanente, provenance obligatoire, immuabilité par
succession, magasin append-only. Un seul objet concret pour l'instant :
`Observation`, l'entrée de la boucle scientifique.
"""

from scios.objects.base import ObjectError, ScientificObject, utc_now
from scios.objects.identity import IdentityError, IdRegistry
from scios.objects.observation import Observation
from scios.objects.provenance import (
    ActorType,
    ConfidenceBasis,
    Provenance,
    ProvenanceError,
    measurement,
)
from scios.objects.store import ObjectStore, StoreError

__all__ = [
    "ActorType",
    "ConfidenceBasis",
    "IdRegistry",
    "IdentityError",
    "ObjectError",
    "ObjectStore",
    "Observation",
    "Provenance",
    "ProvenanceError",
    "ScientificObject",
    "StoreError",
    "measurement",
    "utc_now",
]
