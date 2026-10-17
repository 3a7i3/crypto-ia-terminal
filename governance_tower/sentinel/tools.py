"""Table fixe d'outils READ-ONLY de SENTINEL-01.

La table est figée à la construction : aucun outil ne peut être ajouté par une
demande, un contenu GitHub ou un journal. Un nom inconnu est refusé. Il n'existe
aucun outil d'écriture, de commande système, de redémarrage ou d'accès secret.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from governance_tower.contracts import (
    Availability,
    HostSnapshot,
    Observation,
    RepositorySnapshot,
    ToolCall,
    format_utc,
)
from governance_tower.providers.base import Clock, GithubReadProvider, HostObservationProvider

MAX_CALLS_PER_RUN = 6
#: Lectures ciblées GOV-TOWER-01 : enregistrées seulement si le fournisseur les offre.
OPTIONAL_GITHUB_TOOLS = (
    ("github.read_file", "Extrait borné d'un fichier admis, par SHA", "read_file"),
    ("github.issue_detail", "Issue nommée, corps borné", "issue_detail"),
    ("github.pull_detail", "PR nommée, corps borné", "pull_detail"),
    ("github.ci_for_sha", "CI d'un SHA exact", "ci_for_sha"),
)


class ToolDenied(RuntimeError):
    """Outil inconnu, non read-only ou budget épuisé : refus avant tout effet."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    read_only: bool = True

    def __post_init__(self) -> None:
        if self.read_only is not True:
            raise ToolDenied("seuls les outils read-only sont admis dans Sentinel")


def _availability(result: Any) -> Availability:
    if isinstance(result, (RepositorySnapshot, HostSnapshot, Observation)):
        return result.availability
    return Availability.AVAILABLE


class ToolRegistry:
    def __init__(
        self,
        github: GithubReadProvider,
        host: HostObservationProvider,
        clock: Clock,
    ) -> None:
        specs = (
            ToolSpec("github.repository_snapshot", "Dépôt, HEAD, CI, PR et issues", github.repository_snapshot),
            ToolSpec("github.locate_code", "Chemins de code par termes", github.locate_code),
            ToolSpec("github.compare_commits", "Commits entre deux SHA", github.compare_commits),
            ToolSpec("host.host_snapshot", "Snapshots publiés de l'hôte", host.host_snapshot),
        ) + tuple(
            ToolSpec(name, description, getattr(github, attr))
            for name, description, attr in OPTIONAL_GITHUB_TOOLS
            if callable(getattr(github, attr, None))
        )
        self._tools: Mapping[str, ToolSpec] = MappingProxyType({s.name: s for s in specs})
        self._clock = clock

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def session(self) -> "ToolSession":
        return ToolSession(self._tools, self._clock)


class ToolSession:
    """Une session par question : budget d'appels borné et journal des appels."""

    def __init__(self, tools: Mapping[str, ToolSpec], clock: Clock) -> None:
        self._tools = tools
        self._clock = clock
        self.calls: list[ToolCall] = []

    def invoke(self, name: str, *args: Any) -> Any:
        spec = self._tools.get(name)
        if spec is None:
            raise ToolDenied(f"outil inconnu refusé: {name[:60]}")
        if len(self.calls) >= MAX_CALLS_PER_RUN:
            raise ToolDenied("budget d'appels d'outils épuisé")
        started = format_utc(self._clock())
        result = spec.handler(*args)
        finished = format_utc(self._clock())
        self.calls.append(ToolCall(name, _availability(result), started, finished))
        return result
