"""Narrateur — raconte la vie decisionnelle interne de la machine.

Contrat : docs/CONTRAT_SUPERVISEUR.md § 2 (canal ①, « le Narrateur »).

Ce paquet est STRICTEMENT PASSIF (ADR-0007). Il lit la boite noire, met en
mots, agrege, et emet vers Telegram. Il n'importe rien du moteur de decision,
n'ecrit dans aucun etat runtime, et ne peut influencer aucune decision.
"""

from observability.narrator.budget import Budget, Emission
from observability.narrator.digest import Agregat
from observability.narrator.events import DIRECT, IGNORE, ROUTINE, Narration, classify
from observability.narrator.reader import BoiteNoire
from observability.narrator.runner import Narrateur
from observability.narrator.sender import Emetteur

__all__ = [
    "Budget",
    "Emission",
    "Agregat",
    "Narration",
    "Narrateur",
    "BoiteNoire",
    "Emetteur",
    "classify",
    "DIRECT",
    "ROUTINE",
    "IGNORE",
]
