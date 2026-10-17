"""Fournisseurs de lecture de Governance Tower : GitHub et observation hôte.

Chaque fournisseur expose uniquement des méthodes de lecture. Les implémentations
réelles sont opt-in et désactivées par défaut ; les fixtures portent la
provenance SYNTHETIC.
"""

from governance_tower.providers.base import (
    Clock,
    GithubReadProvider,
    HostObservationProvider,
    ProviderInfo,
)

__all__ = ["Clock", "GithubReadProvider", "HostObservationProvider", "ProviderInfo"]
