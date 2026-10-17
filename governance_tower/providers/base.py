"""Interfaces des fournisseurs de lecture (contrat GOV-TOWER-00, lots C et D).

Aucune méthode d'écriture n'existe dans ces interfaces. Une source qui refuse
l'accès rend ``DENIED`` ; une source absente rend ``NOT_AVAILABLE`` ; jamais une
collection vide présentée comme un résultat.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol, runtime_checkable

from governance_tower.contracts import (
    HostSnapshot,
    Observation,
    Provenance,
    RepositorySnapshot,
)

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    provenance: Provenance
    live: bool  # True seulement pour une lecture réelle explicitement activée
    description: str


@runtime_checkable
class GithubReadProvider(Protocol):
    """Lecture du dépôt : métadonnées, HEAD, CI, PR, issues, recherche de code bornée."""

    info: ProviderInfo

    def repository_snapshot(self) -> RepositorySnapshot:
        """Dépôt, branche par défaut, HEAD, CI du HEAD, PR ouvertes, issues de pilotage."""

    def locate_code(self, terms: tuple[str, ...]) -> Observation:
        """Chemins de fichiers pertinents (jamais de contenu de fichier interdit)."""

    def compare_commits(self, base_sha: str, head_sha: str) -> Observation:
        """Commits de ``head_sha`` absents de ``base_sha`` (titres bornés, non fiables)."""


@runtime_checkable
class HostObservationProvider(Protocol):
    """Observation hôte à partir de snapshots publiés et validés ; aucun shell."""

    info: ProviderInfo

    def host_snapshot(self) -> HostSnapshot:
        """Services allowlistés, stockage, déploiement, fraîcheur, ou absence qualifiée."""
